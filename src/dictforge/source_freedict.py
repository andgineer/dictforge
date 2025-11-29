"""FreeDict dictionary source implementation with StarDict format support."""

import gzip
import json
import struct
import tarfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import requests

from .kaikki_utils import get_freedict_code
from .source_base import DictionarySource

FREEDICT_BASE_URL = "https://download.freedict.org/dictionaries"
FREEDICT_CACHE_DIR = "freedict"
FILTERED_CACHE_DIR = "filtered"
DOWNLOADS_CACHE_DIR = "downloads"

ProgressAdvance = Callable[[int], None]
ProgressFactory = Callable[..., AbstractContextManager[ProgressAdvance]]


class FreeDictDownloadError(RuntimeError):
    """Raised when FreeDict resources cannot be downloaded."""


class FreeDictParseError(RuntimeError):
    """Raised when StarDict files cannot be parsed."""


class FreeDictChainError(RuntimeError):
    """Raised when translation chaining fails."""


class FreeDictSource(DictionarySource):
    """Access and prepare FreeDict dictionaries in StarDict format."""

    # Serbian Cyrillic to Latin transliteration mapping
    CYRILLIC_TO_LATIN = {
        # Lowercase
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "ђ": "đ",
        "е": "e",
        "ж": "ž",
        "з": "z",
        "и": "i",
        "ј": "j",
        "к": "k",
        "л": "l",
        "љ": "lj",
        "м": "m",
        "н": "n",
        "њ": "nj",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "ћ": "ć",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "č",
        "џ": "dž",
        "ш": "š",
        # Uppercase
        "А": "A",
        "Б": "B",
        "В": "V",
        "Г": "G",
        "Д": "D",
        "Ђ": "Đ",
        "Е": "E",
        "Ж": "Ž",
        "З": "Z",
        "И": "I",
        "Ј": "J",
        "К": "K",
        "Л": "L",
        "Љ": "Lj",
        "М": "M",
        "Н": "N",
        "Њ": "Nj",
        "О": "O",
        "П": "P",
        "Р": "R",
        "С": "S",
        "Т": "T",
        "Ћ": "Ć",
        "У": "U",
        "Ф": "F",
        "Х": "H",
        "Ц": "C",
        "Ч": "Č",
        "Џ": "Dž",
        "Ш": "Š",
    }

    # Language pairs that should be auto-merged
    RELATED_LANGUAGES = {
        "Serbian": ["Croatian"],
    }

    def __init__(
        self,
        *,
        cache_dir: Path,
        session: requests.Session,
        progress_factory: ProgressFactory,
    ) -> None:
        """Initialize a FreeDict source with shared cache/session/progress helpers."""
        super().__init__()
        self.cache_dir = cache_dir
        self.session = session
        self._progress_factory = progress_factory

    def ensure_download_dirs(self, force: bool = False) -> None:  # noqa: ARG002
        """Make sure the FreeDict cache directory hierarchy exists."""
        freedict_root = self.cache_dir / FREEDICT_CACHE_DIR
        freedict_root.mkdir(parents=True, exist_ok=True)
        (freedict_root / FILTERED_CACHE_DIR).mkdir(parents=True, exist_ok=True)
        (freedict_root / DOWNLOADS_CACHE_DIR).mkdir(parents=True, exist_ok=True)

    def entry_has_content(self, entry: Any) -> bool:
        """Check if FreeDict entry has meaningful content."""
        if not isinstance(entry, dict):
            return False
        senses = entry.get("senses")
        if not isinstance(senses, list) or not senses:
            return False

        for sense in senses:
            if not isinstance(sense, dict):
                continue
            glosses = sense.get("glosses")
            if isinstance(glosses, str) and glosses.strip():
                return True
            if isinstance(glosses, list):
                for gloss in glosses:
                    if isinstance(gloss, str) and gloss.strip():
                        return True
        return False

    def get_entries(self, in_lang: str, out_lang: str) -> tuple[Path, int]:
        """Get entries with automatic Croatian merging for Serbian and translation chaining."""
        import sys

        self.ensure_download_dirs()

        # Try to get direct pair or chained translation
        try:
            entries_path, count = self._get_direct_or_chained(in_lang, out_lang)
            print(
                f"\033[36m[dictforge] FreeDict: loaded {count:,} entries for {in_lang} → {out_lang}\033[0m",
                file=sys.stderr,
            )
        except (FreeDictDownloadError, FreeDictChainError) as exc:
            # Return empty result if no dictionary available
            print(
                f"\033[33m[dictforge] FreeDict: no dictionary available for {in_lang} → {out_lang} ({type(exc).__name__})\033[0m",
                file=sys.stderr,
            )
            return self._create_empty_result(in_lang, out_lang)

        return entries_path, count

    def _transliterate_serbian_cyrillic(self, text: str) -> str:
        """Convert Serbian Cyrillic to Latin script.

        Uses the standard Serbian Cyrillic→Latin mapping including
        special digraphs (Љ→Lj, Њ→Nj, Џ→Dž).
        """
        return "".join(self.CYRILLIC_TO_LATIN.get(c, c) for c in text)

    def _apply_transliteration(self, entry: dict[str, Any], lang: str) -> dict[str, Any]:
        """Apply transliteration to entry if needed.

        For Serbian dictionaries:
        - Transliterate both 'word' and 'glosses' fields
        """
        if lang != "Serbian":
            return entry

        # Transliterate word
        if "word" in entry:
            entry["word"] = self._transliterate_serbian_cyrillic(entry["word"])

        # Transliterate glosses in all senses
        for sense in entry.get("senses", []):
            if "glosses" in sense:
                glosses = sense["glosses"]
                if isinstance(glosses, list):
                    sense["glosses"] = [self._transliterate_serbian_cyrillic(g) for g in glosses]
                elif isinstance(glosses, str):
                    sense["glosses"] = self._transliterate_serbian_cyrillic(glosses)

        return entry

    def _get_related_languages(self, lang: str) -> list[str]:
        """Return languages to automatically include.

        Rules:
            "Serbian" -> ["Croatian"]
            Others -> []
        """
        return self.RELATED_LANGUAGES.get(lang, [])

    def _create_empty_result(self, in_lang: str, out_lang: str) -> tuple[Path, int]:
        """Create an empty JSONL file for when no dictionary is available."""
        freedict_root = self.cache_dir / FREEDICT_CACHE_DIR / FILTERED_CACHE_DIR
        freedict_root.mkdir(parents=True, exist_ok=True)
        empty_path = freedict_root / f"{in_lang}__{out_lang}__empty.jsonl"
        empty_path.touch()
        return empty_path, 0

    def _get_direct_or_chained(self, in_lang: str, out_lang: str) -> tuple[Path, int]:
        """Try direct pair first, then chained translation if unavailable."""
        # First, try direct translation
        try:
            return self._get_direct_pair(in_lang, out_lang)
        except FreeDictDownloadError:
            # Direct pair not available, try chaining through English
            chained_path = self._try_chained_translation(in_lang, out_lang)
            if chained_path:
                # Count entries in chained file
                count = sum(1 for _ in chained_path.open("r", encoding="utf-8"))
                return chained_path, count
            raise

    def _get_direct_pair(self, in_lang: str, out_lang: str) -> tuple[Path, int]:
        """Get direct language pair with optional Croatian merging for Serbian."""
        in_code = get_freedict_code(in_lang)
        out_code = get_freedict_code(out_lang)

        # Check if we need to merge related languages
        related_langs = self._get_related_languages(in_lang)

        if not related_langs:
            # Simple case: single language pair
            entries = self._fetch_and_parse_dict(in_lang, out_lang, in_code, out_code)
        else:
            # Merge primary language with related languages
            entries = self._fetch_and_parse_dict(in_lang, out_lang, in_code, out_code)

            for related_lang in related_langs:
                related_code = get_freedict_code(related_lang)
                try:
                    related_entries = self._fetch_and_parse_dict(
                        related_lang,
                        out_lang,
                        related_code,
                        out_code,
                    )
                    # Merge related entries into main entries
                    self._merge_entries_list(entries, related_entries)
                except (FreeDictDownloadError, FreeDictParseError):
                    # If related language not available, continue without it
                    pass

        # Write to cache
        cache_key = f"{in_lang}__{out_lang}"
        if related_langs:
            cache_key += f"__{'_'.join(related_langs)}"

        freedict_root = self.cache_dir / FREEDICT_CACHE_DIR / FILTERED_CACHE_DIR
        output_path = freedict_root / f"{cache_key}.jsonl"

        with output_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        count = len(entries)
        return output_path, count

    def _merge_entries_list(self, target: list[dict], incoming: list[dict]) -> None:
        """Merge incoming entries into target list by word (case-insensitive)."""
        # Build index of existing words
        word_index: dict[str, int] = {}
        for idx, entry in enumerate(target):
            word_lower = entry.get("word", "").lower()
            if word_lower:
                word_index[word_lower] = idx

        # Add or merge incoming entries
        for entry in incoming:
            word_lower = entry.get("word", "").lower()
            if not word_lower:
                continue

            if word_lower in word_index:
                # Merge senses
                target_idx = word_index[word_lower]
                target_entry = target[target_idx]
                target_senses = target_entry.setdefault("senses", [])
                incoming_senses = entry.get("senses", [])

                # Build set of existing glosses to avoid duplicates
                existing_glosses = set()
                for sense in target_senses:
                    glosses = sense.get("glosses", [])
                    if isinstance(glosses, list):
                        existing_glosses.add(tuple(glosses))
                    elif isinstance(glosses, str):
                        existing_glosses.add((glosses,))

                # Add new senses
                for sense in incoming_senses:
                    glosses = sense.get("glosses", [])
                    gloss_key = tuple(glosses) if isinstance(glosses, list) else (glosses,)
                    if gloss_key not in existing_glosses:
                        target_senses.append(sense)
                        existing_glosses.add(gloss_key)
            else:
                # New word, add to target
                target.append(entry)
                word_index[word_lower] = len(target) - 1

    def _fetch_and_parse_dict(
        self,
        lang_name: str,
        out_lang: str,
        in_code: str,
        out_code: str,
    ) -> list[dict]:
        """Fetch dictionary for language pair and parse to Kaikki format."""
        import sys

        lang_pair = f"{in_code}-{out_code}"

        # Download and extract StarDict files
        dict_dir = self._download_dictionary(lang_pair)
        print(
            f"\033[36m[dictforge] FreeDict: parsing StarDict files from {dict_dir}\033[0m",
            file=sys.stderr,
        )

        # Parse StarDict files to entries
        entries = self._parse_stardict_files(dict_dir)
        print(
            f"\033[36m[dictforge] FreeDict: parsed {len(entries)} entries from {lang_pair}\033[0m",
            file=sys.stderr,
        )

        # Apply transliteration for Serbian
        if lang_name == "Serbian":
            entries = [self._apply_transliteration(e, lang_name) for e in entries]
            print(
                f"\033[36m[dictforge] FreeDict: applied transliteration to {len(entries)} entries\033[0m",
                file=sys.stderr,
            )

        return entries

    def _download_dictionary(self, lang_pair: str) -> Path:
        """Download and extract StarDict dictionary for language pair.

        Returns path to directory containing extracted .ifo, .idx, .dict.dz files.
        """
        import sys

        freedict_root = self.cache_dir / FREEDICT_CACHE_DIR

        # Try to find existing extracted directory
        pair_dir = freedict_root / lang_pair
        if pair_dir.exists():
            # Find version directory (e.g., "0.2", "1.3")
            version_dirs = [d for d in pair_dir.iterdir() if d.is_dir()]
            if version_dirs:
                # Use latest version (sort by name)
                latest_version = sorted(version_dirs)[-1]
                if self._has_stardict_files(latest_version):
                    print(
                        f"\033[36m[dictforge] FreeDict: using cached {lang_pair}\033[0m",
                        file=sys.stderr,
                    )
                    return latest_version

        # Need to download - try to find latest version
        print(
            f"\033[36m[dictforge] FreeDict: looking for {lang_pair} dictionary\033[0m",
            file=sys.stderr,
        )
        version = self._find_latest_version(lang_pair)
        if not version:
            print(
                f"\033[33m[dictforge] FreeDict: dictionary {lang_pair} not found on freedict.org\033[0m",
                file=sys.stderr,
            )
            raise FreeDictDownloadError(
                f"Could not find FreeDict dictionary for {lang_pair}",
            )

        # Download tar.xz archive - find actual filename from directory listing
        downloads_dir = freedict_root / DOWNLOADS_CACHE_DIR
        download_path = downloads_dir / f"{lang_pair}-{version}.tar.xz"

        # Download if not cached
        if not download_path.exists():
            # Fetch directory listing to find actual filename
            version_url = f"{FREEDICT_BASE_URL}/{lang_pair}/{version}/"
            print(
                f"\033[36m[dictforge] FreeDict: fetching directory listing from {version_url}\033[0m",
                file=sys.stderr,
            )

            download_url = None
            try:
                response = self.session.get(version_url, timeout=10)
                if response.status_code == 200:
                    # Parse HTML for tar.xz files
                    import re

                    # Look for links to .tar.xz files
                    tar_pattern = r'href="([^"]*\.tar\.xz)"'
                    tar_files = re.findall(tar_pattern, response.text)

                    if tar_files:
                        # Prefer files with 'stardict' in the name
                        stardict_files = [f for f in tar_files if "stardict" in f.lower()]
                        filename = stardict_files[0] if stardict_files else tar_files[0]
                        download_url = f"{FREEDICT_BASE_URL}/{lang_pair}/{version}/{filename}"
                        print(
                            f"\033[36m[dictforge] FreeDict: found file {filename}\033[0m",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"\033[33m[dictforge] FreeDict: no .tar.xz files found in {version_url}\033[0m",
                            file=sys.stderr,
                        )
            except requests.RequestException as e:
                print(
                    f"\033[33m[dictforge] FreeDict: could not fetch directory listing: {e}\033[0m",
                    file=sys.stderr,
                )

            # Fallback: try common filename patterns
            if not download_url:
                print(
                    "\033[36m[dictforge] FreeDict: trying common filename patterns\033[0m",
                    file=sys.stderr,
                )
                filename_patterns = [
                    f"freedict-{lang_pair}.tar.xz",
                    f"{lang_pair}.tar.xz",
                    f"freedict-{lang_pair}-{version}.tar.xz",
                ]

                for filename in filename_patterns:
                    url = f"{FREEDICT_BASE_URL}/{lang_pair}/{version}/{filename}"
                    try:
                        response = self.session.head(url, timeout=10)
                        if response.status_code == 200:
                            download_url = url
                            print(
                                f"\033[36m[dictforge] FreeDict: found {filename}\033[0m",
                                file=sys.stderr,
                            )
                            break
                    except requests.RequestException:
                        continue

            if not download_url:
                raise FreeDictDownloadError(
                    f"Could not find downloadable file for {lang_pair} version {version}",
                )

            print(
                f"\033[36m[dictforge] FreeDict: downloading {download_url}\033[0m",
                file=sys.stderr,
            )
            try:
                response = self.session.get(download_url, stream=True, timeout=180)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise FreeDictDownloadError(
                    f"Failed to download FreeDict {lang_pair} from {download_url}: {exc}",
                ) from exc

            # Save archive
            with download_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(
                f"\033[36m[dictforge] FreeDict: downloaded {download_path.name}\033[0m",
                file=sys.stderr,
            )

        # Extract to version directory
        extract_dir = pair_dir / version
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            print(
                f"\033[36m[dictforge] FreeDict: extracting {download_path.name}\033[0m",
                file=sys.stderr,
            )
            with tarfile.open(download_path, "r:xz") as tar:
                tar.extractall(path=extract_dir)
        except (tarfile.TarError, OSError) as exc:
            raise FreeDictParseError(
                f"Failed to extract {download_path}: {exc}",
            ) from exc

        # Find the actual StarDict files (may be in a subdirectory)
        print(
            f"\033[36m[dictforge] FreeDict: searching for StarDict files in {extract_dir}\033[0m",
            file=sys.stderr,
        )

        # List contents of extract_dir for debugging
        if extract_dir.exists():
            contents = list(extract_dir.iterdir())
            print(
                f"\033[36m[dictforge] FreeDict: extract_dir contains {len(contents)} items: {[p.name for p in contents[:5]]}\033[0m",
                file=sys.stderr,
            )

        stardict_dir = self._find_stardict_dir(extract_dir)
        if not stardict_dir:
            raise FreeDictParseError(
                f"Could not find StarDict files in {extract_dir}",
            )

        print(
            f"\033[36m[dictforge] FreeDict: found StarDict files in {stardict_dir}\033[0m",
            file=sys.stderr,
        )
        return stardict_dir

    def _find_latest_version(self, lang_pair: str) -> str | None:
        """Try to find latest version for a language pair."""
        import re
        import sys

        # First, try to fetch the directory listing and parse available versions
        index_url = f"{FREEDICT_BASE_URL}/{lang_pair}/"
        try:
            response = self.session.get(index_url, timeout=10)
            if response.status_code == 200:
                # Parse HTML for version directories (looking for links like "2023.09.10/")
                # Match patterns like: href="2023.09.10/" or href="0.2/"
                version_pattern = r'href="([0-9]+(?:\.[0-9]+)*(?:\.[0-9]{2}\.[0-9]{2})?)/\"'
                versions = re.findall(version_pattern, response.text)
                if versions:
                    # Sort versions (newest first) - date-based versions will sort correctly
                    sorted_versions = sorted(versions, reverse=True)
                    print(
                        f"\033[36m[dictforge] FreeDict: found versions for {lang_pair}: {', '.join(sorted_versions[:3])}\033[0m",
                        file=sys.stderr,
                    )
                    return sorted_versions[0]
        except requests.RequestException as e:
            print(
                f"\033[33m[dictforge] FreeDict: could not fetch version list for {lang_pair}: {e}\033[0m",
                file=sys.stderr,
            )

        # Fallback: try common version patterns
        common_versions = [
            # Recent date-based versions (try last few years)
            "2024.12.18",
            "2024.09.10",
            "2024.04.22",
            "2023.12.18",
            "2023.09.10",
            "2023.04.22",
            "2022.12.18",
            "2022.09.10",
            # Semantic versions
            "0.2",
            "0.1.3",
            "0.1.2",
            "0.1.1",
            "0.1",
            "1.0",
            "1.3",
        ]

        for version in common_versions:
            url = f"{FREEDICT_BASE_URL}/{lang_pair}/{version}/"
            try:
                response = self.session.head(url, timeout=10)
                if response.status_code == 200:
                    print(
                        f"\033[36m[dictforge] FreeDict: found version {version} for {lang_pair}\033[0m",
                        file=sys.stderr,
                    )
                    return version
            except requests.RequestException:
                continue

        return None

    def _has_stardict_files(self, directory: Path) -> bool:
        """Check if directory contains .ifo, .idx, and .dict.dz files."""
        import sys

        files = list(directory.glob("*.ifo"))
        if not files:
            # Log what files ARE there
            all_files = list(directory.glob("*"))
            if all_files and len(all_files) <= 10:
                print(
                    f"\033[36m[dictforge] FreeDict: {directory.name} contains: {[f.name for f in all_files]}\033[0m",
                    file=sys.stderr,
                )
            return False

        base_name = files[0].stem
        print(
            f"\033[36m[dictforge] FreeDict: found .ifo file '{files[0].name}', base_name='{base_name}'\033[0m",
            file=sys.stderr,
        )

        # List all files in directory for debugging
        all_files = list(directory.glob("*"))
        print(
            f"\033[36m[dictforge] FreeDict: {directory.name} has {len(all_files)} files: {[f.name for f in all_files]}\033[0m",
            file=sys.stderr,
        )

        # Check for .idx or .idx.gz
        has_idx = (directory / f"{base_name}.idx").exists() or (
            directory / f"{base_name}.idx.gz"
        ).exists()
        has_dict = (directory / f"{base_name}.dict.dz").exists() or (
            directory / f"{base_name}.dict"
        ).exists()

        print(
            f"\033[36m[dictforge] FreeDict: looking for '{base_name}.idx/.idx.gz' (found={has_idx}), '{base_name}.dict.dz/.dict' (found={has_dict})\033[0m",
            file=sys.stderr,
        )

        return has_idx and has_dict

    def _find_stardict_dir(self, root: Path) -> Path | None:
        """Find directory containing StarDict files (may be in subdirectory)."""
        import sys

        # Check root first
        print(
            f"\033[36m[dictforge] FreeDict: checking root {root} for StarDict files\033[0m",
            file=sys.stderr,
        )
        if self._has_stardict_files(root):
            print(
                "\033[36m[dictforge] FreeDict: found StarDict files in root\033[0m",
                file=sys.stderr,
            )
            return root

        # Search subdirectories (max depth 2)
        subdirs = [d for d in root.rglob("*") if d.is_dir()]
        print(
            f"\033[36m[dictforge] FreeDict: searching {len(subdirs)} subdirectories\033[0m",
            file=sys.stderr,
        )

        for i, subdir in enumerate(subdirs):
            if i < 5:  # Log first few for debugging
                print(
                    f"\033[36m[dictforge] FreeDict: checking {subdir.relative_to(root)}\033[0m",
                    file=sys.stderr,
                )
            if self._has_stardict_files(subdir):
                print(
                    f"\033[36m[dictforge] FreeDict: found StarDict files in {subdir.relative_to(root)}\033[0m",
                    file=sys.stderr,
                )
                return subdir

        return None

    def _parse_stardict_files(self, dict_dir: Path) -> list[dict]:
        """Parse StarDict .ifo, .idx/.idx.gz, .dict/.dict.dz files to Kaikki format."""
        # Find .ifo file
        ifo_files = list(dict_dir.glob("*.ifo"))
        if not ifo_files:
            raise FreeDictParseError(f"No .ifo file found in {dict_dir}")

        ifo_path = ifo_files[0]
        base_name = ifo_path.stem

        # Check for .idx or .idx.gz
        idx_path = dict_dir / f"{base_name}.idx"
        idx_path_gz = dict_dir / f"{base_name}.idx.gz"

        if idx_path.exists():
            actual_idx_path = idx_path
        elif idx_path_gz.exists():
            actual_idx_path = idx_path_gz
        else:
            raise FreeDictParseError(f"Missing .idx or .idx.gz file: {idx_path}")

        # Check for .dict or .dict.dz
        dict_path_dz = dict_dir / f"{base_name}.dict.dz"
        dict_path = dict_dir / f"{base_name}.dict"

        if not dict_path_dz.exists() and not dict_path.exists():
            raise FreeDictParseError(f"Missing .dict or .dict.dz file in {dict_dir}")

        # Parse metadata
        metadata = self._read_ifo_metadata(ifo_path)

        # Parse index
        index = self._read_index(actual_idx_path)

        # Read definitions
        actual_dict_path = dict_path_dz if dict_path_dz.exists() else dict_path
        definitions = self._read_definitions(actual_dict_path, index)

        # Convert to Kaikki format
        entries = []
        for word, definition in definitions.items():
            entry = self._convert_to_kaikki_format(word, definition, metadata)
            if self.entry_has_content(entry):
                entries.append(entry)

        return entries

    def _read_ifo_metadata(self, ifo_path: Path) -> dict[str, str]:
        """Parse .ifo metadata file."""
        metadata = {}
        try:
            with ifo_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, _, value = line.partition("=")
                        metadata[key.strip()] = value.strip()
        except OSError as exc:
            raise FreeDictParseError(f"Failed to read {ifo_path}: {exc}") from exc

        return metadata

    def _read_index(self, idx_path: Path) -> list[tuple[str, int, int]]:
        """Parse .idx or .idx.gz file.

        Returns: [(word, offset, size), ...]

        Format: word\\0 + offset[4 bytes BE] + size[4 bytes BE]
        """
        index = []
        try:
            # Handle both .idx and .idx.gz
            if idx_path.suffix == ".gz":
                with gzip.open(idx_path, "rb") as f:
                    data = f.read()
            else:
                with idx_path.open("rb") as f:
                    data = f.read()
        except OSError as exc:
            raise FreeDictParseError(f"Failed to read {idx_path}: {exc}") from exc

        pos = 0
        while pos < len(data):
            # Find null terminator for word
            null_pos = data.find(b"\x00", pos)
            if null_pos == -1:
                break

            word_bytes = data[pos:null_pos]
            try:
                word = word_bytes.decode("utf-8", errors="ignore")
            except UnicodeDecodeError:
                word = word_bytes.decode("latin-1", errors="ignore")

            # Read offset and size (big-endian 4-byte integers)
            offset_pos = null_pos + 1
            if offset_pos + 8 > len(data):
                break

            offset = struct.unpack(">I", data[offset_pos : offset_pos + 4])[0]
            size = struct.unpack(">I", data[offset_pos + 4 : offset_pos + 8])[0]

            index.append((word, offset, size))
            pos = offset_pos + 8

        return index

    def _read_definitions(
        self,
        dict_path: Path,
        index: list[tuple[str, int, int]],
    ) -> dict[str, str]:
        """Read definitions from .dict or .dict.dz file."""
        definitions = {}

        try:
            # Handle compressed (.dz) or plain (.dict) file
            if dict_path.suffix == ".dz":
                with gzip.open(dict_path, "rb") as f:
                    dict_data = f.read()
            else:
                with dict_path.open("rb") as f:
                    dict_data = f.read()
        except (OSError, gzip.BadGzipFile) as exc:
            raise FreeDictParseError(f"Failed to read {dict_path}: {exc}") from exc

        # Extract definitions using index
        for word, offset, size in index:
            if offset + size > len(dict_data):
                continue

            definition_bytes = dict_data[offset : offset + size]
            try:
                definition = definition_bytes.decode("utf-8", errors="ignore")
            except UnicodeDecodeError:
                definition = definition_bytes.decode("latin-1", errors="ignore")

            definitions[word] = definition.strip()

        return definitions

    def _convert_to_kaikki_format(
        self,
        word: str,
        definition: str,
        metadata: dict[str, str],
    ) -> dict[str, Any]:
        """Convert StarDict entry to Kaikki JSONL format."""
        # Parse definition - can be plain text or HTML
        # For simplicity, split on common delimiters
        glosses = self._extract_glosses(definition)

        return {
            "word": word,
            "pos": "noun",  # FreeDict doesn't provide POS, use default
            "senses": [
                {
                    "glosses": glosses,
                    "raw_glosses": glosses,
                },
            ],
        }

    def _extract_glosses(self, definition: str) -> list[str]:
        """Extract glosses from StarDict definition text.

        StarDict definitions can be plain text or HTML. Extract meaningful glosses.
        """
        # Remove common HTML tags
        import re

        text = re.sub(r"<[^>]+>", "", definition)

        # Split on common delimiters
        parts = re.split(r"[;|\n]", text)
        glosses = [part.strip() for part in parts if part.strip()]

        # If no delimiters found, return whole text
        if not glosses:
            glosses = [text.strip()] if text.strip() else []

        return glosses

    def _try_chained_translation(self, in_lang: str, out_lang: str) -> Path | None:
        """Attempt translation via English pivot.

        Example: Serbian → Russian becomes Serbian → English → Russian
        """
        import sys

        # Only chain through English
        pivot_lang = "English"

        print(
            f"\033[36m[dictforge] FreeDict: attempting chained translation {in_lang} → {pivot_lang} → {out_lang}\033[0m",
            file=sys.stderr,
        )

        # Check if we can build the chain
        in_code = get_freedict_code(in_lang)
        pivot_code = get_freedict_code(pivot_lang)
        out_code = get_freedict_code(out_lang)

        # Check cache first
        cache_key = f"{in_lang}__{out_lang}__chained"
        freedict_root = self.cache_dir / FREEDICT_CACHE_DIR / FILTERED_CACHE_DIR
        cached_path = freedict_root / f"{cache_key}.jsonl"

        if cached_path.exists():
            print(
                "\033[36m[dictforge] FreeDict: using cached chained translation\033[0m",
                file=sys.stderr,
            )
            return cached_path

        try:
            # Get first pair: in_lang → English
            print(
                f"\033[36m[dictforge] FreeDict: fetching {in_code}-{pivot_code} ({in_lang} → {pivot_lang})\033[0m",
                file=sys.stderr,
            )
            first_pair_entries = self._fetch_and_parse_dict(
                in_lang,
                pivot_lang,
                in_code,
                pivot_code,
            )
            print(
                f"\033[36m[dictforge] FreeDict: got {len(first_pair_entries)} entries for first pair\033[0m",
                file=sys.stderr,
            )

            # Get second pair: English → out_lang
            print(
                f"\033[36m[dictforge] FreeDict: fetching {pivot_code}-{out_code} ({pivot_lang} → {out_lang})\033[0m",
                file=sys.stderr,
            )
            second_pair_entries = self._fetch_and_parse_dict(
                pivot_lang,
                out_lang,
                pivot_code,
                out_code,
            )
            print(
                f"\033[36m[dictforge] FreeDict: got {len(second_pair_entries)} entries for second pair\033[0m",
                file=sys.stderr,
            )

            # Build pivot translation map
            pivot_map: dict[str, list[str]] = {}
            for entry in second_pair_entries:
                word_lower = entry.get("word", "").lower()
                glosses = []
                for sense in entry.get("senses", []):
                    sense_glosses = sense.get("glosses", [])
                    if isinstance(sense_glosses, list):
                        glosses.extend(sense_glosses)
                    elif isinstance(sense_glosses, str):
                        glosses.append(sense_glosses)
                if glosses:
                    pivot_map[word_lower] = glosses

            # Build chained entries
            chained_entries = []
            for entry in first_pair_entries:
                word = entry.get("word", "")
                final_glosses: set[str] = set()

                # For each gloss in first pair, look up in pivot map
                for sense in entry.get("senses", []):
                    sense_glosses = sense.get("glosses", [])
                    if isinstance(sense_glosses, str):
                        sense_glosses = [sense_glosses]

                    for pivot_word in sense_glosses:
                        pivot_lower = pivot_word.lower().strip()
                        if pivot_lower in pivot_map:
                            final_glosses.update(pivot_map[pivot_lower])

                if final_glosses:
                    chained_entry = {
                        "word": word,
                        "pos": "noun",  # FreeDict doesn't provide POS, use default
                        "senses": [
                            {
                                "glosses": sorted(final_glosses),
                                "raw_glosses": sorted(final_glosses),
                            },
                        ],
                    }
                    chained_entries.append(chained_entry)

            # Write to cache
            with cached_path.open("w", encoding="utf-8") as f:
                for entry in chained_entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            return cached_path

        except (FreeDictDownloadError, FreeDictParseError) as exc:
            print(
                f"\033[31m[dictforge] FreeDict: chaining failed: {type(exc).__name__}: {exc}\033[0m",
                file=sys.stderr,
            )
            raise FreeDictChainError(
                f"Cannot chain {in_lang} → {pivot_lang} → {out_lang}: {exc}",
            ) from exc
        except Exception as exc:
            print(
                f"\033[31m[dictforge] FreeDict: unexpected error during chaining: {type(exc).__name__}: {exc}\033[0m",
                file=sys.stderr,
            )
            raise FreeDictChainError(
                f"Unexpected error chaining {in_lang} → {pivot_lang} → {out_lang}: {exc}",
            ) from exc
