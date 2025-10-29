from __future__ import annotations

import io

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    Task,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
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
