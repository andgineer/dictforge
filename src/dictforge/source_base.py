from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from rich.console import Console

GlossValue = list[str] | str


class SenseDict(TypedDict, total=False):
    """Definition text that explains what the word means in plain language.

    ``glosses`` contains the polished strings shown to the user, for example
    ``"greeting"`` or ``"domestic cat"``.  ``raw_glosses`` keeps the same
    definitions before any clean-up, so we still accept entries that only have a
    rough version (e.g. with markup or punctuation fragments).
    """

    glosses: GlossValue
    raw_glosses: GlossValue


class EntryDict(TypedDict, total=False):
    """Dictionary entry that groups all sense definitions for a single headword.

    ``senses`` is the ordered list of meanings (each a ``SenseDict``). The entry
    typically includes other keys such as ``word`` (the lemma being defined) and
    translation data, but ``entry_has_content`` only checks this ``senses`` list
    when deciding whether the entry contains useful text.
    """

    senses: list[SenseDict]


class DictionarySource:
    def __init__(self) -> None:
        self._filter_stats: dict[str, dict[str, int]] = {}
        self._logged_filter_languages: set[str] = set()

    def ensure_download_dirs(self, force: bool = False) -> None:  # pragma: no cover - base contract
        """Make sure the top-level cache directory hierarchy exists."""
        raise NotImplementedError

    def get_entries(
        self,
        in_lang: str,
        out_lang: str,
    ) -> tuple[Path, int]:  # pragma: no cover - base contract
        """Entries filtered for the language pair."""
        raise NotImplementedError

    @staticmethod
    def entry_has_content(entry: EntryDict | Any) -> bool:  # noqa: C901
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

    def record_filter_stats(self, language: str, meta: dict[str, Any]) -> None:
        """Cache filtered entry statistics for ``language``."""
        stats = {
            key: int(meta[key])
            for key in ("count", "matched_entries", "skipped_empty")
            if key in meta and isinstance(meta[key], (int, float))
        }
        if stats:
            self._filter_stats[language] = stats

    def get_filter_stats(self, language: str) -> dict[str, int] | None:
        """Return cached filter statistics for ``language`` if available."""
        return self._filter_stats.get(language)

    def log_filter_stats(self, language: str, console: Console) -> None:
        """Log a one-time summary of filtered entries for ``language``."""
        language_key = language.lower()
        if language_key in self._logged_filter_languages:
            return

        stats = self.get_filter_stats(language) or {}
        count = stats.get("count")
        matched = stats.get("matched_entries", count)
        skipped = stats.get("skipped_empty")
        if count is None:
            return

        skipped_label = f", skipped {skipped:,} empty" if skipped is not None else ""
        matched_label = f" of {matched:,} entries" if matched is not None else ""
        console.print(
            f"[dictforge] {language}: kept {count:,}{matched_label}{skipped_label}",
            style="cyan",
        )
        self._logged_filter_languages.add(language_key)
