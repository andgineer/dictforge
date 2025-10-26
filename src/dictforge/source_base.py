from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DictionarySource(Protocol):
    """Protocol for dictionary content providers."""

    def ensure_download(self, force: bool = False) -> None:  # pragma: no cover - protocol
        ...

    def get_entries(
        self,
        in_lang: str,
        out_lang: str,
    ) -> tuple[Path, int]:  # pragma: no cover - protocol
        ...
