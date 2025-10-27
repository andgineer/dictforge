from __future__ import annotations

import copy
import io
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import requests
from ebook_dictionary_creator import DictionaryCreator
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    Task,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from .langutil import lang_meta
from .source_base import DictionarySource
from .source_kaikki import KaikkiDownloadError, KaikkiParseError, KaikkiSource

KINDLE_SUPPORTED_LANGS = {
    "af",
    "sq",
    "ar",
    "ar-dz",
    "ar-bh",
    "ar-eg",
    "ar-iq",
    "ar-jo",
    "ar-kw",
    "ar-lb",
    "ar-ly",
    "ar-ma",
    "ar-om",
    "ar-qa",
    "ar-sa",
    "ar-sy",
    "ar-tn",
    "ar-ae",
    "ar-ye",
    "hy",
    "az",
    "eu",
    "be",
    "bn",
    "bg",
    "ca",
    "zh",
    "zh-hk",
    "zh-cn",
    "zh-sg",
    "zh-tw",
    "hr",
    "cs",
    "da",
    "nl",
    "nl-be",
    "en",
    "en-au",
    "en-bz",
    "en-ca",
    "en-ie",
    "en-jm",
    "en-nz",
    "en-ph",
    "en-za",
    "en-tt",
    "en-gb",
    "en-us",
    "en-zw",
    "et",
    "fo",
    "fa",
    "fi",
    "fr",
    "fr-be",
    "fr-ca",
    "fr-lu",
    "fr-mc",
    "fr-ch",
    "ka",
    "de",
    "de-at",
    "de-li",
    "de-lu",
    "de-ch",
    "el",
    "gu",
    "he",
    "hi",
    "hu",
    "is",
    "id",
    "it",
    "it-ch",
    "ja",
    "kn",
    "kk",
    "x-kok",
    "ko",
    "lv",
    "lt",
    "mk",
    "ms",
    "ms-bn",
    "ml",
    "mt",
    "mr",
    "ne",
    "no",
    "no-bok",
    "no-nyn",
    "or",
    "pl",
    "pt",
    "pt-br",
    "pa",
    "rm",
    "ro",
    "ro-mo",
    "ru",
    "ru-mo",
    "sz",
    "sa",
    "sr-latn",
    "sk",
    "sl",
    "sb",
    "es",
    "es-ar",
    "es-bo",
    "es-cl",
    "es-co",
    "es-cr",
    "es-do",
    "es-ec",
    "es-sv",
    "es-gt",
    "es-hn",
    "es-mx",
    "es-ni",
    "es-pa",
    "es-py",
    "es-pe",
    "es-pr",
    "es-uy",
    "es-ve",
    "sx",
    "sw",
    "sv",
    "sv-fi",
    "ta",
    "tt",
    "te",
    "th",
    "ts",
    "tn",
    "tr",
    "uk",
    "ur",
    "uz",
    "vi",
    "xh",
    "zu",
}


class KindleBuildError(RuntimeError):
    """Raised when kindlegen fails while creating the MOBI file."""


def _format_units(task: Task, unit: str) -> str:
    """Present rich-progress counts with human-friendly thousands separators."""
    completed = int(task.completed or 0)
    total = task.total
    label = unit if unit != "B" else "B"
    if total is None:
        return f"{completed:,} {label}"
    return f"{completed:,}/{int(total):,} {label}"


class _BaseProgressCapture:
    """Mirror stdout/stderr into a Rich task while collecting diagnostic text."""

    def __init__(
        self,
        *,
        console: Console,
        enabled: bool,
        description: str,
        unit: str,
        total_hint: int | None = None,
    ) -> None:
        """Capture console/progress configuration and reset buffered state."""
        self._console = console
        self._enabled = enabled
        self._description = description
        self._unit = unit
        self._total_hint = total_hint
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._captured = io.StringIO()
        self._buffer = ""
        self._current = 0
        self._warnings: list[str] = []

    def _format_description(self, text: str) -> str:
        """Append unit information to ``text`` for nicer progress labels."""
        unit_hint = f" [{self._unit}]" if self._unit else ""
        return f"{text}{unit_hint}"

    def start(self) -> None:
        """Create the Rich progress task if progress output is enabled."""
        if not self._enabled:
            return
        columns = [
            TextColumn("[progress.description]{task.description}"),
            SpinnerColumn(),
            BarColumn(bar_width=None),
            TextColumn("{task.completed:,}", justify="right"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ]
        self._progress = Progress(
            *columns,
            console=self._console,
            transient=False,
            refresh_per_second=5,
            expand=True,
        )
        self._progress.__enter__()
        self._task_id = self._progress.add_task(
            self._format_description(self._description),
            total=self._total_hint,
        )

    def stop(self) -> None:
        """Flush buffered text and tear down the Rich progress context."""
        if self._buffer.strip():
            self.handle_line(self._buffer.strip())
        self._buffer = ""
        if self._progress is not None and self._task_id is not None:
            self._progress.__exit__(None, None, None)
            self._progress = None

    def write(self, text: str) -> int:
        """Buffer ``text`` and dispatch whole lines to :meth:`handle_line`."""
        self._captured.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self.handle_line(line.strip())
        return len(text)

    def flush(self) -> None:  # pragma: no cover - interface requirement
        """Satisfy the file-like interface expected by ``redirect_stdout``."""
        return

    def handle_line(self, line: str) -> None:  # pragma: no cover - overridden
        """Record non-empty ``line`` values as warnings for later inspection."""
        if line:
            self._warnings.append(line)

    def set_total(self, total: int) -> None:
        """Switch the task into determinate mode when ``total`` becomes known."""
        if total < 0:
            return
        self._total_hint = total
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, total=total)  # type: ignore

    def advance_to(self, value: int) -> None:
        """Advance the completed counter monotonically to ``value``."""
        if value <= self._current:
            return
        self._current = value
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, completed=value)  # type: ignore

    def set_description(self, description: str) -> None:
        """Update the text displayed alongside the progress indicator."""
        self._description = description
        if self._progress is not None and self._task_id is not None:
            self._progress.update(
                self._task_id,  # type: ignore
                description=self._format_description(description),
            )

    def finish(self) -> None:
        """Ensure the task reaches completion once the wrapped job ends."""
        if self._progress is not None and self._task_id is not None:
            completed = self._total_hint if self._total_hint is not None else self._current
            self._progress.update(self._task_id, completed=completed)  # type: ignore

    @property
    def warnings(self) -> list[str]:
        """Warnings captured from the underlying tool's stdout/stderr."""
        return self._warnings

    def output(self) -> str:
        """Return the raw captured output (including buffered partial lines)."""
        if self._buffer.strip():
            self.handle_line(self._buffer.strip())
            self._buffer = ""
        return self._captured.getvalue()


class _DatabaseProgressCapture(_BaseProgressCapture):
    """Interpret database build output to keep the progress bar in sync."""

    def __init__(self, *, console: Console, enabled: bool) -> None:
        super().__init__(
            console=console,
            enabled=enabled,
            description="Building database",
            unit="inflections",
        )

    def handle_line(self, line: str) -> None:
        """Translate sqlite import chatter into progress updates and messages."""
        if not line:
            return
        if line.endswith("inflections to add manually"):
            try:
                total = int(line.split(" ", 1)[0])
            except ValueError:
                return
            self.set_description("Adding inflections")
            self.set_total(total)
        elif line.isdigit():
            self.advance_to(int(line))
        elif line.endswith("relations with 3 elements"):
            self.set_description("Linking inflections")
        else:
            self.warnings.append(line)


class _KindleProgressCapture(_BaseProgressCapture):
    """Track kindlegen/Kindle Previewer output to surface friendly status."""

    def __init__(
        self,
        *,
        console: Console,
        enabled: bool,
        total_hint: int | None,
    ) -> None:
        super().__init__(
            console=console,
            enabled=enabled,
            description="Creating Kindle dictionary",
            unit="words",
            total_hint=total_hint,
        )
        self.base_forms: int | None = None
        self.inflections: int | None = None

    def handle_line(self, line: str) -> None:  # noqa: C901,PLR0912
        """Derive progress milestones from Kindle Previewer console output."""
        if not line:
            return
        if line == "Getting base forms":
            self.set_description("Loading base forms")
        elif line.startswith("Iterating through base forms"):
            self.set_description("Processing base forms")
        elif line.endswith(" words"):
            try:
                words = int(line.split(" ", 1)[0])
            except ValueError:
                return
            if self._total_hint is None and self.base_forms is not None:
                self.set_total(self.base_forms)
            elif self._total_hint is None:
                self.set_total(words)
            self.advance_to(words)
        elif line == "Creating dictionary":
            self.set_description("Compiling dictionary")
        elif line == "Writing dictionary":
            self.set_description("Writing MOBI file")
        elif line.endswith(" base forms"):
            try:
                self.base_forms = int(line.split(" ", 1)[0])
            except ValueError:
                return
            self.set_total(self.base_forms)
            self.advance_to(self.base_forms)
        elif line.endswith(" inflections"):
            try:
                self.inflections = int(line.split(" ", 1)[0])
            except ValueError:
                self.inflections = None
        else:
            self.warnings.append(line)


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
        self._sources: list[DictionarySource]
        if sources is None:
            default_source = KaikkiSource(
                cache_dir=self.cache_dir,
                session=self.session,
                progress_factory=self._progress_bar,
            )
            self._sources = [default_source]
        else:
            self._sources = list(sources)

    @contextmanager
    def _progress_bar(
        self,
        *,
        description: str,
        total: int | None = None,
        unit: str = "entries",
    ) -> Iterator[Callable[[int], None]]:
        """Yield a callback that advances a Rich progress bar, or a noop when hidden."""
        if not self._show_progress:

            def noop(_: int) -> None:
                return None

            yield noop
            return

        columns: list[Any] = [TextColumn("[progress.description]{task.description}")]
        if total is None:
            columns.append(SpinnerColumn())
        else:
            columns.append(BarColumn(bar_width=None))
        if unit == "B":
            columns.extend([DownloadColumn(), TransferSpeedColumn()])
        columns.append(TimeElapsedColumn())
        if total is not None:
            columns.append(TimeRemainingColumn())
        else:
            label = "bytes" if unit == "B" else unit
            columns.append(TextColumn(f"{{task.completed:,}} {label}"))

        progress = Progress(
            *columns,
            console=self._console,
            transient=False,
            refresh_per_second=4,
            expand=True,
        )
        with progress:
            task_id = progress.add_task(description, total=total)

            def advance(amount: int) -> None:
                progress.update(task_id, advance=amount)

            yield advance

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
            return self._sources[0].get_entries(in_lang, out_lang)

        combined_dir = self.cache_dir / "combined"
        combined_dir.mkdir(parents=True, exist_ok=True)
        source_tag = "_".join(type(src).__name__ for src in self._sources)
        source_tag_slug = self._slugify(source_tag)
        filename = f"{self._slugify(in_lang)}__{self._slugify(out_lang)}__{source_tag_slug}.jsonl"
        combined_path = combined_dir / filename

        merged_entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for source in self._sources:
            data_path, _ = source.get_entries(in_lang, out_lang)
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

    def ensure_download(self, force: bool = False) -> None:  # noqa: ARG002
        """Delegate download preparation to each configured source."""
        # Placeholder for future caching/version pinning; ensure dir exists.
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for source in self._sources:
            source.ensure_download(force=force)

    def _slugify(self, value: str) -> str:
        """Return a filesystem-friendly slug used for cache file names."""
        return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()) or "language"

    def _kindle_lang_code(self, code: str | None, override: str | None = None) -> str:
        """Derive the Kindle language identifier, applying overrides/fallbacks."""
        if override:
            normalized_override = override.lower()
            if normalized_override in KINDLE_SUPPORTED_LANGS:
                return normalized_override
            raise KindleBuildError(
                (
                    f"Kindle language override '{override}' is not supported by Kindle. "
                    "Check the supported list and pick a valid code."
                ),
            )

        if not code:
            return "en"

        normalized = code.lower()
        if normalized in KINDLE_SUPPORTED_LANGS:
            return normalized

        overrides = {
            "sr": "hr",
            "en": "en-us",
        }
        normalized = overrides.get(normalized, normalized)

        if normalized == "en":
            return "en-us"

        return normalized if normalized in KINDLE_SUPPORTED_LANGS else "en"

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
        kindle_in = self._kindle_lang_code(iso_in)
        kindle_out = self._kindle_lang_code(iso_out, override=kindle_lang_override)

        dc = DictionaryCreator(in_lang, out_lang, kaikki_file_path=str(language_file))
        dc.source_language = kindle_in
        dc.target_language = kindle_out
        database_path = self.cache_dir / f"{self._slugify(in_lang)}_{self._slugify(out_lang)}.db"
        db_capture = _DatabaseProgressCapture(console=self._console, enabled=self._show_progress)
        db_capture.start()
        try:
            with redirect_stdout(db_capture), redirect_stderr(db_capture):  # type: ignore
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
            with redirect_stdout(kindle_capture), redirect_stderr(kindle_capture):  # type: ignore
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
        primary = in_langs[0]
        counts = {}
        primary_file, primary_count = self._prepare_combined_entries(primary, out_lang)
        counts[primary] = self._export_one(
            primary,
            out_lang,
            outdir,
            kindlegen_path,
            title,
            shortname,
            include_pos,
            try_fix_inflections,
            max_entries,
            primary_file,
            primary_count,
            kindle_lang_override,
        )

        for extra in in_langs[1:]:
            extra_out = outdir / f"extra_{extra.replace(' ', '_')}"
            extra_out.mkdir(parents=True, exist_ok=True)
            extra_file, extra_count = self._prepare_combined_entries(extra, out_lang)
            counts[extra] = self._export_one(
                extra,
                out_lang,
                extra_out,
                kindlegen_path,
                f"{title} (extra: {extra})",
                f"{shortname}+{extra}",
                include_pos,
                try_fix_inflections,
                max_entries,
                extra_file,
                extra_count,
                kindle_lang_override,
            )

        self.session.close()
        return counts
