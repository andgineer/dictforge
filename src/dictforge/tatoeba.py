from __future__ import annotations

import bz2
import json
import re
import shutil
import tarfile
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .translit import cyr_to_lat

TATOEBA_EXPORT_ROOT = "https://downloads.tatoeba.org/exports/per_language"
TATOEBA_LINKS_ROOT = "https://downloads.tatoeba.org/exports"
MAX_WORDS = 3
SENTENCE_FILES = (
    "sentences.tar.bz2",
    "sentences.csv.bz2",
    "sentences.tsv.bz2",
    "sentences.csv",
    "sentences.tsv",
)
LINK_FILES = (
    "links.tar.bz2",
    "links.csv.bz2",
    "links.tsv.bz2",
    "links.csv",
    "links.tsv",
)
SENTENCE_FIELDS_MIN = 3
LINK_FIELDS_MIN = 2


class TatoebaError(RuntimeError):
    """Generic integration failure for the Tatoeba source."""


@dataclass(frozen=True)
class _SentencePair:
    source: str
    target: str


class TatoebaExamples:
    """Download, cache, and expose aligned example pairs from Tatoeba."""

    _global_links_path: Path

    def __init__(
        self,
        source_lang: str,
        target_lang: str,
        cache_dir: Path,
        reset_cache: bool = False,
    ) -> None:
        self._source_langs = self._expand_language(source_lang)
        self._target_langs = self._expand_language(target_lang)
        self._root = cache_dir / "tatoeba"
        self._root.mkdir(parents=True, exist_ok=True)
        if reset_cache:
            shutil.rmtree(self._root, ignore_errors=True)
            self._root.mkdir(parents=True, exist_ok=True)

        key = self._cache_key(self._source_langs, self._target_langs)
        self._dataset_dir = self._root / key
        self._dataset_dir.mkdir(parents=True, exist_ok=True)
        self._download_dir = self._root / "downloads"
        self._download_dir.mkdir(parents=True, exist_ok=True)
        self._pairs_cache = self._dataset_dir / "pairs.json"

        self._pairs: dict[str, list[tuple[str, str]]] | None = None

    # Public API -----------------------------------------------------
    def vocabulary(self) -> set[str]:
        mappings = self._load_pairs()
        return set(mappings)

    def get_examples_for(self, word: str) -> list[tuple[str, str]]:
        if not word:
            return []
        mappings = self._load_pairs()
        key = self._normalise(word)
        examples = mappings.get(key, [])
        return list(examples)

    def get_gloss_for(self, word: str) -> str | None:
        examples = self.get_examples_for(word)
        if not examples:
            return None
        return examples[0][1]

    # Internal helpers -----------------------------------------------
    def _load_pairs(self) -> dict[str, list[tuple[str, str]]]:  # noqa: C901,PLR0912
        if self._pairs is not None:
            return self._pairs

        if self._pairs_cache.exists():
            try:
                data = json.loads(self._pairs_cache.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - corrupted cache
                raise TatoebaError(f"Failed to read cached Tatoeba data: {exc}") from exc
            self._pairs = {key: [(src, tgt) for src, tgt in value] for key, value in data.items()}
            return self._pairs

        source_sentences, source_lang_map = self._collect_sentences(self._source_langs)
        if not source_sentences:
            self._pairs_cache.write_text("{}", encoding="utf-8")
            self._pairs = {}
            return self._pairs

        target_sentences, _ = self._collect_sentences(self._target_langs)
        if not target_sentences:
            self._pairs_cache.write_text("{}", encoding="utf-8")
            self._pairs = {}
            return self._pairs

        links = self._collect_links(self._source_langs, source_lang_map)
        if not links:
            self._pairs_cache.write_text("{}", encoding="utf-8")
            self._pairs = {}
            return self._pairs

        pairs: dict[str, list[tuple[str, str]]] = {}
        seen: dict[str, set[_SentencePair]] = {}

        for lang in self._source_langs:
            for source_id, target_ids in links.get(lang, {}).items():
                source_text = source_sentences.get(source_id)
                if not source_text:
                    continue
                normalised_key = self._normalise(source_text)
                if not normalised_key:
                    continue
                for target_id in target_ids:
                    target_text = target_sentences.get(target_id)
                    if not target_text:
                        continue
                    pair = _SentencePair(source_text, target_text)
                    seen.setdefault(normalised_key, set()).add(pair)

        for key, pair_set in seen.items():
            ordered = sorted(pair_set, key=lambda pair: (pair.source.lower(), pair.target.lower()))
            pairs[key] = [(pair.source, pair.target) for pair in ordered]

        self._pairs_cache.write_text(json.dumps(pairs, ensure_ascii=False), encoding="utf-8")
        self._pairs = pairs
        return pairs

    def _collect_sentences(self, language_codes: set[str]) -> tuple[dict[str, str], dict[str, str]]:
        sentences: dict[str, str] = {}
        sentence_lang: dict[str, str] = {}
        for lang in language_codes:
            candidates: list[str] = [
                f"{lang}_sentences.tsv.bz2",
                f"{lang}_sentences.csv.bz2",
                f"{lang}_sentences.tsv",
                f"{lang}_sentences.csv",
            ]
            candidates.extend(SENTENCE_FILES)
            path = self._download_first_available(lang, candidates)
            if path is None:
                continue
            extracted = self._extract_sentences(path, lang)
            sentences.update(extracted)
            sentence_lang.update(dict.fromkeys(extracted, lang))
        return sentences, sentence_lang

    def _collect_links(
        self,
        language_codes: set[str],
        sentence_lang: dict[str, str],
    ) -> dict[str, dict[str, set[str]]]:
        links: dict[str, dict[str, set[str]]] = {}
        missing: list[str] = []
        for lang in language_codes:
            candidates: list[str] = []
            for target in self._target_langs:
                pair = f"{lang}-{target}"
                candidates.extend(
                    [
                        f"{pair}_links.tsv.bz2",
                        f"{pair}_links.csv.bz2",
                        f"{pair}_links.tsv",
                        f"{pair}_links.csv",
                    ],
                )
            candidates.extend(
                [
                    f"{lang}_links.tsv.bz2",
                    f"{lang}_links.csv.bz2",
                    f"{lang}_links.tsv",
                    f"{lang}_links.csv",
                ],
            )
            candidates.extend(LINK_FILES)
            path = self._download_first_available(lang, candidates)
            if path is None:
                missing.append(lang)
                continue
            links[lang] = self._extract_links(path)

        if missing:
            global_links = self._extract_links(self._ensure_global_links())
            for lang in missing:
                subset: dict[str, set[str]] = {}
                for src, targets in global_links.items():
                    if sentence_lang.get(src) != lang:
                        continue
                    subset[src] = targets
                links[lang] = subset
        return links

    def _extract_sentences(self, archive_path: Path, lang_code: str) -> dict[str, str]:
        sentences: dict[str, str] = {}
        suffixes = archive_path.suffixes
        try:
            if suffixes[-2:] == [".tar", ".bz2"]:
                with tarfile.open(archive_path, mode="r:bz2") as archive:
                    member = self._find_member(archive, target_suffix="sentences")
                    if member is None:
                        return sentences
                    fileobj = archive.extractfile(member)
                    if not fileobj:
                        return sentences
                    with TextIOWrapper(fileobj, encoding="utf-8", errors="ignore") as handle:
                        self._read_sentence_rows(handle, lang_code, sentences)
            else:
                opener = bz2.open if suffixes[-1:] == [".bz2"] else Path.open
                with opener(archive_path, "rt", encoding="utf-8", errors="ignore") as handle:
                    self._read_sentence_rows(handle, lang_code, sentences)
        except (OSError, tarfile.TarError) as exc:
            raise TatoebaError(f"Failed to open sentences archive for {lang_code}: {exc}") from exc
        return sentences

    def _extract_links(self, archive_path: Path) -> dict[str, set[str]]:
        results: dict[str, set[str]] = {}
        suffixes = archive_path.suffixes
        try:
            if suffixes[-2:] == [".tar", ".bz2"]:
                with tarfile.open(archive_path, mode="r:bz2") as archive:
                    member = self._find_member(archive, target_suffix="links")
                    if member is None:
                        return results
                    fileobj = archive.extractfile(member)
                    if not fileobj:
                        return results
                    with TextIOWrapper(fileobj, encoding="utf-8", errors="ignore") as handle:
                        self._read_link_rows(handle, results)
            else:
                opener = bz2.open if suffixes[-1:] == [".bz2"] else Path.open
                with opener(archive_path, "rt", encoding="utf-8", errors="ignore") as handle:
                    self._read_link_rows(handle, results)
        except (OSError, tarfile.TarError) as exc:
            raise TatoebaError(f"Failed to open links archive: {exc}") from exc
        return results

    def _ensure_download(self, language_code: str, filename: str) -> Path:
        local_name = (
            filename if filename.startswith(f"{language_code}_") else f"{language_code}_{filename}"
        )
        destination = self._download_dir / local_name
        if destination.exists():
            return destination

        legacy_candidates = [
            self._root / local_name,
            self._root / filename,
        ]
        for candidate in legacy_candidates:
            if candidate.exists():
                try:
                    shutil.copyfile(candidate, destination)
                except OSError:
                    continue
                return destination

        url = f"{TATOEBA_EXPORT_ROOT}/{language_code}/{filename}"
        try:
            with urlopen(url, timeout=180) as response, destination.open("wb") as handle:  # noqa: S310
                shutil.copyfileobj(response, handle)
        except (HTTPError, URLError, OSError) as exc:  # pragma: no cover - network failures
            raise TatoebaError(f"Failed to download {url}: {exc}") from exc
        return destination

    def _download_first_available(
        self,
        language_code: str,
        candidates: Iterable[str],
    ) -> Path | None:
        for name in candidates:
            try:
                return self._ensure_download(language_code, name)
            except TatoebaError:
                continue
        return None

    def _ensure_global_links(self) -> Path:
        if hasattr(self, "_global_links_path"):
            path = self._global_links_path
            if isinstance(path, Path) and path.exists():
                return path

        global_dir = self._root / "global"
        global_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("links.csv.bz2", "links.csv", "links.tar.bz2"):
            destination = global_dir / filename
            url = f"{TATOEBA_LINKS_ROOT}/{filename}"
            if destination.exists():
                self._global_links_path = destination
                return destination
            try:
                with urlopen(url, timeout=180) as response, destination.open("wb") as handle:  # noqa: S310
                    shutil.copyfileobj(response, handle)
            except (HTTPError, URLError, OSError):
                destination.unlink(missing_ok=True)
                continue
            self._global_links_path = destination
            return destination
        raise TatoebaError("Failed to download Tatoeba global links dataset")

    @staticmethod
    def _find_member(archive: tarfile.TarFile, *, target_suffix: str) -> tarfile.TarInfo | None:
        for member in archive.getmembers():
            name = Path(member.name).name.lower()
            if name.startswith(target_suffix) and name.endswith((".csv", ".tsv")):
                return member
        return None

    @staticmethod
    def _iter_rows(handle: Iterable[str]) -> Iterable[list[str]]:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "\t" in line:
                yield line.split("\t")
            else:
                yield line.split(",")

    @staticmethod
    def _clean_text(text: str) -> str:
        normalized = unicodedata.normalize("NFC", text)
        normalized = normalized.strip()
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = normalized.strip("'\"“”‘’()[]{}«»")
        return normalized.strip()

    @staticmethod
    def _word_count(text: str) -> int:
        if not text:
            return 0
        tokens = [token for token in re.split(r"\s+", text) if token]
        return len(tokens)

    @staticmethod
    def _normalise(text: str) -> str:
        base = TatoebaExamples._clean_text(text).lower()
        base = cyr_to_lat(base)
        base = re.sub(r"[^0-9a-zA-Zšđčćž\s-]", "", base)
        base = re.sub(r"\s+", " ", base)
        return base.strip()

    def _read_sentence_rows(
        self,
        handle: Iterable[str],
        lang_code: str,
        sentences: dict[str, str],
    ) -> None:
        for row in self._iter_rows(handle):
            if len(row) < SENTENCE_FIELDS_MIN:
                continue
            identifier, lang, text = row[0], row[1], row[2]
            if lang.lower() != lang_code.lower():
                continue
            cleaned = self._clean_text(text)
            if not cleaned:
                continue
            if self._word_count(cleaned) > MAX_WORDS:
                continue
            sentences[identifier] = cleaned

    def _read_link_rows(self, handle: Iterable[str], results: dict[str, set[str]]) -> None:
        for row in self._iter_rows(handle):
            if len(row) < LINK_FIELDS_MIN:
                continue
            src, tgt = row[0], row[1]
            results.setdefault(src, set()).add(tgt)

    @staticmethod
    def _cache_key(source_langs: set[str], target_langs: set[str]) -> str:
        sources = "-".join(sorted(source_langs))
        targets = "-".join(sorted(target_langs))
        return f"{sources}__{targets}"

    @staticmethod
    def _expand_language(code: str) -> set[str]:
        normalized = code.strip().lower()
        if normalized in {"srp", "hrv", "sr", "hr"}:
            return {"srp", "hrv"}
        return {normalized}
