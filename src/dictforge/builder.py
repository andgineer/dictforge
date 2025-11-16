import copy
import json
import re
import shutil
import sys
from collections import OrderedDict
from collections.abc import Iterable
from functools import partial
from pathlib import Path
from typing import Any

import requests
from rich.console import Console

from .export_base import ExportFormat
from .export_mobi import MobiExportFormat
from .export_stardict import StarDictExportFormat

# Re-export for backwards compatibility
from .kindle import KindleBuildError  # noqa: F401
from .progress_bar import progress_bar
from .source_base import DictionarySource
from .source_kaikki import KaikkiDownloadError, KaikkiParseError, KaikkiSource


def get_available_formats() -> dict[str, type[ExportFormat]]:
    """Return a dictionary of available export format classes."""
    return {
        "mobi": MobiExportFormat,
        "stardict": StarDictExportFormat,
    }


class Builder:
    """
    Thin wrapper around dictionary sources and export formats.
    Aggregates entries from configured sources and exports dictionaries.
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

    def _create_export_format(self, format_name: str) -> ExportFormat:
        """Create an export format instance by name."""
        formats = get_available_formats()
        if format_name not in formats:
            available = ", ".join(formats.keys())
            raise ValueError(f"Unknown export format '{format_name}'. Available: {available}")

        format_class = formats[format_name]

        # MOBI format needs cache_dir for database creation
        if format_name == "mobi":
            return MobiExportFormat(
                cache_dir=self.cache_dir,
                console=self._console,
                show_progress=self._show_progress,
            )
        return format_class(
            console=self._console,
            show_progress=self._show_progress,
        )

    def _export_one(  # noqa: PLR0913
        self,
        in_lang: str,
        out_lang: str,
        outdir: Path,
        title: str,
        language_file: Path,
        entry_count: int,
        export_format: ExportFormat,
        export_options: dict[str, Any],
    ) -> int:
        """Build and export a single dictionary volume using the specified format."""
        export_format.export(
            entries_file=language_file,
            entry_count=entry_count,
            in_lang=in_lang,
            out_lang=out_lang,
            outdir=outdir,
            title=title,
            **export_options,
        )
        return entry_count

    def build_dictionary(  # noqa: PLR0913
        self,
        in_langs: list[str],
        out_lang: str,
        title: str,
        shortname: str,
        outdir: Path,
        export_format: str = "mobi",
        export_options: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        """
        Build the primary dictionary and any merged extras, returning entry counts.

        Args:
            in_langs: List of input languages (first is primary, rest are extras).
            out_lang: Output language.
            title: Dictionary title.
            shortname: Short name for the dictionary.
            outdir: Output directory.
            export_format: Name of export format to use ('mobi', 'stardict', etc.).
            export_options: Format-specific options.

        Returns:
            Dictionary mapping language names to entry counts.
        """
        if export_options is None:
            export_options = {}

        # Create export format instance
        format_instance = self._create_export_format(export_format)

        # Validate options before starting
        format_instance.validate_options(**export_options)

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
            _volume_shortname,
        ) in exports:
            counts[in_lang] = self._export_one(
                in_lang,
                out_lang,
                volume_outdir,
                volume_title,
                combined_file,
                entry_count,
                format_instance,
                export_options,
            )

        self.session.close()
        return counts
