from pathlib import Path
from typing import Any

from rich.console import Console


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

    def entry_has_content(self, entry: Any) -> bool:  # noqa: ARG002
        """Return ``True`` when ``entry`` should be kept in downstream merges."""
        return True

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
