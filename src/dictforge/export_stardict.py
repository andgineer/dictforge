"""StarDict dictionary export format."""

import gzip
import json
import re
import struct
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeRemainingColumn

from .export_base import ExportFormat


class StarDictExportFormat(ExportFormat):
    """
    Export dictionary to StarDict format.

    StarDict is an open format used by various dictionary applications.
    It consists of three main files:
    - .ifo: Dictionary information/metadata
    - .idx: Word index with offsets and sizes
    - .dict/.dict.dz: Dictionary data (optionally compressed)
    """

    @property
    def name(self) -> str:
        """Return format name."""
        return "stardict"

    @property
    def description(self) -> str:
        """Return format description."""
        return "StarDict dictionary format (compatible with GoldenDict, etc.)"

    def validate_options(self, **options: Any) -> None:
        """
        Validate StarDict-specific options.

        Optional options:
            compress: Whether to gzip the .dict file (default: True).
            same_type_sequence: Data format sequence (default: 'h').
        """
        # No required options for StarDict
        same_type_sequence = options.get("same_type_sequence", "h")
        if same_type_sequence not in ("h", "m", "x", "g"):
            raise ValueError(f"Invalid same_type_sequence: {same_type_sequence}")

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
        Export dictionary entries to StarDict format.

        Args:
            entries_file: Path to JSONL file with entries.
            entry_count: Number of entries.
            in_lang: Input language name.
            out_lang: Output language name.
            outdir: Output directory.
            title: Dictionary title.
            **options: Additional options:
                - compress: Gzip the .dict file (default: True).
                - same_type_sequence: Data format (default: 'h' for HTML).

        Returns:
            Path to the .ifo file (main metadata file).
        """
        compress = options.get("compress", True)
        same_type_sequence = options.get("same_type_sequence", "h")

        # Create dictionary name (filename base)
        dict_name = f"{in_lang}-{out_lang}"
        safe_name = self._slugify(dict_name)

        # Create output directory for StarDict files
        dict_dir = outdir / safe_name
        dict_dir.mkdir(parents=True, exist_ok=True)

        # File paths
        ifo_path = dict_dir / f"{safe_name}.ifo"
        idx_path = dict_dir / f"{safe_name}.idx"
        dict_path = dict_dir / f"{safe_name}.dict"

        # Process entries and build StarDict files
        word_count, index_size = self._build_dictionary_files(
            entries_file=entries_file,
            entry_count=entry_count,
            idx_path=idx_path,
            dict_path=dict_path,
            same_type_sequence=same_type_sequence,
        )

        # Compress dict file if requested
        if compress:
            compressed_path = Path(str(dict_path) + ".dz")
            self._compress_dict_file(dict_path, compressed_path)
            dict_path.unlink()  # Remove uncompressed file

        # Write .ifo metadata file
        self._write_ifo_file(
            ifo_path=ifo_path,
            title=title or f"{in_lang} → {out_lang} Dictionary",
            word_count=word_count,
            index_size=index_size,
            same_type_sequence=same_type_sequence,
        )

        self.announce_summary(in_lang, out_lang, word_count, ifo_path)
        return ifo_path

    def _slugify(self, value: str) -> str:
        """Return a filesystem-friendly slug."""
        return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()) or "dictionary"

    def _build_dictionary_files(
        self,
        entries_file: Path,
        entry_count: int,
        idx_path: Path,
        dict_path: Path,
        same_type_sequence: str,
    ) -> tuple[int, int]:
        """
        Build the .idx and .dict files from JSONL entries.

        Returns:
            Tuple of (word_count, index_file_size).
        """
        # Collect all entries first, sorting by word (case-sensitive)
        entries: list[tuple[str, str]] = []

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self._console,
            disable=not self._show_progress,
        ) as progress:
            # Read and parse entries
            read_task = progress.add_task("Reading entries...", total=entry_count)

            with entries_file.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line_content = raw_line.strip()
                    if not line_content:
                        continue

                    try:
                        entry = json.loads(line_content)
                    except json.JSONDecodeError:
                        continue

                    word = entry.get("word", "")
                    if not word or not isinstance(word, str):
                        continue

                    # Format the definition
                    definition = self._format_definition(entry, same_type_sequence)
                    if definition:
                        entries.append((word, definition))

                    progress.update(read_task, advance=1)

        # Sort entries by word (StarDict requires sorted index)
        entries.sort(key=lambda x: x[0].lower())

        # Build index and data files
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self._console,
            disable=not self._show_progress,
        ) as progress:
            write_task = progress.add_task("Writing dictionary...", total=len(entries))

            with (
                idx_path.open("wb") as idx_file,
                dict_path.open("wb") as dict_file,
            ):
                offset = 0

                for word, definition in entries:
                    # Write definition to .dict file
                    def_bytes = definition.encode("utf-8")
                    dict_file.write(def_bytes)

                    # Write index entry: word\0 + offset (4 bytes BE) + size (4 bytes BE)
                    word_bytes = word.encode("utf-8") + b"\x00"
                    idx_file.write(word_bytes)
                    idx_file.write(struct.pack(">I", offset))  # Big-endian unsigned int
                    idx_file.write(struct.pack(">I", len(def_bytes)))

                    offset += len(def_bytes)
                    progress.update(write_task, advance=1)

        # Get index file size
        index_size = idx_path.stat().st_size

        return len(entries), index_size

    def _format_definition(self, entry: dict[str, Any], format_type: str = "h") -> str:
        """
        Format dictionary entry as a definition string.

        Args:
            entry: Dictionary entry with 'word', 'senses', etc.
            format_type: 'h' for HTML, 'm' for Pango markup, 'x' for XDXF, 'g' for plain.

        Returns:
            Formatted definition string.
        """
        senses = entry.get("senses", [])
        if not senses:
            return ""

        if format_type == "h":
            return self._format_html(entry)
        if format_type == "m":
            return self._format_pango(entry)
        return self._format_plain(entry)

    def _format_html(self, entry: dict[str, Any]) -> str:  # noqa: C901, PLR0912
        """Format entry as HTML."""
        parts: list[str] = []
        senses = entry.get("senses", [])

        # Add part of speech if available
        pos = entry.get("pos", "")
        if pos:
            parts.append(f'<i style="color: #666;">{self._escape_html(pos)}</i><br>')

        # Add numbered senses
        if len(senses) == 1:
            self._format_single_sense_html(senses[0], parts)
        else:
            self._format_multiple_senses_html(senses, parts)

        return "".join(parts)

    def _format_single_sense_html(self, sense: dict[str, Any], parts: list[str]) -> None:
        """Format a single sense entry as HTML."""
        glosses = sense.get("glosses", sense.get("raw_glosses", []))
        if isinstance(glosses, str):
            glosses = [glosses]
        if glosses:
            parts.append(self._escape_html("; ".join(glosses)))

        # Add examples
        examples = sense.get("examples", [])
        if examples:
            parts.append("<br><small>")
            self._format_examples_html(examples[:3], parts)
            parts.append("</small>")

    def _format_multiple_senses_html(self, senses: list[dict[str, Any]], parts: list[str]) -> None:
        """Format multiple senses as an ordered HTML list."""
        parts.append("<ol>")
        for sense in senses:
            glosses = sense.get("glosses", sense.get("raw_glosses", []))
            if isinstance(glosses, str):
                glosses = [glosses]
            if not glosses:
                continue

            parts.append(f"<li>{self._escape_html('; '.join(glosses))}")

            # Add examples
            examples = sense.get("examples", [])
            if examples:
                parts.append("<br><small>")
                self._format_examples_html(examples[:2], parts)
                parts.append("</small>")

            parts.append("</li>")
        parts.append("</ol>")

    def _format_examples_html(self, examples: list[Any], parts: list[str]) -> None:
        """Format example sentences as HTML."""
        for example in examples:
            if isinstance(example, dict):
                text = example.get("text", "")
                if text:
                    parts.append(f'<i>"{self._escape_html(text)}"</i><br>')
            elif isinstance(example, str):
                parts.append(f'<i>"{self._escape_html(example)}"</i><br>')

    def _format_pango(self, entry: dict[str, Any]) -> str:
        """Format entry as Pango markup (similar to HTML subset)."""
        # Pango markup is similar to HTML, so we can reuse HTML formatting
        # with slight adjustments
        return self._format_html(entry)

    def _format_plain(self, entry: dict[str, Any]) -> str:  # noqa: C901
        """Format entry as plain text."""
        parts: list[str] = []
        senses = entry.get("senses", [])

        pos = entry.get("pos", "")
        if pos:
            parts.append(f"({pos})")

        for i, sense in enumerate(senses, 1):
            glosses = sense.get("glosses", sense.get("raw_glosses", []))
            if isinstance(glosses, str):
                glosses = [glosses]
            if not glosses:
                continue

            if len(senses) > 1:
                parts.append(f"{i}. {'; '.join(glosses)}")
            else:
                parts.append("; ".join(glosses))

            self._format_examples_plain(sense.get("examples", [])[:2], parts)

        return "\n".join(parts)

    def _format_examples_plain(self, examples: list[Any], parts: list[str]) -> None:
        """Format example sentences as plain text."""
        for example in examples:
            if isinstance(example, dict):
                text = example.get("text", "")
                if text:
                    parts.append(f'   "{text}"')
            elif isinstance(example, str):
                parts.append(f'   "{example}"')

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _compress_dict_file(self, dict_path: Path, compressed_path: Path) -> None:
        """
        Compress .dict file using dictzip-compatible gzip.

        Note: True dictzip format supports random access, but standard gzip
        works for most StarDict readers. For full dictzip support, consider
        using the dictzip tool.
        """
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=self._console,
            disable=not self._show_progress,
        ) as progress:
            progress.add_task("Compressing dictionary...", total=None)

            with (
                dict_path.open("rb") as f_in,
                gzip.open(compressed_path, "wb", compresslevel=9) as f_out,
            ):
                # Read in chunks to handle large files
                while chunk := f_in.read(1024 * 1024):
                    f_out.write(chunk)

    def _write_ifo_file(
        self,
        ifo_path: Path,
        title: str,
        word_count: int,
        index_size: int,
        same_type_sequence: str,
    ) -> None:
        """
        Write the .ifo metadata file.

        The .ifo file contains dictionary metadata in a simple key=value format.
        """
        ifo_content = [
            "StarDict's dict ifo file",
            "version=2.4.2",
            f"wordcount={word_count}",
            f"idxfilesize={index_size}",
            f"bookname={title}",
            f"sametypesequence={same_type_sequence}",
            f"date={datetime.now().strftime('%Y.%m.%d')}",
            "author=dictforge",
            "description=Generated by dictforge",
        ]

        with ifo_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(ifo_content) + "\n")
