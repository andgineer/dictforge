"""MOBI/Kindle dictionary export format."""

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from json import JSONDecodeError
from pathlib import Path
from typing import Any, TextIO, cast

from ebook_dictionary_creator import DictionaryCreator
from rich.console import Console

from .export_base import ExportFormat
from .kaikki_utils import lang_meta
from .kindle import KindleBuildError, kindle_lang_code
from .progress_bar import (
    _BaseProgressCapture,
    _DatabaseProgressCapture,
    _KindleProgressCapture,
)
from .source_kaikki import KaikkiParseError


class MobiExportFormat(ExportFormat):
    """
    Export dictionary to MOBI format for Kindle devices.

    Uses ebook_dictionary_creator library and kindlegen for conversion.
    """

    def __init__(
        self,
        cache_dir: Path,
        console: Console | None = None,
        show_progress: bool = True,
    ):
        """
        Initialize MOBI exporter.

        Args:
            cache_dir: Directory for caching intermediate database files.
            console: Rich console for output.
            show_progress: Whether to show progress indicators.
        """
        super().__init__(console, show_progress)
        self._cache_dir = cache_dir

    @property
    def name(self) -> str:
        """Return format name."""
        return "mobi"

    @property
    def description(self) -> str:
        """Return format description."""
        return "Kindle MOBI dictionary format"

    def validate_options(self, **options: Any) -> None:
        """
        Validate MOBI-specific options.

        Required options:
            kindlegen_path: Path to kindlegen executable.

        Optional options:
            try_fix_inflections: Whether to fix inflections (default: False).
            kindle_lang_override: Override Kindle language code.
        """
        kindlegen_path = options.get("kindlegen_path", "")
        if not kindlegen_path:
            raise ValueError("kindlegen_path is required for MOBI export")

        kindlegen = Path(kindlegen_path)
        if not kindlegen.exists():
            raise ValueError(f"kindlegen not found at: {kindlegen_path}")

    def export(  # noqa: PLR0913
        self,
        entries_file: Path,
        entry_count: int,
        in_lang: str,
        out_lang: str,
        outdir: Path,
        title: str,
        **options: Any,
    ) -> Path:
        """
        Export dictionary entries to MOBI format.

        Args:
            entries_file: Path to JSONL file with entries.
            entry_count: Number of entries.
            in_lang: Input language name.
            out_lang: Output language name.
            outdir: Output directory.
            title: Dictionary title.
            **options: Additional options:
                - kindlegen_path: Path to kindlegen (required).
                - try_fix_inflections: Fix inflections (default: False).
                - kindle_lang_override: Override Kindle language code.

        Returns:
            Path to the generated .mobi file.
        """
        kindlegen_path = options.get("kindlegen_path", "")
        try_fix_inflections = options.get("try_fix_inflections", False)
        kindle_lang_override = options.get("kindle_lang_override")

        iso_in, _ = lang_meta(in_lang)
        iso_out, _ = lang_meta(out_lang)
        kindle_in = kindle_lang_code(iso_in)
        kindle_out = kindle_lang_code(iso_out, override=kindle_lang_override)

        dc = DictionaryCreator(in_lang, out_lang, kaikki_file_path=str(entries_file))
        dc.source_language = kindle_in
        dc.target_language = kindle_out

        # Create database
        database_path = self._cache_dir / f"{self._slugify(in_lang)}_{self._slugify(out_lang)}.db"
        self._create_database(dc, database_path)

        # Export to MOBI
        mobi_base = outdir / f"{in_lang}-{out_lang}"
        shutil.rmtree(mobi_base, ignore_errors=True)

        output_path = self._export_kindle(
            dc=dc,
            mobi_base=mobi_base,
            entry_count=entry_count,
            kindlegen_path=kindlegen_path,
            try_fix_inflections=try_fix_inflections,
            kindle_in=kindle_in,
            kindle_out=kindle_out,
            title=title,
        )

        self.announce_summary(in_lang, out_lang, entry_count, output_path)
        return output_path

    def _slugify(self, value: str) -> str:
        """Return a filesystem-friendly slug."""
        return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()) or "language"

    def _emit_creator_output(self, label: str, capture: _BaseProgressCapture) -> None:
        """Dump captured stdout/stderr with a friendly heading."""
        output = capture.output().strip()
        if not output:
            return
        self._console.print(f"[dictforge] {label}", style="yellow")
        self._console.print(output, style="dim")

    def _create_database(self, dc: DictionaryCreator, database_path: Path) -> None:
        """Create SQLite database from dictionary entries."""
        db_capture = _DatabaseProgressCapture(
            console=self._console,
            enabled=self._show_progress,
        )
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

    def _export_kindle(  # noqa: PLR0913
        self,
        dc: DictionaryCreator,
        mobi_base: Path,
        entry_count: int,
        kindlegen_path: str,
        try_fix_inflections: bool,
        kindle_in: str,
        kindle_out: str,
        title: str,
    ) -> Path:
        """Perform the actual Kindle export with fallback for metadata issues."""
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
                    try_to_fix_failed_inflections=try_fix_inflections,  # type: ignore[arg-type]
                    author="andgineer/dictforge",
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
            return Path(f"{mobi_base}.mobi")

        # Fallback: fix OPF metadata and retry
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

        return final_path

    def _ensure_opf_languages(  # noqa: PLR0912, C901
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

    def announce_summary(
        self,
        in_lang: str,
        out_lang: str,
        entry_count: int,
        output_path: Path,
    ) -> None:
        """Print a post-build summary with MOBI-specific info."""
        parts = [f"{entry_count:,} entries"]
        summary = ", ".join(parts)
        self._console.print(
            f"[dictforge] {in_lang} → {out_lang}: {summary} → {output_path}",
            style="green",
        )
