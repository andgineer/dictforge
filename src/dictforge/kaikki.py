from __future__ import annotations

import gzip
import json
import re
import shutil
from html.parser import HTMLParser
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

RAW_DUMP_URL = "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz"
RAW_CACHE_DIR = "raw"
FILTERED_CACHE_DIR = "filtered"
META_SUFFIX = ".meta.json"
LANGUAGE_CACHE_DIR = "languages"
TRANSLATION_CACHE_DIR = "translations"
LANGUAGE_DUMP_URL = "https://kaikki.org/dictionary/{lang}/kaikki.org-dictionary-{slug}.jsonl"
EXCERPT_MAX_CHARS = 200
ELLIPSIS = "..."
_LANGUAGE_FALLBACKS = {
    "Croatian": "Serbo-Croatian",
    "Serbian": "Serbo-Croatian",
}


class KaikkiDownloadError(RuntimeError):
    """Raised when Kaikki resources cannot be downloaded."""


class KaikkiParseError(RuntimeError):
    """Raised when the Kaikki JSON dump cannot be parsed."""

    def __init__(self, path: str | Path | None, exc: JSONDecodeError):
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
            text = data.strip()
            if text:
                self.chunks.append(text)

    def _load_excerpt(self, limit: int = 3) -> list[str]:
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
            if len(line) <= EXCERPT_MAX_CHARS
            else f"{line[: EXCERPT_MAX_CHARS - len(ELLIPSIS)]}{ELLIPSIS}"
            for line in excerpt
        ]


class KaikkiClient:
    """Helper responsible for fetching and preparing Kaikki datasets."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        session: requests.Session | None = None,
        reset_cache: bool = False,
    ) -> None:
        self.cache_dir = cache_dir
        self.session = session or requests.Session()
        self._translation_cache: dict[tuple[str, str], dict[str, list[str]]] = {}
        if reset_cache:
            self._reset_cache()

    # Public API -----------------------------------------------------
    def ensure_language_dataset(self, language: str) -> Path:
        language = self._canonical_language(language)
        lang_dir = self.cache_dir / LANGUAGE_CACHE_DIR
        lang_dir.mkdir(parents=True, exist_ok=True)
        slug = self._kaikki_slug(language)
        filename = f"kaikki.org-dictionary-{slug}.jsonl"
        target = lang_dir / filename
        if target.exists():
            return target

        url = LANGUAGE_DUMP_URL.format(lang=self._quote(language), slug=slug)
        try:
            response = self.session.get(url, stream=True, timeout=180)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise KaikkiDownloadError(
                f"Failed to download Kaikki dump for {language} from {url}: {exc}",
            ) from exc

        try:
            with target.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    if not chunk:
                        continue
                    fh.write(chunk)
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise KaikkiDownloadError(f"Failed to write file {target}: {exc}") from exc

        return target

    def ensure_filtered_language(self, language: str) -> tuple[Path, int]:  # noqa C901,PLR0912
        language = self._canonical_language(language)
        raw_dump = self.ensure_raw_dump()

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
            if meta.get("source_mtime") == raw_mtime and meta.get("count"):
                return filtered_path, int(meta["count"])

        temp_path = filtered_path.with_suffix(".tmp")
        count = 0
        try:
            with (
                gzip.open(raw_dump, "rt", encoding="utf-8") as src,
                temp_path.open(
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

                    entry_language = entry.get("language") or entry.get("lang")
                    if entry_language == language:
                        dst.write(line if line.endswith("\n") else f"{line}\n")
                        count += 1
        except OSError as exc:
            raise KaikkiDownloadError(
                f"Failed to read Kaikki raw dump from {raw_dump}: {exc}",
            ) from exc

        if count == 0:
            temp_path.unlink(missing_ok=True)
            source_dump = self.ensure_language_dataset(language)
            try:
                with (
                    source_dump.open("r", encoding="utf-8") as src,
                    temp_path.open(
                        "w",
                        encoding="utf-8",
                    ) as dst,
                ):
                    for line in src:
                        if not line.strip():
                            continue
                        dst.write(line if line.endswith("\n") else f"{line}\n")
                        count += 1
            except OSError as exc:
                temp_path.unlink(missing_ok=True)
                raise KaikkiDownloadError(
                    f"Failed to read Kaikki dump for {language}: {exc}",
                ) from exc
            if count == 0:
                temp_path.unlink(missing_ok=True)
                raise KaikkiDownloadError(
                    f"No entries found for language '{language}' in Kaikki dumps.",
                )

        temp_path.rename(filtered_path)
        meta_path.write_text(
            json.dumps({"language": language, "count": count, "source_mtime": raw_mtime}),
            encoding="utf-8",
        )

        return filtered_path, count

    def ensure_translated_glosses(
        self,
        base_path: Path,
        source_lang: str,
        target_lang: str,
    ) -> Path:
        translation_map = self.load_translation_map(source_lang, target_lang)

        source_lang = self._canonical_language(source_lang)
        target_lang = self._canonical_language(target_lang)
        suffix = f"__to_{self._kaikki_slug(target_lang)}.jsonl"
        localized_path = base_path.with_name(base_path.stem + suffix)

        if localized_path.exists() and localized_path.stat().st_mtime >= base_path.stat().st_mtime:
            return localized_path

        try:
            with (
                base_path.open("r", encoding="utf-8") as src,
                localized_path.open(
                    "w",
                    encoding="utf-8",
                ) as dst,
            ):
                for raw_line in src:
                    if not raw_line.strip():
                        continue
                    entry = json.loads(raw_line)
                    self.apply_translation_glosses(entry, translation_map)
                    dst.write(json.dumps(entry, ensure_ascii=False))
                    dst.write("\n")
        except json.JSONDecodeError as exc:
            raise KaikkiParseError(base_path, exc) from exc
        except OSError as exc:
            raise KaikkiDownloadError(f"Failed to enrich Kaikki glosses: {exc}") from exc

        return localized_path

    def load_translation_map(self, source_lang: str, target_lang: str) -> dict[str, list[str]]:
        source_lang = self._canonical_language(source_lang)
        target_lang = self._canonical_language(target_lang)
        key = (source_lang.lower(), target_lang.lower())
        cached = self._translation_cache.get(key)
        if cached is not None:
            return cached

        cache_dir = self.cache_dir / TRANSLATION_CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)

        source_slug = self._kaikki_slug(source_lang)
        target_slug = self._kaikki_slug(target_lang)
        cache_path = cache_dir / f"{source_slug}_to_{target_slug}.json"

        source_dump = self.ensure_language_dataset(source_lang)
        if cache_path.exists() and cache_path.stat().st_mtime >= source_dump.stat().st_mtime:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            self._translation_cache[key] = {k: list(v) for k, v in data.items()}
            return self._translation_cache[key]

        mapping: dict[str, list[str]] = {}
        try:
            with source_dump.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    headword = entry.get("word")
                    if not isinstance(headword, str):
                        continue
                    translations = {
                        tr["word"]
                        for sense in entry.get("senses", [])
                        if isinstance(sense, dict)
                        for tr in sense.get("translations") or []
                        if isinstance(tr, dict)
                        and tr.get("lang") == target_lang
                        and isinstance(tr.get("word"), str)
                    }
                    if translations:
                        mapping[headword.lower()] = sorted(translations)
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

    def ensure_raw_dump(self) -> Path:
        raw_dir = self.cache_dir / RAW_CACHE_DIR
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_target = raw_dir / Path(RAW_DUMP_URL).name
        if raw_target.exists():
            return raw_target

        try:
            response = self.session.get(RAW_DUMP_URL, stream=True, timeout=300)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise KaikkiDownloadError(
                f"Failed to download Kaikki raw dump from {RAW_DUMP_URL}: {exc}",
            ) from exc

        try:
            with raw_target.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    if chunk:
                        fh.write(chunk)
        except OSError as exc:
            raise KaikkiDownloadError(
                f"Failed to write Kaikki raw dump to {raw_target}: {exc}",
            ) from exc

        return raw_target

    def close(self) -> None:
        self.session.close()

    # Static helpers --------------------------------------------------
    @staticmethod
    def apply_translation_glosses(  # noqa: C901
        entry: dict[str, Any],
        translation_map: dict[str, list[str]],
    ) -> None:
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

    @staticmethod
    def _kaikki_slug(language: str) -> str:
        return language.replace(" ", "").replace("-", "").replace("'", "")

    @staticmethod
    def _quote(language: str) -> str:
        return quote(language, safe="-")

    @staticmethod
    def _slugify(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()) or "language"

    def _reset_cache(self) -> None:
        for name in (
            RAW_CACHE_DIR,
            FILTERED_CACHE_DIR,
            LANGUAGE_CACHE_DIR,
            TRANSLATION_CACHE_DIR,
        ):
            shutil.rmtree(self.cache_dir / name, ignore_errors=True)

    @staticmethod
    def _canonical_language(language: str) -> str:
        return _LANGUAGE_FALLBACKS.get(language, language)
