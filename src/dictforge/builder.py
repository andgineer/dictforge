from __future__ import annotations

import gzip
import io
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from html.parser import HTMLParser
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from ebook_dictionary_creator import DictionaryCreator
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    Task,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from .langutil import lang_meta

RAW_DUMP_URL = "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz"
RAW_CACHE_DIR = "raw"
FILTERED_CACHE_DIR = "filtered"
META_SUFFIX = ".meta.json"
RESPONSE_EXCERPT_MAX_LENGTH = 200
ELLIPSE = "..."
LANGUAGE_CACHE_DIR = "languages"
TRANSLATION_CACHE_DIR = "translations"
LANGUAGE_DUMP_URL = "https://kaikki.org/dictionary/{lang}/kaikki.org-dictionary-{slug}.jsonl"

KINDLE_SUPPORTED_LANGS = {
    "af",
    "sq",
    "ar",
    "ar-dz",
    "ar-bh",
    "ar-eg",
    "ar-iq",
    "ar-jo",
    "ar-kw",
    "ar-lb",
    "ar-ly",
    "ar-ma",
    "ar-om",
    "ar-qa",
    "ar-sa",
    "ar-sy",
    "ar-tn",
    "ar-ae",
    "ar-ye",
    "hy",
    "az",
    "eu",
    "be",
    "bn",
    "bg",
    "ca",
    "zh",
    "zh-hk",
    "zh-cn",
    "zh-sg",
    "zh-tw",
    "hr",
    "cs",
    "da",
    "nl",
    "nl-be",
    "en",
    "en-au",
    "en-bz",
    "en-ca",
    "en-ie",
    "en-jm",
    "en-nz",
    "en-ph",
    "en-za",
    "en-tt",
    "en-gb",
    "en-us",
    "en-zw",
    "et",
    "fo",
    "fa",
    "fi",
    "fr",
    "fr-be",
    "fr-ca",
    "fr-lu",
    "fr-mc",
    "fr-ch",
    "ka",
    "de",
    "de-at",
    "de-li",
    "de-lu",
    "de-ch",
    "el",
    "gu",
    "he",
    "hi",
    "hu",
    "is",
    "id",
    "it",
    "it-ch",
    "ja",
    "kn",
    "kk",
    "x-kok",
    "ko",
    "lv",
    "lt",
    "mk",
    "ms",
    "ms-bn",
    "ml",
    "mt",
    "mr",
    "ne",
    "no",
    "no-bok",
    "no-nyn",
    "or",
    "pl",
    "pt",
    "pt-br",
    "pa",
    "rm",
    "ro",
    "ro-mo",
    "ru",
    "ru-mo",
    "sz",
    "sa",
    "sr-latn",
    "sk",
    "sl",
    "sb",
    "es",
    "es-ar",
    "es-bo",
    "es-cl",
    "es-co",
    "es-cr",
    "es-do",
    "es-ec",
    "es-sv",
    "es-gt",
    "es-hn",
    "es-mx",
    "es-ni",
    "es-pa",
    "es-py",
    "es-pe",
    "es-pr",
    "es-uy",
    "es-ve",
    "sx",
    "sw",
    "sv",
    "sv-fi",
    "ta",
    "tt",
    "te",
    "th",
    "ts",
    "tn",
    "tr",
    "uk",
    "ur",
    "uz",
    "vi",
    "xh",
    "zu",
}


class KaikkiDownloadError(RuntimeError):
    """Raised when Kaikki resources cannot be downloaded."""


class KindleBuildError(RuntimeError):
    """Raised when kindlegen fails while creating the MOBI file."""


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
            if len(line) <= RESPONSE_EXCERPT_MAX_LENGTH
            else f"{line[: RESPONSE_EXCERPT_MAX_LENGTH - len(ELLIPSE)]}{ELLIPSE}"
            for line in excerpt
        ]


def _format_units(task: Task, unit: str) -> str:
    completed = int(task.completed or 0)
    total = task.total
    label = unit if unit != "B" else "B"
    if total is None:
        return f"{completed:,} {label}"
    return f"{completed:,}/{int(total):,} {label}"


class _BaseProgressCapture:
    def __init__(
        self,
        *,
        console: Console,
        enabled: bool,
        description: str,
        unit: str,
        total_hint: int | None = None,
    ) -> None:
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

    def _format_description(self, text: str) -> str:
        unit_hint = f" [{self._unit}]" if self._unit else ""
        return f"{text}{unit_hint}"

    def start(self) -> None:
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
        if self._buffer.strip():
            self.handle_line(self._buffer.strip())
        self._buffer = ""
        if self._progress is not None and self._task_id is not None:
            self._progress.__exit__(None, None, None)
            self._progress = None

    def write(self, text: str) -> int:
        self._captured.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self.handle_line(line.strip())
        return len(text)

    def flush(self) -> None:  # pragma: no cover - interface requirement
        return None

    def handle_line(self, line: str) -> None:  # pragma: no cover - overridden
        if line:
            self._warnings.append(line)

    def set_total(self, total: int) -> None:
        if total < 0:
            return
        self._total_hint = total
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, total=total)  # type: ignore

    def advance_to(self, value: int) -> None:
        if value <= self._current:
            return
        self._current = value
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, completed=value)  # type: ignore

    def set_description(self, description: str) -> None:
        self._description = description
        if self._progress is not None and self._task_id is not None:
            self._progress.update(
                self._task_id,  # type: ignore
                description=self._format_description(description),
            )

    def finish(self) -> None:
        if self._progress is not None and self._task_id is not None:
            completed = self._total_hint if self._total_hint is not None else self._current
            self._progress.update(self._task_id, completed=completed)  # type: ignore

    @property
    def warnings(self) -> list[str]:
        return self._warnings

    def output(self) -> str:
        if self._buffer.strip():
            self.handle_line(self._buffer.strip())
            self._buffer = ""
        return self._captured.getvalue()


class _DatabaseProgressCapture(_BaseProgressCapture):
    def __init__(self, *, console: Console, enabled: bool) -> None:
        super().__init__(
            console=console,
            enabled=enabled,
            description="Building database",
            unit="inflections",
        )

    def handle_line(self, line: str) -> None:
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


class Builder:
    """
    Thin wrapper around ebook_dictionary_creator.
    Downloads Kaikki data, builds DB, exports Kindle dictionary.
    """

    def __init__(self, cache_dir: Path, show_progress: bool | None = None):
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self._translation_cache: dict[tuple[str, str], dict[str, list[str]]] = {}
        self._show_progress = sys.stderr.isatty() if show_progress is None else show_progress
        self._console = Console(stderr=True, force_terminal=self._show_progress)

    @contextmanager
    def _progress_bar(
        self,
        *,
        description: str,
        total: int | None = None,
        unit: str = "entries",
    ) -> Iterator[Callable[[int], None]]:
        if not self._show_progress:

            def noop(_: int) -> None:
                return None

            yield noop
            return

        columns: list[Any] = [TextColumn("[progress.description]{task.description}")]
        if total is None:
            columns.append(SpinnerColumn())
        else:
            columns.append(BarColumn(bar_width=None))
        if unit == "B":
            columns.extend([DownloadColumn(), TransferSpeedColumn()])
        columns.append(TimeElapsedColumn())
        if total is not None:
            columns.append(TimeRemainingColumn())
        else:
            label = "bytes" if unit == "B" else unit
            columns.append(TextColumn(f"{{task.completed:,}} {label}"))

        progress = Progress(
            *columns,
            console=self._console,
            transient=False,
            refresh_per_second=4,
            expand=True,
        )
        with progress:
            task_id = progress.add_task(description, total=total)

            def advance(amount: int) -> None:
                progress.update(task_id, advance=amount)

            yield advance

    def _emit_creator_output(self, label: str, capture: _BaseProgressCapture) -> None:
        output = capture.output().strip()
        if not output:
            return
        self._console.print(f"[dictforge] {label}", style="yellow")
        self._console.print(output, style="dim")

    def _announce_summary(
        self,
        in_lang: str,
        out_lang: str,
        entry_count: int,
        capture: _KindleProgressCapture,
    ) -> None:
        parts = [f"{entry_count:,} entries"]
        if capture.base_forms is not None:
            parts.append(f"{capture.base_forms:,} base forms")
        if capture.inflections is not None:
            parts.append(f"{capture.inflections:,} inflections")
        summary = ", ".join(parts)
        self._console.print(
            f"[dictforge] {in_lang} → {out_lang}: {summary}",
            style="green",
        )

    def ensure_download(self, force: bool = False) -> None:  # noqa: ARG002
        # Placeholder for future caching/version pinning; ensure dir exists.
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _slugify(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()) or "language"

    def _kaikki_slug(self, language: str) -> str:
        return language.replace(" ", "").replace("-", "").replace("'", "")

    def _ensure_language_dataset(self, language: str) -> Path:
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
            self._progress_bar(
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

    def _load_translation_map(self, source_lang: str, target_lang: str) -> dict[str, list[str]]:
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
        in_lang: str,  # noqa: ARG002
        out_lang: str,
    ) -> Path:
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

    def _ensure_raw_dump(self) -> Path:
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
            self._progress_bar(
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

    def _ensure_filtered_language(self, language: str) -> tuple[Path, int]:
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
            if meta.get("source_mtime") == raw_mtime and meta.get("count"):
                return filtered_path, int(meta["count"])

        count = 0
        try:
            with (
                self._progress_bar(
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
                        dst.write(line if line.endswith("\n") else f"{line}\n")
                        count += 1
        except OSError as exc:
            raise KaikkiDownloadError(
                f"Failed to read Kaikki raw dump from {raw_dump}: {exc}",
            ) from exc

        if count == 0:
            filtered_path.unlink(missing_ok=True)
            raise KaikkiDownloadError(
                f"No entries found for language '{language}' in Kaikki raw dump.",
            )

        meta_path.write_text(
            json.dumps({"language": language, "count": count, "source_mtime": raw_mtime}),
            encoding="utf-8",
        )

        return filtered_path, count

    def _kindle_lang_code(self, code: str | None, override: str | None = None) -> str:
        if override:
            normalized_override = override.lower()
            if normalized_override in KINDLE_SUPPORTED_LANGS:
                return normalized_override
            raise KindleBuildError(
                (
                    f"Kindle language override '{override}' is not supported by Kindle. "
                    "Check the supported list and pick a valid code."
                ),
            )

        if not code:
            return "en"

        normalized = code.lower()
        if normalized in KINDLE_SUPPORTED_LANGS:
            return normalized

        overrides = {
            "sr": "hr",
            "en": "en-us",
        }
        normalized = overrides.get(normalized, normalized)

        if normalized == "en":
            return "en-us"

        return normalized if normalized in KINDLE_SUPPORTED_LANGS else "en"

    def _export_one(  # noqa: PLR0913,PLR0915
        self,
        in_lang: str,
        out_lang: str,
        outdir: Path,
        kindlegen_path: str,
        title: str,
        shortname: str,  # noqa: ARG002
        include_pos: bool,  # noqa: ARG002
        try_fix_inflections: bool,
        max_entries: int,  # noqa: ARG002
        kindle_lang_override: str | None = None,
    ) -> int:
        language_file, entry_count = self._ensure_filtered_language(in_lang)
        language_file = self._ensure_translated_glosses(language_file, in_lang, out_lang)
        iso_in, _ = lang_meta(in_lang)
        iso_out, _ = lang_meta(out_lang)
        kindle_in = self._kindle_lang_code(iso_in)
        kindle_out = self._kindle_lang_code(iso_out, override=kindle_lang_override)

        dc = DictionaryCreator(in_lang, out_lang, kaikki_file_path=str(language_file))
        dc.source_language = kindle_in
        dc.target_language = kindle_out
        database_path = self.cache_dir / f"{self._slugify(in_lang)}_{self._slugify(out_lang)}.db"
        db_capture = _DatabaseProgressCapture(console=self._console, enabled=self._show_progress)
        db_capture.start()
        try:
            with redirect_stdout(db_capture), redirect_stderr(db_capture):  # type: ignore
                try:
                    dc.create_database(database_path=str(database_path))
                except JSONDecodeError as exc:
                    raise KaikkiParseError(getattr(dc, "kaikki_file_path", None), exc) from exc
        except Exception:
            self._emit_creator_output("Database build output", db_capture)
            raise
        else:
            db_capture.finish()
        finally:
            db_capture.stop()
        mobi_base = outdir / f"{in_lang}-{out_lang}"
        shutil.rmtree(mobi_base, ignore_errors=True)
        kindle_capture = _KindleProgressCapture(
            console=self._console,
            enabled=self._show_progress,
            total_hint=entry_count if entry_count else None,
        )
        kindle_capture.start()
        fallback_exc: FileNotFoundError | None = None
        try:
            with redirect_stdout(kindle_capture), redirect_stderr(kindle_capture):  # type: ignore
                dc.export_to_kindle(
                    kindlegen_path=kindlegen_path,
                    try_to_fix_failed_inflections=try_fix_inflections,  # type: ignore[arg-type]  # bug in the lib
                    author="Wiktionary via Wiktextract (Kaikki.org)",
                    title=title,
                    mobi_temp_folder_path=str(mobi_base),
                    mobi_output_file_path=f"{mobi_base}.mobi",
                )
        except FileNotFoundError as exc:
            fallback_exc = exc
        except Exception:
            self._emit_creator_output("Kindle export output", kindle_capture)
            raise
        else:
            kindle_capture.finish()
        finally:
            kindle_capture.stop()

        if fallback_exc is None:
            self._announce_summary(in_lang, out_lang, entry_count, kindle_capture)
            return entry_count

        opf_path = mobi_base / "OEBPS" / "content.opf"
        if not opf_path.exists():
            raise KindleBuildError(
                "Kindle Previewer failed and content.opf is missing; see previous output.",
            ) from fallback_exc
        self._console.print(
            "[dictforge] Kindle Previewer fallback: fixing metadata and retrying",
            style="yellow",
        )
        self._ensure_opf_languages(opf_path, kindle_in, kindle_out, title)
        self._run_kindlegen(kindlegen_path, opf_path)
        mobi_path = mobi_base / "OEBPS" / "content.mobi"
        if not mobi_path.exists():
            raise KindleBuildError(
                "Kindle Previewer did not produce content.mobi even after fixing metadata.",
            ) from fallback_exc
        final_path = Path(f"{mobi_base}.mobi")
        shutil.move(mobi_path, final_path)
        dc.mobi_path = str(final_path)
        shutil.rmtree(mobi_base, ignore_errors=True)

        self._announce_summary(in_lang, out_lang, entry_count, kindle_capture)
        return entry_count

    def _ensure_opf_languages(  # noqa: PLR0912,C901
        self,
        opf_path: Path,
        primary_code: str,
        secondary_code: str,
        title: str,
    ) -> None:
        print(
            (
                f"[dictforge] Preparing OPF languages: source→'{primary_code}', "
                f"target→'{secondary_code}'"
            ),
            flush=True,
        )

        tree = ET.parse(opf_path)
        ns = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/",
            "legacy": "http://purl.org/metadata/dublin_core",
        }
        ET.register_namespace("", ns["opf"])
        ET.register_namespace("dc", ns["dc"])
        metadata = tree.find("opf:metadata", ns)
        if metadata is None:
            metadata = ET.SubElement(tree.getroot(), "{http://www.idpf.org/2007/opf}metadata")

        # modern dc:title/creator fallbacks
        if metadata.find("dc:title", ns) is None:
            title_elem = ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}title")
            title_elem.text = title or "dictforge dictionary"

        if metadata.find("dc:creator", ns) is None:
            legacy = metadata.find("opf:dc-metadata", ns)
            creator_text = None
            if legacy is not None:
                legacy_creator = legacy.find("legacy:Creator", ns)
                if legacy_creator is not None:
                    creator_text = legacy_creator.text
            ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}creator").text = (
                creator_text or "dictforge"
            )

        # modern dc:language entries
        for elem in list(metadata.findall("dc:language", ns)):
            metadata.remove(elem)
        ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}language").text = primary_code

        # legacy dc-metadata block
        legacy = metadata.find("opf:dc-metadata", ns)
        if legacy is not None:
            for elem in legacy.findall("legacy:Language", ns):
                elem.text = primary_code
            if legacy.find("legacy:Title", ns) is None:
                ET.SubElement(legacy, "{http://purl.org/metadata/dublin_core}Title").text = title
            if legacy.find("legacy:Creator", ns) is None:
                ET.SubElement(
                    legacy,
                    "{http://purl.org/metadata/dublin_core}Creator",
                ).text = "dictforge"

        # x-metadata block used by Kindle dictionaries
        x_metadata = metadata.find("opf:x-metadata", ns)
        if x_metadata is not None:
            dict_in = x_metadata.find("opf:DictionaryInLanguage", ns)
            if dict_in is not None:
                dict_in.text = primary_code
            dict_out = x_metadata.find("opf:DictionaryOutLanguage", ns)
            if dict_out is not None:
                dict_out.text = secondary_code
            default_lookup = x_metadata.find("opf:DefaultLookupIndex", ns)
            if default_lookup is None:
                ET.SubElement(
                    x_metadata,
                    "{http://www.idpf.org/2007/opf}DefaultLookupIndex",
                ).text = "default"

        tree.write(opf_path, encoding="utf-8", xml_declaration=True)

    def _run_kindlegen(self, kindlegen_path: str, opf_path: Path) -> None:
        if not kindlegen_path:
            raise KindleBuildError("Kindle Previewer path is empty; cannot invoke kindlegen.")

        process = subprocess.run(
            [kindlegen_path, opf_path.name],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(opf_path.parent),
        )
        if process.returncode != 0:
            raise KindleBuildError(
                "Kindle Previewer reported an error after fixing metadata:\n"
                f"STDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}",
            )

    def build_dictionary(  # noqa: PLR0913
        self,
        in_langs: list[str],
        out_lang: str,
        title: str,
        shortname: str,
        outdir: Path,
        kindlegen_path: str,
        include_pos: bool,
        try_fix_inflections: bool,
        max_entries: int,
        kindle_lang_override: str | None = None,
    ) -> dict[str, int]:
        primary = in_langs[0]
        counts = {}
        counts[primary] = self._export_one(
            primary,
            out_lang,
            outdir,
            kindlegen_path,
            title,
            shortname,
            include_pos,
            try_fix_inflections,
            max_entries,
            kindle_lang_override,
        )

        for extra in in_langs[1:]:
            extra_out = outdir / f"extra_{extra.replace(' ', '_')}"
            extra_out.mkdir(parents=True, exist_ok=True)
            counts[extra] = self._export_one(
                extra,
                out_lang,
                extra_out,
                kindlegen_path,
                f"{title} (extra: {extra})",
                f"{shortname}+{extra}",
                include_pos,
                try_fix_inflections,
                max_entries,
                kindle_lang_override,
            )

        self.session.close()
        return counts
