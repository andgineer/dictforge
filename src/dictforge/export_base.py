"""Abstract base class for dictionary export formats."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from rich.console import Console


class ExportFormat(ABC):
    """
    Abstract base class for dictionary export formats.

    Each format implementation is responsible for converting dictionary entries
    (in JSONL format) to a specific output format (MOBI, StarDict, etc.).
    """

    def __init__(self, console: Console | None = None, show_progress: bool = True):
        """
        Initialize the export format.

        Args:
            console: Rich console for output. Creates a new one if not provided.
            show_progress: Whether to show progress indicators.
        """
        self._console = console or Console(stderr=True)
        self._show_progress = show_progress

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the short name of the format (e.g., 'mobi', 'stardict')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of the format."""
        ...

    @abstractmethod
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
        Export dictionary entries to the target format.

        Args:
            entries_file: Path to JSONL file containing dictionary entries.
            entry_count: Number of entries in the file.
            in_lang: Input language name (e.g., 'Serbian').
            out_lang: Output language name (e.g., 'English').
            outdir: Directory where output files should be written.
            title: Dictionary title.
            **options: Format-specific options.

        Returns:
            Path to the main output file.

        Raises:
            ExportError: If export fails.
        """
        ...

    @abstractmethod
    def validate_options(self, **options: Any) -> None:
        """
        Validate format-specific options before export.

        Args:
            **options: Options to validate.

        Raises:
            ValueError: If options are invalid.
        """
        ...

    def announce_summary(
        self,
        in_lang: str,
        out_lang: str,
        entry_count: int,
        output_path: Path,
    ) -> None:
        """
        Print a post-export summary.

        Args:
            in_lang: Input language name.
            out_lang: Output language name.
            entry_count: Number of entries exported.
            output_path: Path to the output file.
        """
        self._console.print(
            f"[dictforge] {in_lang} → {out_lang}: {entry_count:,} entries → {output_path}",
            style="green",
        )


class ExportError(Exception):
    """Raised when an export operation fails."""
