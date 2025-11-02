from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from collections.abc import Iterable
from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from json import JSONDecodeError
from pathlib import Path
from typing import Any, TextIO, cast

import requests
from ebook_dictionary_creator import DictionaryCreator
from rich.console import Console

from .kindle import KindleBuildError, kindle_lang_code
from .langutil import lang_meta
from .progress_bar import (
    _BaseProgressCapture,
    _DatabaseProgressCapture,
    _KindleProgressCapture,
    progress_bar,
)
from .source_base import DictionarySource
from .source_kaikki import KaikkiDownloadError, KaikkiParseError, KaikkiSource


class Builder:
    """
    Thin wrapper around ebook_dictionary_creator.
    Aggregates entries from configured sources and exports Kindle dictionaries.
    """

    def __init__(
        self,
        cache_dir: Path,
        show_progress: bool | None = None,
        sources: Iterable[DictionarySource] | None = None,
    ):
        """Configure cache location, HTTP session, and available dictionary sources."""
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self._show_progress = sys.stderr.isatty() if show_progress is None else show_progress
        self._console = Console(stderr=True, force_terminal=self._show_progress)
        self._progress_factory = partial(
            progress_bar,
            console=self._console,
            enabled=self._show_progress,
        )
        self._sources: list[DictionarySource]
        if sources is None:
            default_source = KaikkiSource(
                cache_dir=self.cache_dir,
                session=self.session,
                progress_factory=self._progress_factory,
            )
            self._sources = [default_source]
        else:
            self._sources = list(sources)

    def _emit_creator_output(self, label: str, capture: _BaseProgressCapture) -> None:
        """Dump captured stdout/stderr with a friendly heading when something goes wrong."""
        output = capture.output().strip()
        if not output:
            return
        self._console.print(f"[dictforge] {label}", style="yellow")
        self._console.print(output, style="dim")

    def _announce_summary(
        self,
        in_lang: str,
        out_lang: str,
        entry_count: int,
        capture: _KindleProgressCapture,
    ) -> None:
        """Print a post-build summary including base forms/inflection counts when available."""
        parts = [f"{entry_count:,} entries"]
        if capture.base_forms is not None:
            parts.append(f"{capture.base_forms:,} base forms")
        if capture.inflections is not None:
            parts.append(f"{capture.inflections:,} inflections")
        summary = ", ".join(parts)
        self._console.print(
            f"[dictforge] {in_lang} → {out_lang}: {summary}",
            style="green",
        )

    def _prepare_combined_entries(self, in_lang: str, out_lang: str) -> tuple[Path, int]:  # noqa: C901
        """Aggregate entries from each configured source, merging senses/examples by word."""
        if len(self._sources) == 1:
            source = self._sources[0]
            result = source.get_entries(in_lang, out_lang)
            source.log_filter_stats(in_lang, self._console)
            return result

        combined_dir = self.cache_dir / "combined"
        combined_dir.mkdir(parents=True, exist_ok=True)
        source_tag = "_".join(type(src).__name__ for src in self._sources)
        source_tag_slug = self._slugify(source_tag)
        filename = f"{self._slugify(in_lang)}__{self._slugify(out_lang)}__{source_tag_slug}.jsonl"
        combined_path = combined_dir / filename

        merged_entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for source in self._sources:
            data_path, _ = source.get_entries(in_lang, out_lang)
            source.log_filter_stats(in_lang, self._console)
            try:
                with data_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        payload = line.strip()
                        if not payload:
                            continue
                        try:
                            entry = json.loads(payload)
                        except json.JSONDecodeError as exc:
                            raise KaikkiParseError(data_path, exc) from exc
                        if not source.entry_has_content(entry):
                            continue
                        word = entry.get("word")
                        if not isinstance(word, str):
                            continue
                        key = word.lower()
                        if key not in merged_entries:
                            merged_entries[key] = copy.deepcopy(entry)
                        else:
                            self._merge_entry(merged_entries[key], entry)
            except OSError as exc:
                raise KaikkiDownloadError(
                    f"Failed to read source dataset '{data_path}': {exc}",
                ) from exc

        if not merged_entries:
            raise KaikkiDownloadError(
                f"No entries produced by configured sources for {in_lang} → {out_lang}.",
            )

        with combined_path.open("w", encoding="utf-8") as dst:
            for entry in merged_entries.values():
                dst.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return combined_path, len(merged_entries)

    def _merge_entry(self, target: dict[str, Any], incoming: dict[str, Any]) -> None:
        """Combine senses/examples from ``incoming`` into ``target`` without duplicates."""
        target_senses = target.get("senses")
        incoming_senses = incoming.get("senses")
        if not isinstance(target_senses, list) or not isinstance(incoming_senses, list):
            return

        index: dict[tuple[str, ...], dict[str, Any]] = {}
        for sense in target_senses:
            if not isinstance(sense, dict):
                continue
            glosses = sense.get("glosses")
            if isinstance(glosses, list) and glosses:
                key = tuple(str(g) for g in glosses)
                index[key] = sense

        for sense in incoming_senses:
            if not isinstance(sense, dict):
                continue
            glosses = sense.get("glosses")
            if isinstance(glosses, list) and glosses:
                key = tuple(str(g) for g in glosses)
                self._merge_examples(index[key], sense)
            else:
                target_senses.append(copy.deepcopy(sense))

    def _merge_examples(self, target_sense: dict[str, Any], incoming_sense: dict[str, Any]) -> None:
        """Append new example blocks from ``incoming_sense`` onto ``target_sense``."""
        incoming_examples = incoming_sense.get("examples")
        if not isinstance(incoming_examples, list) or not incoming_examples:
            return

        target_examples = target_sense.get("examples")
        if not isinstance(target_examples, list):
            target_examples = []
            target_sense["examples"] = target_examples

        for example in incoming_examples:
            exemplar = copy.deepcopy(example)
            if exemplar not in target_examples:
                target_examples.append(exemplar)

    def ensure_download_dirs(self, force: bool = False) -> None:  # noqa: ARG002
        """Delegate download preparation to each configured source."""
        if force:
            shutil.rmtree(self.cache_dir, ignore_errors=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for source in self._sources:
            source.ensure_download_dirs(force=force)

    def _slugify(self, value: str) -> str:
        """Return a filesystem-friendly slug used for cache file names."""
        return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()) or "language"

    def _export_one(  # noqa: PLR0913,PLR0915
        self,
        in_lang: str,
        out_lang: str,
        outdir: Path,
        kindlegen_path: str,
        title: str,
        shortname: str,  # noqa: ARG002
        include_pos: bool,  # noqa: ARG002
        try_fix_inflections: bool,
        max_entries: int,  # noqa: ARG002
        language_file: Path,
        entry_count: int,
        kindle_lang_override: str | None = None,
    ) -> int:
        """Build and export a single dictionary volume from the prepared Kaikki file."""
        iso_in, _ = lang_meta(in_lang)
        iso_out, _ = lang_meta(out_lang)
        kindle_in = kindle_lang_code(iso_in)
        kindle_out = kindle_lang_code(iso_out, override=kindle_lang_override)

        dc = DictionaryCreator(in_lang, out_lang, kaikki_file_path=str(language_file))
        dc.source_language = kindle_in
        dc.target_language = kindle_out
        database_path = self.cache_dir / f"{self._slugify(in_lang)}_{self._slugify(out_lang)}.db"
        db_capture = _DatabaseProgressCapture(console=self._console, enabled=self._show_progress)
        db_capture.start()
        try:
            with (
                redirect_stdout(cast(TextIO, db_capture)),
                redirect_stderr(cast(TextIO, db_capture)),
            ):
                try:
                    dc.create_database(database_path=str(database_path))
                except JSONDecodeError as exc:
                    raise KaikkiParseError(getattr(dc, "kaikki_file_path", None), exc) from exc
        except Exception:
            self._emit_creator_output("Database build output", db_capture)
            raise
        else:
            db_capture.finish()
        finally:
            db_capture.stop()
        mobi_base = outdir / f"{in_lang}-{out_lang}"
        shutil.rmtree(mobi_base, ignore_errors=True)
        kindle_capture = _KindleProgressCapture(
            console=self._console,
            enabled=self._show_progress,
            total_hint=entry_count if entry_count else None,
        )
        kindle_capture.start()
        fallback_exc: FileNotFoundError | None = None
        try:
            with (
                redirect_stdout(cast(TextIO, kindle_capture)),
                redirect_stderr(cast(TextIO, kindle_capture)),
            ):
                dc.export_to_kindle(
                    kindlegen_path=kindlegen_path,
                    try_to_fix_failed_inflections=try_fix_inflections,  # type: ignore[arg-type]  # bug in the lib
                    author="Wiktionary via Wiktextract (Kaikki.org)",
                    title=title,
                    mobi_temp_folder_path=str(mobi_base),
                    mobi_output_file_path=f"{mobi_base}.mobi",
                )
        except FileNotFoundError as exc:
            fallback_exc = exc
        except Exception:
            self._emit_creator_output("Kindle export output", kindle_capture)
            raise
        else:
            kindle_capture.finish()
        finally:
            kindle_capture.stop()

        if fallback_exc is None:
            self._announce_summary(in_lang, out_lang, entry_count, kindle_capture)
            return entry_count

        opf_path = mobi_base / "OEBPS" / "content.opf"
        if not opf_path.exists():
            raise KindleBuildError(
                "Kindle Previewer failed and content.opf is missing; see previous output.",
            ) from fallback_exc
        self._console.print(
            "[dictforge] Kindle Previewer fallback: fixing metadata and retrying",
            style="yellow",
        )
        self._ensure_opf_languages(opf_path, kindle_in, kindle_out, title)
        self._run_kindlegen(kindlegen_path, opf_path)
        mobi_path = mobi_base / "OEBPS" / "content.mobi"
        if not mobi_path.exists():
            raise KindleBuildError(
                "Kindle Previewer did not produce content.mobi even after fixing metadata.",
            ) from fallback_exc
        final_path = Path(f"{mobi_base}.mobi")
        shutil.move(mobi_path, final_path)
        dc.mobi_path = str(final_path)
        shutil.rmtree(mobi_base, ignore_errors=True)

        self._announce_summary(in_lang, out_lang, entry_count, kindle_capture)
        return entry_count

    def _ensure_opf_languages(  # noqa: PLR0912,C901
        self,
        opf_path: Path,
        primary_code: str,
        secondary_code: str,
        title: str,
    ) -> None:
        """Patch the OPF metadata so Kindle recognises the dictionary languages."""
        print(
            (
                f"[dictforge] Preparing OPF languages: source→'{primary_code}', "
                f"target→'{secondary_code}'"
            ),
            flush=True,
        )

        tree = ET.parse(opf_path)
        ns = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/",
            "legacy": "http://purl.org/metadata/dublin_core",
        }
        ET.register_namespace("", ns["opf"])
        ET.register_namespace("dc", ns["dc"])
        metadata = tree.find("opf:metadata", ns)
        if metadata is None:
            metadata = ET.SubElement(tree.getroot(), "{http://www.idpf.org/2007/opf}metadata")

        # modern dc:title/creator fallbacks
        if metadata.find("dc:title", ns) is None:
            title_elem = ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}title")
            title_elem.text = title or "dictforge dictionary"

        if metadata.find("dc:creator", ns) is None:
            legacy = metadata.find("opf:dc-metadata", ns)
            creator_text = None
            if legacy is not None:
                legacy_creator = legacy.find("legacy:Creator", ns)
                if legacy_creator is not None:
                    creator_text = legacy_creator.text
            ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}creator").text = (
                creator_text or "dictforge"
            )

        # modern dc:language entries
        for elem in list(metadata.findall("dc:language", ns)):
            metadata.remove(elem)
        ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}language").text = primary_code

        # legacy dc-metadata block
        legacy = metadata.find("opf:dc-metadata", ns)
        if legacy is not None:
            for elem in legacy.findall("legacy:Language", ns):
                elem.text = primary_code
            if legacy.find("legacy:Title", ns) is None:
                ET.SubElement(legacy, "{http://purl.org/metadata/dublin_core}Title").text = title
            if legacy.find("legacy:Creator", ns) is None:
                ET.SubElement(
                    legacy,
                    "{http://purl.org/metadata/dublin_core}Creator",
                ).text = "dictforge"

        # x-metadata block used by Kindle dictionaries
        x_metadata = metadata.find("opf:x-metadata", ns)
        if x_metadata is not None:
            dict_in = x_metadata.find("opf:DictionaryInLanguage", ns)
            if dict_in is not None:
                dict_in.text = primary_code
            dict_out = x_metadata.find("opf:DictionaryOutLanguage", ns)
            if dict_out is not None:
                dict_out.text = secondary_code
            default_lookup = x_metadata.find("opf:DefaultLookupIndex", ns)
            if default_lookup is None:
                ET.SubElement(
                    x_metadata,
                    "{http://www.idpf.org/2007/opf}DefaultLookupIndex",
                ).text = "default"

        tree.write(opf_path, encoding="utf-8", xml_declaration=True)

    def _run_kindlegen(self, kindlegen_path: str, opf_path: Path) -> None:
        """Invoke Kindle Previewer/kindlegen and surface helpful errors."""
        if not kindlegen_path:
            raise KindleBuildError("Kindle Previewer path is empty; cannot invoke kindlegen.")

        process = subprocess.run(
            [kindlegen_path, opf_path.name],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(opf_path.parent),
        )
        if process.returncode != 0:
            raise KindleBuildError(
                "Kindle Previewer reported an error after fixing metadata:\n"
                f"STDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}",
            )

    def build_dictionary(  # noqa: PLR0913
        self,
        in_langs: list[str],
        out_lang: str,
        title: str,
        shortname: str,
        outdir: Path,
        kindlegen_path: str,
        include_pos: bool,
        try_fix_inflections: bool,
        max_entries: int,
        kindle_lang_override: str | None = None,
    ) -> dict[str, int]:
        """Build the primary dictionary and any merged extras, returning entry counts."""
        counts: dict[str, int] = {}
        exports: list[tuple[str, Path, int, Path, str, str]] = []
        for index, in_lang in enumerate(in_langs):
            combined_file, entry_count = self._prepare_combined_entries(in_lang, out_lang)
            if index == 0:
                volume_outdir = outdir
                volume_title = title
                volume_shortname = shortname
            else:
                extra_slug = in_lang.replace(" ", "_")
                volume_outdir = outdir / f"extra_{extra_slug}"
                volume_outdir.mkdir(parents=True, exist_ok=True)
                volume_title = f"{title} (extra: {in_lang})"
                volume_shortname = f"{shortname}+{in_lang}"
            exports.append(
                (
                    in_lang,
                    combined_file,
                    entry_count,
                    volume_outdir,
                    volume_title,
                    volume_shortname,
                ),
            )

        for (
            in_lang,
            combined_file,
            entry_count,
            volume_outdir,
            volume_title,
            volume_shortname,
        ) in exports:
            counts[in_lang] = self._export_one(
                in_lang,
                out_lang,
                volume_outdir,
                kindlegen_path,
                volume_title,
                volume_shortname,
                include_pos,
                try_fix_inflections,
                max_entries,
                combined_file,
                entry_count,
                kindle_lang_override,
            )

        self.session.close()
        return counts
