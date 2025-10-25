from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from json import JSONDecodeError
from pathlib import Path
from typing import Any, TextIO, cast

from ebook_dictionary_creator import DictionaryCreator
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from .kaikki import KaikkiClient, KaikkiDownloadError, KaikkiParseError
from .langutil import lang_meta
from .tatoeba import TatoebaError, TatoebaExamples
from .translit import cyr_to_lat

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

_TATOEBA_CODE_MAP = {
    "en": "eng",
    "ru": "rus",
    "sr": "srp",
    "hr": "hrv",
}


class KindleBuildError(RuntimeError):
    """Raised when kindlegen fails while creating the MOBI file."""


class _BaseProgressCapture(io.TextIOBase):
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
        self._task_id: TaskID | None = None
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

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def write(self, text: str) -> int:
        self._captured.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self.handle_line(line.strip())
        return len(text)

    def flush(self) -> None:  # pragma: no cover - interface requirement
        if self._buffer.strip():
            self.handle_line(self._buffer.strip())
            self._buffer = ""

    def handle_line(self, line: str) -> None:  # pragma: no cover - override in subclasses
        self._warnings.append(line)

    def set_description(self, text: str) -> None:
        if self._progress is not None and self._task_id is not None:
            task_id = self._task_id
            self._progress.update(
                task_id,
                description=self._format_description(text),
            )

    def set_total(self, total: int) -> None:
        if self._progress is not None and self._task_id is not None:
            task_id = self._task_id
            self._progress.update(task_id, total=total)

    def advance_to(self, value: int) -> None:
        self._current = max(self._current, value)
        if self._progress is not None and self._task_id is not None:
            task_id = self._task_id
            self._progress.update(task_id, completed=self._current)

    def finish(self) -> None:
        if self._progress is not None and self._task_id is not None:
            completed = self._total_hint if self._total_hint is not None else self._current
            task_id = self._task_id
            self._progress.update(task_id, completed=completed)

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
    def __init__(
        self,
        cache_dir: Path,
        show_progress: bool | None = None,
        *,
        reset_cache: bool = False,
    ) -> None:
        self.cache_dir = cache_dir
        self._show_progress = sys.stderr.isatty() if show_progress is None else show_progress
        self._console = Console(stderr=True, force_terminal=self._show_progress)
        self._reset_cache = reset_cache
        self.kaikki = KaikkiClient(cache_dir, reset_cache=reset_cache)

    # ------------------------------------------------------------------
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
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def _slugify(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()) or "language"

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

    def _resolve_source_languages(self, primary: str, iso_code: str) -> list[str]:
        if iso_code.lower() in {"sr", "hr"}:
            return sorted({primary, "Serbian", "Croatian"})
        return [primary]

    def _tatoeba_code(self, iso_code: str) -> str | None:
        return _TATOEBA_CODE_MAP.get(iso_code.lower())

    def _load_tatoeba(self, source_iso: str, target_iso: str) -> TatoebaExamples | None:
        source_code = self._tatoeba_code(source_iso)
        target_code = self._tatoeba_code(target_iso)
        if not source_code or not target_code:
            return None
        try:
            return TatoebaExamples(
                source_lang=source_code,
                target_lang=target_code,
                cache_dir=self.cache_dir,
                reset_cache=self._reset_cache,
            )
        except TatoebaError as exc:
            self._console.print(
                f"[dictforge] Warning: failed to load Tatoeba data ({exc}).",
                style="yellow",
            )
            return None

    def _normalise_key(self, word: str, *, normalize_serbian: bool) -> str:
        text = word.strip()
        if normalize_serbian:
            text = cyr_to_lat(text)
        return re.sub(r"\s+", " ", text.lower())

    def _normalize_display(self, word: str, *, normalize_serbian: bool) -> str:
        text = word.strip()
        if normalize_serbian:
            text = cyr_to_lat(text)
        return re.sub(r"\s+", " ", text)

    def _normalize_examples(
        self,
        examples: Iterable[tuple[str, str]],
        *,
        normalize_serbian: bool,
    ) -> list[tuple[str, str]]:
        normalized: list[tuple[str, str]] = []
        for source, target in examples:
            source_text = re.sub(r"\s+", " ", source.strip())
            if normalize_serbian:
                source_text = cyr_to_lat(source_text)
            normalized.append((source_text, target.strip()))
        return normalized

    def _merge_entries(self, target: dict[str, Any], source: dict[str, Any]) -> None:
        if source is target:
            return
        for key in ("senses", "forms"):
            target_list = target.get(key)
            source_list = source.get(key)
            if isinstance(target_list, list) and isinstance(source_list, list):
                target_list.extend(source_list)
            elif not target_list and isinstance(source_list, list):
                target[key] = list(source_list)

    def _apply_tatoeba_enrichment(
        self,
        entry: dict[str, Any],
        examples: list[tuple[str, str]],
        gloss: str | None,
        *,
        normalize_serbian: bool,
    ) -> bool:
        changed = False
        senses = entry.setdefault("senses", [])
        if not senses:
            senses.append({})
        sense = senses[0]

        if gloss and not sense.get("glosses"):
            sense["glosses"] = [gloss]
            sense["raw_glosses"] = [gloss]
            changed = True

        if examples:
            normalized_examples = self._normalize_examples(
                examples,
                normalize_serbian=normalize_serbian,
            )
            bucket = sense.setdefault("examples", [])
            existing = {
                (example.get("text"), example.get("translation"))
                for example in bucket
                if isinstance(example, dict)
            }
            for source_text, target_text in normalized_examples:
                pair = (source_text, target_text)
                if pair in existing:
                    continue
                bucket.append({"text": source_text, "translation": target_text})
                existing.add(pair)
                changed = True

        return changed

    def _create_tatoeba_entry(  # noqa: PLR0913
        self,
        *,
        headword: str,  # noqa: ARG002
        display_word: str,
        matches: list[tuple[str, str]],
        gloss: str | None,
        language_name: str,
        normalize_serbian: bool,
    ) -> dict[str, Any]:
        normalized_examples = self._normalize_examples(
            matches,
            normalize_serbian=normalize_serbian,
        )
        sense: dict[str, Any] = {}
        if gloss:
            sense["glosses"] = [gloss]
            sense["raw_glosses"] = [gloss]
        if normalized_examples:
            sense["examples"] = [
                {"text": src, "translation": tgt} for src, tgt in normalized_examples
            ]
        return {
            "word": display_word,
            "language": language_name,
            "senses": [sense] if sense else [],
            "source": "tatoeba",
        }

    def _prepare_dataset(  # noqa: C901,PLR0912,PLR0913,PLR0915
        self,
        *,
        source_langs: list[str],
        primary_language: str,
        out_lang: str,
        normalize_serbian: bool,
        tatoeba: TatoebaExamples | None,
        max_entries: int,
    ) -> tuple[Path, dict[str, int]]:
        combined_dir = self.cache_dir / "combined"
        combined_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self._slugify('_'.join(source_langs))}__to__{self._slugify(out_lang)}.jsonl"
        combined_path = combined_dir / filename

        combined_entries: list[dict[str, Any]] = []
        indices_by_key: dict[str, list[int]] = {}
        headword_sources: dict[str, set[str]] = {}
        enriched_from_tatoeba: set[str] = set()
        kaikki_headwords: set[str] = set()
        kaikki_total_entries = 0

        tatoeba_vocab: set[str] = set()
        if tatoeba is not None:
            try:
                tatoeba_vocab = tatoeba.vocabulary()
            except TatoebaError as exc:
                self._console.print(
                    f"[dictforge] Warning: failed to read Tatoeba vocabulary ({exc}).",
                    style="yellow",
                )
                tatoeba_vocab = set()

        for language in source_langs:
            filtered_path, count = self.kaikki.ensure_filtered_language(language)
            kaikki_total_entries += count
            data_path = filtered_path
            target_iso_code, _ = lang_meta(out_lang)
            if target_iso_code != "en":
                data_path = self.kaikki.ensure_translated_glosses(
                    filtered_path,
                    "English",
                    out_lang,
                )

            with data_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    word = entry.get("word")
                    if not isinstance(word, str):
                        continue
                    display_word = self._normalize_display(
                        word,
                        normalize_serbian=normalize_serbian,
                    )
                    key = self._normalise_key(display_word, normalize_serbian=normalize_serbian)
                    if not key:
                        continue
                    entry["word"] = display_word
                    if normalize_serbian:
                        for form in entry.get("forms") or []:
                            if isinstance(form, dict) and isinstance(form.get("form"), str):
                                form["form"] = self._normalize_display(
                                    form["form"],
                                    normalize_serbian=True,
                                )

                    entry_index = len(combined_entries)
                    combined_entries.append(entry)
                    indices_by_key.setdefault(key, []).append(entry_index)
                    headword_sources.setdefault(key, set()).add("kaikki")
                    kaikki_headwords.add(key)

                    if tatoeba is not None:
                        examples = tatoeba.get_examples_for(display_word)
                        gloss = tatoeba.get_gloss_for(display_word)
                        if examples or gloss:  # noqa: SIM102
                            if self._apply_tatoeba_enrichment(
                                entry,
                                examples,
                                gloss,
                                normalize_serbian=normalize_serbian,
                            ):
                                headword_sources[key].add("tatoeba")
                                enriched_from_tatoeba.add(key)

        if tatoeba is not None:
            for key in sorted(tatoeba_vocab):
                headword_sources.setdefault(key, set()).add("tatoeba")
                existing_indices = indices_by_key.get(key, [])
                examples = tatoeba.get_examples_for(key)
                gloss = tatoeba.get_gloss_for(key)
                if existing_indices:
                    changed = False
                    for idx in existing_indices:
                        if self._apply_tatoeba_enrichment(
                            combined_entries[idx],
                            examples,
                            gloss,
                            normalize_serbian=normalize_serbian,
                        ):
                            changed = True
                    if changed:
                        enriched_from_tatoeba.add(key)
                    continue
                if not examples and not gloss:
                    continue
                display_word = self._normalize_display(
                    examples[0][0] if examples else key,
                    normalize_serbian=normalize_serbian,
                )
                entry = self._create_tatoeba_entry(
                    headword=key,
                    display_word=display_word,
                    matches=examples,
                    gloss=gloss,
                    language_name=primary_language,
                    normalize_serbian=normalize_serbian,
                )
                entry_index = len(combined_entries)
                combined_entries.append(entry)
                indices_by_key.setdefault(key, []).append(entry_index)
                enriched_from_tatoeba.add(key)

        if max_entries > 0 and len(combined_entries) > max_entries:
            combined_entries = combined_entries[:max_entries]

        with combined_path.open("w", encoding="utf-8") as fh:
            for entry in combined_entries:
                fh.write(json.dumps(entry, ensure_ascii=False))
                fh.write("\n")

        stats = {
            "kaikki_total": kaikki_total_entries,
            "kaikki_unique": len(kaikki_headwords),
            "tatoeba_total": len(tatoeba_vocab),
            "tatoeba_unique": len(tatoeba_vocab),
            "overlap": len({k for k in tatoeba_vocab if k in indices_by_key}),
            "enriched_from_tatoeba": len(enriched_from_tatoeba),
            "final_headword_count": len(combined_entries),
        }

        return combined_path, stats

    def _print_stats(self, stats: dict[str, int]) -> None:
        self._console.print("[dictforge] Source statistics", style="cyan")
        self._console.print(
            f"  Kaikki headwords: {stats['kaikki_total']:,} (unique {stats['kaikki_unique']:,})",
            style="dim",
        )
        self._console.print(
            (
                "  Tatoeba expressions: "
                f"{stats['tatoeba_total']:,} (unique {stats['tatoeba_unique']:,})"
            ),
            style="dim",
        )
        self._console.print(
            f"  Overlap: {stats['overlap']:,}",
            style="dim",
        )
        self._console.print(
            f"  Enriched from Tatoeba: {stats['enriched_from_tatoeba']:,}",
            style="dim",
        )
        self._console.print(
            f"  Final dictionary size: {stats['final_headword_count']:,}",
            style="dim",
        )

    def _ensure_opf_languages(
        self,
        opf_path: Path,
        kindle_in: str,
        kindle_out: str,
        title: str,
    ) -> None:
        if not opf_path.exists():
            raise KindleBuildError("content.opf is missing; cannot update languages.")
        tree = ET.parse(opf_path)
        root = tree.getroot()
        ns = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        title_elem = root.find("dc:title", ns)
        if title_elem is not None:
            title_elem.text = title
        lang_elem = root.find("dc:language", ns)
        if lang_elem is not None:
            lang_elem.text = kindle_out
        xmetadata = root.find("opf:metadata", ns)
        if xmetadata is not None:
            in_elem = xmetadata.find("opf:DictionaryInLanguage", ns)
            out_elem = xmetadata.find("opf:DictionaryOutLanguage", ns)
            if in_elem is not None:
                in_elem.text = kindle_in
            if out_elem is not None:
                out_elem.text = kindle_out
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

    # ------------------------------------------------------------------
    def _export_one(  # noqa: C901,PLR0913,PLR0915
        self,
        in_lang: str,
        out_lang: str,
        outdir: Path,
        kindlegen_path: str,
        title: str,
        shortname: str,  # noqa: ARG002
        include_pos: bool,  # noqa: ARG002
        try_fix_inflections: bool,
        max_entries: int,
        kindle_lang_override: str | None = None,
    ) -> int:
        in_iso, _ = lang_meta(in_lang)
        out_iso, _ = lang_meta(out_lang)
        normalize_serbian = in_iso.lower() in {"sr", "hr"}
        source_langs = self._resolve_source_languages(in_lang, in_iso)
        tatoeba = self._load_tatoeba(in_iso, out_iso)

        combined_path, stats = self._prepare_dataset(
            source_langs=source_langs,
            primary_language=in_lang,
            out_lang=out_lang,
            normalize_serbian=normalize_serbian,
            tatoeba=tatoeba,
            max_entries=max_entries,
        )

        self._print_stats(stats)

        entry_count = stats["final_headword_count"]
        kindle_in = self._kindle_lang_code(in_iso)
        kindle_out = self._kindle_lang_code(out_iso, override=kindle_lang_override)

        dc = DictionaryCreator(in_lang, out_lang, kaikki_file_path=str(combined_path))
        dc.source_language = kindle_in
        dc.target_language = kindle_out
        database_path = self.cache_dir / f"{self._slugify(in_lang)}_{self._slugify(out_lang)}.db"
        db_capture = _DatabaseProgressCapture(console=self._console, enabled=self._show_progress)
        db_capture.start()
        try:
            with (
                redirect_stdout(cast(TextIO, db_capture)),
                redirect_stderr(
                    cast(TextIO, db_capture),
                ),
            ):
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

        mobi_base = outdir / f"{self._slugify(in_lang)}-{self._slugify(out_lang)}"
        shutil.rmtree(mobi_base, ignore_errors=True)
        kindle_capture = _KindleProgressCapture(
            console=self._console,
            enabled=self._show_progress,
            total_hint=entry_count if entry_count else None,
        )
        kindle_capture.start()
        fallback_exc: FileNotFoundError | None = None
        try:
            with (
                redirect_stdout(cast(TextIO, kindle_capture)),
                redirect_stderr(
                    cast(TextIO, kindle_capture),
                ),
            ):
                dc.export_to_kindle(
                    kindlegen_path=kindlegen_path,
                    try_to_fix_failed_inflections=try_fix_inflections,  # type: ignore[arg-type]
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

        if fallback_exc is not None:
            kindle_path = Path(kindlegen_path)
            if kindle_path.exists():
                raise fallback_exc from fallback_exc
            opf_path = mobi_base / "OEBPS" / "content.opf"
            self._ensure_opf_languages(opf_path, kindle_in, kindle_out, title)
            self._run_kindlegen(kindlegen_path, opf_path)

        mobi_path = mobi_base.with_suffix(".mobi")
        if mobi_path.exists():
            target_path = outdir / f"{self._slugify(in_lang)}-{self._slugify(out_lang)}.mobi"
            if mobi_path != target_path:
                shutil.copyfile(mobi_path, target_path)

        self._announce_summary(in_lang, out_lang, entry_count, kindle_capture)
        self._emit_creator_output("Kindle export output", kindle_capture)

        return entry_count

    # ------------------------------------------------------------------
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
        counts: dict[str, int] = {}
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
            extra_out = outdir / f"extra_{self._slugify(extra)}"
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

        self.kaikki.close()
        return counts


__all__ = [
    "Builder",
    "KindleBuildError",
    "KaikkiDownloadError",
    "KaikkiParseError",
]
