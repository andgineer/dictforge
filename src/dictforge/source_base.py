from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


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


def entry_has_content(entry: dict[str, Any] | Any) -> bool:  # noqa: C901
    """Return ``True`` when ``entry`` includes a non-empty gloss or raw_gloss value."""
    if not isinstance(entry, dict):
        return False

    senses = entry.get("senses")
    if not isinstance(senses, list) or not senses:
        return False

    def _iter_values(values: Any) -> list[str]:
        if isinstance(values, str):
            return [values]
        if isinstance(values, list):
            return [value for value in values if isinstance(value, str)]
        return []

    for sense in senses:
        if not isinstance(sense, dict):
            continue
        for key in ("glosses", "raw_glosses"):
            for value in _iter_values(sense.get(key)):
                if value.strip():
                    return True
    return False
