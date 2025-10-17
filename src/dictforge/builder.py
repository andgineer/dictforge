from __future__ import annotations
from pathlib import Path
from typing import List
from ebook_dictionary_creator import DictionaryCreator

class Builder:
    """
    Thin wrapper around ebook_dictionary_creator.
    Downloads Kaikki data, builds DB, exports Kindle dictionary.
    """
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir

    def ensure_download(self, force: bool = False):
        # Placeholder for future caching/version pinning; ensure dir exists.
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _export_one(self,
                    in_lang: str,
                    out_lang: str,
                    outdir: Path,
                    kindlegen_path: str,
                    title: str,
                    shortname: str,
                    include_pos: bool,
                    try_fix_inflections: bool,
                    max_entries: int):
        dc = DictionaryCreator(in_lang, out_lang)
        dc.download_data_from_kaikki()
        dc.create_database()
        dc.export_to_kindle(
            kindlegen_path=kindlegen_path,
            author="Wiktionary via Wiktextract (Kaikki.org)",
            title=title,
            mobi_path=str(outdir / f"{in_lang}-{out_lang}"),
            include_pos=include_pos,
            try_to_fix_failed_inflections=try_fix_inflections,
            max_entries=max_entries if max_entries > 0 else None,
        )

    def build_dictionary(self,
                         in_langs: List[str],
                         out_lang: str,
                         title: str,
                         shortname: str,
                         outdir: Path,
                         kindlegen_path: str,
                         include_pos: bool,
                         try_fix_inflections: bool,
                         max_entries: int):
        primary = in_langs[0]
        self._export_one(primary, out_lang, outdir, kindlegen_path, title, shortname,
                         include_pos, try_fix_inflections, max_entries)

        for extra in in_langs[1:]:
            extra_out = outdir / f"extra_{extra.replace(' ', '_')}"
            extra_out.mkdir(parents=True, exist_ok=True)
            self._export_one(extra, out_lang, extra_out, kindlegen_path,
                             f"{title} (extra: {extra})", f"{shortname}+{extra}",
                             include_pos, try_fix_inflections, max_entries)
