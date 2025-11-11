import gzip
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from html.parser import HTMLParser
from json import JSONDecodeError
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import quote

import requests

from .kaikki_utils import lang_meta
from .source_base import DictionarySource

RAW_DUMP_URL = "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz"
RAW_CACHE_DIR = "raw"
FILTERED_CACHE_DIR = "filtered"
META_SUFFIX = ".meta.json"
LANGUAGE_CACHE_DIR = "languages"
TRANSLATION_CACHE_DIR = "translations"
LANGUAGE_DUMP_URL = "https://kaikki.org/dictionary/{lang}/kaikki.org-dictionary-{slug}.jsonl"
RESPONSE_EXCERPT_MAX_LENGTH = 200
ELLIPSE = "..."

ProgressAdvance = Callable[[int], None]
ProgressFactory = Callable[..., AbstractContextManager[ProgressAdvance]]


GlossText = list[str] | str


class KaikkiSense(TypedDict, total=False):
    """Definition text that explains what the word means in plain language.

    ``glosses`` contains the polished strings shown to the user, for example
    ``"greeting"`` or ``"domestic cat"``.  ``raw_glosses`` keeps the same
    definitions before any clean-up, so we still accept entries that only have a
    rough version (e.g. with markup or punctuation fragments).
    """

    glosses: GlossText
    raw_glosses: GlossText


class KaikkiEntry(TypedDict, total=False):
    """Dictionary entry that groups all sense definitions for a single headword.

    ``senses`` is the ordered list of meanings (each a ``KaikkiSense``).
    ``word`` stores the lemma being defined.
    """

    word: str
    senses: list[KaikkiSense]


class KaikkiDownloadError(RuntimeError):
    """Raised when Kaikki resources cannot be downloaded."""


class KaikkiParseError(RuntimeError):
    """Raised when the Kaikki JSON dump cannot be parsed."""

    def __init__(self, path: str | Path | None, exc: JSONDecodeError):
        """Capture location/context for JSON parsing failures emitted by Kaikki."""
        self.path = Path(path) if path else None
        location = f"line {exc.lineno}, column {exc.colno}" if exc.lineno else f"position {exc.pos}"
        path_hint = str(self.path) if self.path else "<unknown Kaikki file>"
        message = f"Failed to parse Kaikki JSON at {path_hint} ({location}): {exc.msg}."
        super().__init__(message)
        self.lineno = exc.lineno
        self.colno = exc.colno
        self.original_error = exc
        doc_snippet = getattr(exc, "doc", "").strip()
        self.excerpt = self._load_excerpt() if self.path else ([doc_snippet] if doc_snippet else [])

    class _HTMLStripper(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.chunks: list[str] = []

        def handle_data(self, data: str) -> None:  # noqa: D401
            """Collect plain-text chunks while stripping any HTML structure."""
            text = data.strip()
            if text:
                self.chunks.append(text)

    def _load_excerpt(self, limit: int = 3) -> list[str]:
        """Return the first few lines from the problematic Kaikki file for context."""
        if not self.path or not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read(4096)
        except OSError:
            return []

        raw_lines = [line.strip() for line in content.splitlines() if line.strip()]
        if raw_lines and raw_lines[0].startswith("<"):
            stripper = self._HTMLStripper()
            stripper.feed(content)
            text_lines = stripper.chunks
        else:
            text_lines = raw_lines

        excerpt = text_lines[:limit]
        return [
            line
            if len(line) <= RESPONSE_EXCERPT_MAX_LENGTH
            else f"{line[: RESPONSE_EXCERPT_MAX_LENGTH - len(ELLIPSE)]}{ELLIPSE}"
            for line in excerpt
        ]


class KaikkiSource(DictionarySource):
    """Access and prepare Kaikki (Wiktextract) datasets."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        session: requests.Session,
        progress_factory: ProgressFactory,
    ) -> None:
        """Initialise a Kaikki source with shared cache/session/progress helpers."""
        super().__init__()
        self.cache_dir = cache_dir
        self.session = session
        self._progress_factory = progress_factory
        self._translation_cache: dict[tuple[str, str], dict[str, list[str]]] = {}

    @property
    def translation_cache(self) -> dict[tuple[str, str], dict[str, list[str]]]:
        """Expose the in-memory translation cache (primarily for tests)."""
        return self._translation_cache

    def ensure_download_dirs(self, force: bool = False) -> None:  # noqa: ARG002
        """Make sure the top-level cache directory hierarchy exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def entry_has_content(self, entry: Any) -> bool:  # noqa: C901
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

    def get_entries(self, in_lang: str, out_lang: str) -> tuple[Path, int]:
        """Entries filtered for the language pair."""
        language_file, count = self._ensure_filtered_language(in_lang)
        prepared = self._ensure_translated_glosses(language_file, out_lang)
        return prepared, count

    def ensure_language_dataset(self, language: str) -> Path:
        """External helper used by tests to warm the per-language Kaikki dump."""
        return self._ensure_language_dataset(language)

    def _slugify(self, value: str) -> str:
        """Collapse a language name to a Kaikki/filename friendly slug."""
        return value.replace(" ", "").replace("-", "").replace("'", "")

    def _kaikki_slug(self, language: str) -> str:
        """Mirror Kaikki's slug formatting (spaces/dashes removed)."""
        return self._slugify(language)

    def _ensure_language_dataset(self, language: str) -> Path:
        """Download (or reuse) the Kaikki JSONL dump dedicated to ``language``."""
        lang_dir = self.cache_dir / LANGUAGE_CACHE_DIR
        lang_dir.mkdir(parents=True, exist_ok=True)
        slug = self._kaikki_slug(language)
        filename = f"kaikki.org-dictionary-{slug}.jsonl"
        target = lang_dir / filename
        if target.exists():
            return target

        url = LANGUAGE_DUMP_URL.format(lang=quote(language, safe="-"), slug=slug)
        try:
            response = self.session.get(url, stream=True, timeout=180)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise KaikkiDownloadError(
                f"Failed to download Kaikki dump for {language} from {url}: {exc}",
            ) from exc

        headers = getattr(response, "headers", {}) or {}
        content_length = headers.get("Content-Length")
        try:
            total = int(content_length) if content_length else None
        except (TypeError, ValueError):  # pragma: no cover - defensive
            total = None

        with (
            self._progress_factory(
                description=f"Downloading {language}",
                total=total,
                unit="B",
            ) as advance,
            target.open("wb") as fh,
        ):
            for chunk in response.iter_content(chunk_size=1 << 20):
                if not chunk:
                    continue
                fh.write(chunk)
                advance(len(chunk))

        return target

    def _ensure_raw_dump(self) -> Path:
        """Retrieve the monolithic Kaikki dump used for per-language filtering."""
        raw_dir = self.cache_dir / RAW_CACHE_DIR
        raw_dir.mkdir(parents=True, exist_ok=True)
        target = raw_dir / Path(RAW_DUMP_URL).name
        if target.exists():
            return target

        try:
            response = self.session.get(RAW_DUMP_URL, stream=True, timeout=120)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise KaikkiDownloadError(
                f"Failed to download Kaikki raw dump from {RAW_DUMP_URL}: {exc}",
            ) from exc

        headers = getattr(response, "headers", {}) or {}
        content_length = headers.get("Content-Length")
        try:
            total = int(content_length) if content_length else None
        except (TypeError, ValueError):  # pragma: no cover - defensive
            total = None

        with (
            self._progress_factory(
                description="Downloading Kaikki raw dump",
                total=total,
                unit="B",
            ) as advance,
            target.open("wb") as fh,
        ):
            for chunk in response.iter_content(chunk_size=1 << 20):
                if not chunk:
                    continue
                fh.write(chunk)
                advance(len(chunk))

        return target

    def _ensure_filtered_language(self, language: str) -> tuple[Path, int]:  # noqa: C901
        """Filter the raw dump down to entries matching ``language`` and cache metadata."""
        raw_dump = self._ensure_raw_dump()

        filtered_dir = self.cache_dir / FILTERED_CACHE_DIR
        filtered_dir.mkdir(parents=True, exist_ok=True)

        slug = self._slugify(language)
        filtered_path = filtered_dir / f"{slug}.jsonl"
        meta_path = filtered_dir / f"{slug}{META_SUFFIX}"
        raw_mtime = int(raw_dump.stat().st_mtime)

        if filtered_path.exists() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {}
            has_stats = "matched_entries" in meta and "skipped_empty" in meta
            if meta.get("source_mtime") == raw_mtime and "count" in meta and has_stats:
                self.record_filter_stats(language, meta)
                return filtered_path, int(meta["count"])

        kept = 0
        skipped_empty = 0
        matched = 0
        try:
            with (
                self._progress_factory(
                    description=f"Filtering {language}",
                ) as advance,
                gzip.open(raw_dump, "rt", encoding="utf-8") as src,
                filtered_path.open(
                    "w",
                    encoding="utf-8",
                ) as dst,
            ):
                for line in src:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise KaikkiParseError(None, exc) from exc

                    advance(1)

                    entry_language = entry.get("language") or entry.get("lang")
                    if entry_language == language:
                        matched += 1
                        if self.entry_has_content(entry):
                            dst.write(line if line.endswith("\n") else f"{line}\n")
                            kept += 1
                        else:
                            skipped_empty += 1
        except OSError as exc:
            raise KaikkiDownloadError(
                f"Failed to read Kaikki raw dump from {raw_dump}: {exc}",
            ) from exc

        if kept == 0:
            filtered_path.unlink(missing_ok=True)
            raise KaikkiDownloadError(
                f"No entries found for language '{language}' in Kaikki raw dump.",
            )

        meta = {
            "language": language,
            "count": kept,
            "matched_entries": matched,
            "skipped_empty": skipped_empty,
            "source_mtime": raw_mtime,
        }
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        self.record_filter_stats(language, meta)

        return filtered_path, kept

    def get_filter_stats(self, language: str) -> dict[str, int] | None:
        """Return cached filtering statistics for ``language`` when available."""
        stats = super().get_filter_stats(language)
        if stats:
            return stats

        meta_path = self.cache_dir / FILTERED_CACHE_DIR / f"{self._slugify(language)}{META_SUFFIX}"
        if not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        self.record_filter_stats(language, meta)
        return super().get_filter_stats(language)

    def _load_translation_map(self, source_lang: str, target_lang: str) -> dict[str, list[str]]:
        """Build or reuse a map from source words to translations in ``target_lang``."""
        key = (source_lang.lower(), target_lang.lower())
        cached = self._translation_cache.get(key)
        if cached is not None:
            return cached

        cache_dir = self.cache_dir / TRANSLATION_CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)

        source_slug = self._kaikki_slug(source_lang)
        target_slug = self._kaikki_slug(target_lang)
        cache_path = cache_dir / f"{source_slug}_to_{target_slug}.json"

        source_dump = self._ensure_language_dataset(source_lang)
        if cache_path.exists() and cache_path.stat().st_mtime >= source_dump.stat().st_mtime:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            self._translation_cache[key] = {k: list(v) for k, v in data.items()}
            return self._translation_cache[key]

        mapping: dict[str, list[str]] = {}
        try:
            with source_dump.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    translations = {
                        tr["word"]
                        for sense in entry.get("senses", [])
                        for tr in sense.get("translations") or []
                        if tr.get("lang") == target_lang and tr.get("word")
                    }
                    if translations:
                        mapping[entry["word"].lower()] = sorted(translations)
        except OSError as exc:
            raise KaikkiDownloadError(
                f"Failed to read Kaikki dump for {source_lang}: {exc}",
            ) from exc

        cache_path.write_text(
            json.dumps(mapping, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        self._translation_cache[key] = mapping
        return mapping

    def _apply_translation_glosses(  # noqa: C901
        self,
        entry: dict[str, Any],
        translation_map: dict[str, list[str]],
    ) -> None:
        """Mutate ``entry`` so glosses prefer translated variants when available."""
        senses = entry.get("senses") or []
        for sense in senses:
            translations: set[str] = set()
            for link in sense.get("links") or []:
                if not isinstance(link, (list, tuple)) or not link:
                    continue
                pivot = link[0]
                if isinstance(pivot, str):
                    translations.update(translation_map.get(pivot.lower(), []))
            if not translations:
                for gloss in sense.get("glosses") or []:
                    if not isinstance(gloss, str):
                        continue
                    candidate = gloss.lower()
                    if candidate in translation_map:
                        translations.update(translation_map[candidate])
                        continue
                    stripped = candidate.split(";", 1)[0].split("(", 1)[0].strip()
                    if stripped in translation_map:
                        translations.update(translation_map[stripped])
            if translations:
                ordered = sorted(set(translations))
                sense["glosses"] = ordered
                sense["raw_glosses"] = ordered

    def _ensure_translated_glosses(
        self,
        base_path: Path,
        out_lang: str,
    ) -> Path:
        """Re-write glosses for ``out_lang`` via English translations (the only Kaikki pivot)."""
        out_code, _ = lang_meta(out_lang)
        if out_code == "en":
            return base_path

        translation_map = self._load_translation_map("English", out_lang)
        localized = base_path.with_name(f"{base_path.stem}__to_{out_code}.jsonl")
        if localized.exists() and localized.stat().st_mtime >= base_path.stat().st_mtime:
            return localized
        with (
            base_path.open("r", encoding="utf-8") as src,
            localized.open("w", encoding="utf-8") as dst,
        ):
            for line in src:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._apply_translation_glosses(entry, translation_map)
                dst.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return localized
