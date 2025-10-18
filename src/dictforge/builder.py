from __future__ import annotations

from html.parser import HTMLParser
from json import JSONDecodeError
from pathlib import Path

from ebook_dictionary_creator import DictionaryCreator

RESPONSE_EXCERPT_MAX_LENGTH = 200
ELLIPSE = "..."


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
        self.excerpt = self._load_excerpt()

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


class Builder:
    """
    Thin wrapper around ebook_dictionary_creator.
    Downloads Kaikki data, builds DB, exports Kindle dictionary.
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir

    def ensure_download(self, force: bool = False) -> None:  # noqa: ARG002
        # Placeholder for future caching/version pinning; ensure dir exists.
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _export_one(  # noqa: PLR0913
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
    ) -> None:
        dc = DictionaryCreator(in_lang, out_lang)
        dc.download_data_from_kaikki()
        try:
            dc.create_database()
        except JSONDecodeError as exc:
            raise KaikkiParseError(getattr(dc, "kaikki_file_path", None), exc) from exc
        mobi_base = outdir / f"{in_lang}-{out_lang}"
        dc.export_to_kindle(
            kindlegen_path=kindlegen_path,
            try_to_fix_failed_inflections=try_fix_inflections,  # type: ignore[arg-type]  # bug in the lib
            author="Wiktionary via Wiktextract (Kaikki.org)",
            title=title,
            mobi_temp_folder_path=str(mobi_base),
            mobi_output_file_path=f"{mobi_base}.mobi",
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
    ) -> None:
        primary = in_langs[0]
        self._export_one(
            primary,
            out_lang,
            outdir,
            kindlegen_path,
            title,
            shortname,
            include_pos,
            try_fix_inflections,
            max_entries,
        )

        for extra in in_langs[1:]:
            extra_out = outdir / f"extra_{extra.replace(' ', '_')}"
            extra_out.mkdir(parents=True, exist_ok=True)
            self._export_one(
                extra,
                out_lang,
                extra_out,
                kindlegen_path,
                f"{title} (extra: {extra})",
                f"{shortname}+{extra}",
                include_pos,
                try_fix_inflections,
                max_entries,
            )
