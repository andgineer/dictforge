from unittest.mock import MagicMock

import pytest
from rich.console import Console

from dictforge.progress_bar import (
    _BaseProgressCapture,
    _DatabaseProgressCapture,
    _KindleProgressCapture,
)


@pytest.fixture
def mock_console() -> Console:
    """Create a mock console for testing."""
    return MagicMock(spec=Console)


class TestBaseProgressCaptureHandleLine:
    """Test handle_line() in _BaseProgressCapture."""

    def test_handle_line_with_non_empty_line(self, mock_console: Console) -> None:
        capture = _BaseProgressCapture(
            console=mock_console,
            enabled=False,
            description="Test",
            unit="items",
        )
        capture.handle_line("test warning message")
        assert capture.warnings == ["test warning message"]

    def test_handle_line_with_empty_line(self, mock_console: Console) -> None:
        capture = _BaseProgressCapture(
            console=mock_console,
            enabled=False,
            description="Test",
            unit="items",
        )
        capture.handle_line("")
        assert capture.warnings == []

    def test_handle_line_with_multiple_lines(self, mock_console: Console) -> None:
        capture = _BaseProgressCapture(
            console=mock_console,
            enabled=False,
            description="Test",
            unit="items",
        )
        capture.handle_line("first warning")
        capture.handle_line("second warning")
        capture.handle_line("third warning")
        assert capture.warnings == ["first warning", "second warning", "third warning"]

    def test_handle_line_with_whitespace_only(self, mock_console: Console) -> None:
        capture = _BaseProgressCapture(
            console=mock_console,
            enabled=False,
            description="Test",
            unit="items",
        )
        capture.handle_line("   ")
        assert capture.warnings == ["   "]


class TestDatabaseProgressCaptureHandleLine:
    """Test handle_line() in _DatabaseProgressCapture."""

    def test_handle_line_with_inflections_to_add(self, mock_console: Console) -> None:
        capture = _DatabaseProgressCapture(console=mock_console, enabled=False)
        capture.handle_line("150 inflections to add manually")
        assert capture._total_hint == 150
        assert capture._description == "Adding inflections"
        assert capture.warnings == []

    def test_handle_line_with_digit_line(self, mock_console: Console) -> None:
        capture = _DatabaseProgressCapture(console=mock_console, enabled=False)
        capture.handle_line("42")
        assert capture._current == 42
        assert capture.warnings == []

    def test_handle_line_with_linking_inflections(self, mock_console: Console) -> None:
        capture = _DatabaseProgressCapture(console=mock_console, enabled=False)
        capture.handle_line("some relations with 3 elements")
        assert capture._description == "Linking inflections"
        assert capture.warnings == []

    def test_handle_line_with_unknown_line(self, mock_console: Console) -> None:
        capture = _DatabaseProgressCapture(console=mock_console, enabled=False)
        capture.handle_line("unknown message")
        assert capture.warnings == ["unknown message"]

    def test_handle_line_with_empty_line(self, mock_console: Console) -> None:
        capture = _DatabaseProgressCapture(console=mock_console, enabled=False)
        capture.handle_line("")
        assert capture.warnings == []
        assert capture._current == 0

    def test_handle_line_with_invalid_inflections_line(self, mock_console: Console) -> None:
        capture = _DatabaseProgressCapture(console=mock_console, enabled=False)
        original_total = capture._total_hint
        capture.handle_line("invalid inflections to add manually")
        assert capture._total_hint == original_total
        assert capture.warnings == []

    def test_handle_line_with_multiple_digit_lines(self, mock_console: Console) -> None:
        capture = _DatabaseProgressCapture(console=mock_console, enabled=False)
        capture.handle_line("10")
        assert capture._current == 10
        capture.handle_line("20")
        assert capture._current == 20
        capture.handle_line("25")
        assert capture._current == 25


class TestKindleProgressCaptureHandleLine:
    """Test handle_line() in _KindleProgressCapture."""

    def test_handle_line_with_getting_base_forms(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("Getting base forms")
        assert capture._description == "Loading base forms"
        assert capture.warnings == []

    def test_handle_line_with_iterating_base_forms(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("Iterating through base forms")
        assert capture._description == "Processing base forms"
        assert capture.warnings == []

    def test_handle_line_with_words_line(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("500 words")
        assert capture._total_hint == 500
        assert capture._current == 500
        assert capture.warnings == []

    def test_handle_line_with_words_line_with_existing_base_forms(
        self, mock_console: Console
    ) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.base_forms = 1000
        capture.handle_line("500 words")
        assert capture._total_hint == 1000
        assert capture._current == 500
        assert capture.warnings == []

    def test_handle_line_with_words_line_with_existing_total_hint(
        self, mock_console: Console
    ) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=2000,
        )
        capture.handle_line("500 words")
        assert capture._total_hint == 2000
        assert capture._current == 500
        assert capture.warnings == []

    def test_handle_line_with_creating_dictionary(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("Creating dictionary")
        assert capture._description == "Compiling dictionary"
        assert capture.warnings == []

    def test_handle_line_with_writing_dictionary(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("Writing dictionary")
        assert capture._description == "Writing MOBI file"
        assert capture.warnings == []

    def test_handle_line_with_base_forms_line(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("750 base forms")
        assert capture.base_forms == 750
        assert capture._total_hint == 750
        assert capture._current == 750
        assert capture.warnings == []

    def test_handle_line_with_inflections_line(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("1200 inflections")
        assert capture.inflections == 1200
        assert capture.warnings == []

    def test_handle_line_with_invalid_inflections_line(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("invalid inflections")
        assert capture.inflections is None
        assert capture.warnings == []

    def test_handle_line_with_invalid_words_line(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        original_total = capture._total_hint
        original_current = capture._current
        capture.handle_line("invalid words")
        assert capture._total_hint == original_total
        assert capture._current == original_current
        assert capture.warnings == []

    def test_handle_line_with_invalid_base_forms_line(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("invalid base forms")
        assert capture.base_forms is None
        assert capture.warnings == []

    def test_handle_line_with_unknown_line(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("unknown message")
        assert capture.warnings == ["unknown message"]

    def test_handle_line_with_empty_line(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("")
        assert capture.warnings == []
        assert capture._current == 0

    def test_handle_line_with_multiple_words_lines(self, mock_console: Console) -> None:
        capture = _KindleProgressCapture(
            console=mock_console,
            enabled=False,
            total_hint=None,
        )
        capture.handle_line("100 words")
        assert capture._current == 100
        capture.handle_line("200 words")
        assert capture._current == 200
        capture.handle_line("300 words")
        assert capture._current == 300
