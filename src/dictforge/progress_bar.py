import io
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

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


def _format_units(task: Task, unit: str) -> str:
    """Present rich-progress counts with human-friendly thousands separators."""
    completed = int(task.completed or 0)
    total = task.total
    label = unit if unit != "B" else "B"
    if total is None:
        return f"{completed:,} {label}"
    return f"{completed:,}/{int(total):,} {label}"


class _BaseProgressCapture(io.TextIOBase):
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
        super().__init__()
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

    def writable(self) -> bool:  # pragma: no cover - standard TextIO contract
        """Signal compatibility with file-like write operations."""
        return True

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

    @staticmethod
    def _extract_number_prefix(line: str, suffix: str) -> int | None:
        """Extract number from line prefix before given suffix, or None if invalid."""
        if not line.endswith(suffix):
            return None
        try:
            return int(line.split(" ", 1)[0])
        except ValueError:
            return None


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

        # Handle inflections to add - silently ignore if pattern matches but number is invalid
        if line.endswith("inflections to add manually"):
            total = self._extract_number_prefix(line, "inflections to add manually")
            if total is not None:
                self.set_description("Adding inflections")
                self.set_total(total)
            return

        if line.isdigit():
            self.advance_to(int(line))
            return

        if line.endswith("relations with 3 elements"):
            self.set_description("Linking inflections")
            return

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

    def _handle_description_update(self, line: str, exact_match: str, description: str) -> bool:
        """Update description if line exactly matches given string."""
        if line == exact_match:
            self.set_description(description)
            return True
        return False

    def _handle_words_progress(self, line: str) -> bool:
        """Handle lines ending with ' words' and update progress accordingly."""
        words = self._extract_number_prefix(line, " words")
        if words is None:
            return False
        if self._total_hint is None:
            self.set_total(self.base_forms if self.base_forms is not None else words)
        self.advance_to(words)
        return True

    def handle_line(self, line: str) -> None:  # noqa: C901,PLR0911
        """Derive progress milestones from Kindle Previewer console output."""
        if not line:
            return

        # Exact match descriptions
        if self._handle_description_update(line, "Getting base forms", "Loading base forms"):
            return
        if self._handle_description_update(line, "Creating dictionary", "Compiling dictionary"):
            return
        if self._handle_description_update(line, "Writing dictionary", "Writing MOBI file"):
            return

        # Prefix match descriptions
        if line.startswith("Iterating through base forms"):
            self.set_description("Processing base forms")
            return

        # Progress updates with numbers
        # Handle words - silently ignore if pattern matches but number is invalid
        if line.endswith(" words"):
            if self._handle_words_progress(line):
                return
            return

        # Handle base forms - silently ignore if pattern matches but number is invalid
        if line.endswith(" base forms"):
            base_forms = self._extract_number_prefix(line, " base forms")
            if base_forms is not None:
                self.base_forms = base_forms
                self.set_total(base_forms)
                self.advance_to(base_forms)
            return

        # Handle inflections - silently ignore if pattern matches but number is invalid
        if line.endswith(" inflections"):
            inflections = self._extract_number_prefix(line, " inflections")
            if inflections is not None:
                self.inflections = inflections
            return

        self.warnings.append(line)


ProgressAdvance = Callable[[int], None]


@contextmanager
def progress_bar(  # noqa: PLR0913
    *,
    console: Console,
    enabled: bool,
    description: str,
    total: int | None = None,
    unit: str = "entries",
    refresh_per_second: int = 4,
) -> Iterator[ProgressAdvance]:
    """Create a Rich progress context and yield a callback that advances it."""
    if not enabled:

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
        console=console,
        transient=False,
        refresh_per_second=refresh_per_second,
        expand=True,
    )
    with progress:
        task_id = progress.add_task(description, total=total)

        def advance(amount: int) -> None:
            progress.update(task_id, advance=amount)

        yield advance
