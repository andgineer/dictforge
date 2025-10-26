from __future__ import annotations

import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dictforge.builder import (
    Builder,
    KaikkiDownloadError,
    KaikkiParseError,
    KindleBuildError,
)
from dictforge.source_kaikki import KaikkiSource


@pytest.fixture
def builder(tmp_path: Path) -> Builder:
    return Builder(tmp_path, show_progress=False)


@pytest.fixture
def kaikki_source(builder: Builder) -> KaikkiSource:
    return builder._sources[0]


def test_slugify_and_kaikki_slug(builder: Builder, kaikki_source: KaikkiSource) -> None:
    assert builder._slugify("Serbo-Croatian!") == "Serbo_Croatian_"
    assert kaikki_source._kaikki_slug("Serbo-Croatian") == "SerboCroatian"


def test_ensure_download_creates_cache(builder: Builder) -> None:
    builder.ensure_download()
    assert builder.cache_dir.exists()


def test_ensure_language_dataset_uses_cached_file(
    builder: Builder, kaikki_source: KaikkiSource
) -> None:
    lang_dir = builder.cache_dir / "languages"
    lang_dir.mkdir(parents=True, exist_ok=True)
    cached = lang_dir / "kaikki.org-dictionary-Serbian.jsonl"
    cached.write_text("{}", encoding="utf-8")

    path = kaikki_source.ensure_language_dataset("Serbian")
    assert path == cached


def test_ensure_language_dataset_downloads_when_missing(
    kaikki_source: KaikkiSource, monkeypatch
) -> None:
    chunks = [b"line1", b"line2"]

    class DummyResponse:
        def raise_for_status(self) -> None:  # pragma: no cover - simple no-op
            return

        def iter_content(self, chunk_size: int):
            yield from chunks

    monkeypatch.setattr(
        kaikki_source.session,
        "get",
        lambda url, stream, timeout: DummyResponse(),
    )

    path = kaikki_source.ensure_language_dataset("Serbian")
    assert path.exists()
    assert path.read_bytes() == b"".join(chunks)


def test_load_translation_map_reads_dump(
    kaikki_source: KaikkiSource, monkeypatch, tmp_path: Path
) -> None:
    dataset = tmp_path / "kaikki.org-dictionary-English.jsonl"
    dataset.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "word": "House",
                        "senses": [
                            {
                                "translations": [
                                    {"lang": "Serbian", "word": "kuća"},
                                    {"lang": "Serbian", "word": "дом"},
                                ],
                            },
                        ],
                    },
                ),
                json.dumps(
                    {
                        "word": "Ignore",
                        "senses": [
                            {"translations": []},
                        ],
                    },
                ),
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(kaikki_source, "_ensure_language_dataset", lambda language: dataset)

    mapping = kaikki_source._load_translation_map("English", "Serbian")
    assert mapping == {"house": ["kuća", "дом"]}
    assert kaikki_source.translation_cache[("english", "serbian")] is mapping


def test_apply_translation_glosses(kaikki_source: KaikkiSource) -> None:
    entry = {
        "senses": [
            {
                "links": [["Hello"], ["world", "extra"]],
                "glosses": ["Greeting"],
            },
            {
                "links": [],
                "glosses": ["Greeting; informal"],
            },
        ],
    }
    translation_map = {
        "hello": ["hola"],
        "greeting": ["saludo"],
    }

    kaikki_source._apply_translation_glosses(entry, translation_map)

    first, second = entry["senses"]
    assert first["glosses"] == ["hola"]
    assert second["glosses"] == ["saludo"]
    assert second["raw_glosses"] == ["saludo"]


def test_ensure_translated_glosses_reuses_cache(
    kaikki_source: KaikkiSource, monkeypatch, tmp_path: Path
) -> None:
    base_path = tmp_path / "Serbian-English.jsonl"
    base_path.write_text(
        json.dumps({"senses": [{"links": [["Hello"]]}]}) + "\n",
        encoding="utf-8",
    )

    localized_path = base_path.with_name(f"{base_path.stem}__to_ru.jsonl")

    monkeypatch.setattr(
        kaikki_source,
        "_load_translation_map",
        lambda source, target: {"hello": ["здраво"]},
    )

    localized = kaikki_source._ensure_translated_glosses(base_path, "Russian")
    assert localized == localized_path
    content = localized.read_text(encoding="utf-8").strip()
    assert "здраво" in content

    localized.touch()
    localized = kaikki_source._ensure_translated_glosses(base_path, "Russian")
    assert localized == localized_path


def _create_raw_dump(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line)
    return path


class DummySource:
    def __init__(self, base_dir: Path, name: str, entries: list[dict[str, Any]]):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / f"{name}.jsonl"
        self.path.write_text(
            "".join(json.dumps(entry) + "\n" for entry in entries),
            encoding="utf-8",
        )
        self.entries = entries
        self.ensure_calls = 0

    def ensure_download(self, force: bool = False) -> None:  # noqa: ARG002
        self.ensure_calls += 1

    def get_entries(self, in_lang: str, out_lang: str) -> tuple[Path, int]:  # noqa: ARG002
        return self.path, len(self.entries)


def test_ensure_filtered_language_filters_and_caches(
    kaikki_source: KaikkiSource, monkeypatch, tmp_path: Path
) -> None:
    raw_path = tmp_path / "raw" / "dump.jsonl.gz"
    _create_raw_dump(
        raw_path,
        [
            json.dumps({"language": "Serbian", "word": "priča"}) + "\n",
            json.dumps({"language": "English", "word": "story"}) + "\n",
        ],
    )

    monkeypatch.setattr(kaikki_source, "_ensure_raw_dump", lambda: raw_path)

    filtered_path, count = kaikki_source._ensure_filtered_language("Serbian")
    assert count == 1
    entries = [json.loads(line) for line in filtered_path.read_text(encoding="utf-8").splitlines()]
    assert any(entry["word"] == "priča" for entry in entries)

    cached_path, cached_count = kaikki_source._ensure_filtered_language("Serbian")
    assert cached_path == filtered_path
    assert cached_count == 1


def test_ensure_filtered_language_invalid_json(
    kaikki_source: KaikkiSource, monkeypatch, tmp_path: Path
) -> None:
    raw_path = tmp_path / "raw" / "dump.jsonl.gz"
    _create_raw_dump(raw_path, ["{invalid}\n"])
    monkeypatch.setattr(kaikki_source, "_ensure_raw_dump", lambda: raw_path)

    with pytest.raises(KaikkiParseError):
        kaikki_source._ensure_filtered_language("Serbian")


def test_ensure_filtered_language_without_matches(
    kaikki_source: KaikkiSource, monkeypatch, tmp_path: Path
) -> None:
    raw_path = tmp_path / "raw" / "dump.jsonl.gz"
    _create_raw_dump(raw_path, [json.dumps({"language": "English"}) + "\n"])
    monkeypatch.setattr(kaikki_source, "_ensure_raw_dump", lambda: raw_path)

    with pytest.raises(KaikkiDownloadError):
        kaikki_source._ensure_filtered_language("Serbian")


def test_prepare_combined_entries_merges_sources(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    source_dir = tmp_path / "sources"
    entries_one = [
        {
            "word": "test",
            "senses": [{"glosses": ["gloss"], "examples": [{"text": "one"}]}],
        }
    ]
    entries_two = [
        {
            "word": "test",
            "senses": [{"glosses": ["gloss"], "examples": [{"text": "two"}]}],
        },
        {"word": "second", "senses": []},
    ]
    source_one = DummySource(source_dir, "s1", entries_one)
    source_two = DummySource(source_dir, "s2", entries_two)
    builder = Builder(cache_dir, show_progress=False, sources=[source_one, source_two])

    combined_path, count = builder._prepare_combined_entries("Serbian", "English")
    assert count == 2
    merged = [
        json.loads(line)
        for line in combined_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    merged_by_word = {entry["word"]: entry for entry in merged}
    examples = merged_by_word["test"]["senses"][0]["examples"]
    assert {"text": "one"} in examples
    assert {"text": "two"} in examples
    assert "second" in merged_by_word


def test_ensure_download_delegates_to_sources(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    source_dir = tmp_path / "sources"
    source_one = DummySource(source_dir, "s1", [{"word": "alpha"}])
    source_two = DummySource(source_dir, "s2", [{"word": "beta"}])
    builder = Builder(cache_dir, show_progress=False, sources=[source_one, source_two])

    builder.ensure_download()

    assert source_one.ensure_calls == 1
    assert source_two.ensure_calls == 1


def test_kindle_lang_code_variants(builder: Builder) -> None:
    assert builder._kindle_lang_code("sr") == "hr"
    assert builder._kindle_lang_code("en") == "en"
    assert builder._kindle_lang_code(None) == "en"

    with pytest.raises(KindleBuildError):
        builder._kindle_lang_code("sr", override="unsupported")


def test_ensure_opf_languages_updates_metadata(builder: Builder, tmp_path: Path) -> None:
    opf_path = tmp_path / "content.opf"
    opf_path.write_text(
        """
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <metadata>
    <dc:title>Old Title</dc:title>
    <opf:dc-metadata xmlns:opf="http://www.idpf.org/2007/opf" xmlns:legacy="http://purl.org/metadata/dublin_core">
      <legacy:Language>en</legacy:Language>
    </opf:dc-metadata>
    <opf:x-metadata xmlns:opf="http://www.idpf.org/2007/opf">
      <opf:DictionaryInLanguage>en</opf:DictionaryInLanguage>
      <opf:DictionaryOutLanguage>en</opf:DictionaryOutLanguage>
    </opf:x-metadata>
  </metadata>
</package>
""".strip(),
        encoding="utf-8",
    )

    builder._ensure_opf_languages(opf_path, "sr", "en-us", "New Title")

    content = opf_path.read_text(encoding="utf-8")
    assert "sr" in content
    assert "en-us" in content
    assert "New Title" in content


def test_run_kindlegen_success(builder: Builder, monkeypatch) -> None:
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    builder._run_kindlegen("/usr/bin/kindlegen", Path("/tmp/content.opf"))


def test_run_kindlegen_failure(builder: Builder, monkeypatch) -> None:
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="out", stderr="err"),
    )

    with pytest.raises(KindleBuildError) as exc:
        builder._run_kindlegen("/usr/bin/kindlegen", Path("/tmp/content.opf"))
    assert "out" in str(exc.value)
    assert "err" in str(exc.value)


class DummyCreator:
    def __init__(self, in_lang: str, out_lang: str, kaikki_file_path: str) -> None:
        self.in_lang = in_lang
        self.out_lang = out_lang
        self.kaikki_file_path = kaikki_file_path
        self.source_language = ""
        self.target_language = ""
        self.mobi_path = ""

    def create_database(self, database_path: str) -> None:  # pragma: no cover - simple no-op
        self.database_path = database_path

    def export_to_kindle(
        self,
        *,
        kindlegen_path: str,
        try_to_fix_failed_inflections: bool,
        author: str,
        title: str,
        mobi_temp_folder_path: str,
        mobi_output_file_path: str,
    ) -> None:
        temp_dir = Path(mobi_temp_folder_path)
        temp_dir.mkdir(parents=True, exist_ok=True)
        oebps = temp_dir / "OEBPS"
        oebps.mkdir(exist_ok=True)
        opf = oebps / "content.opf"
        opf.write_text(
            """
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <metadata />
</package>
""".strip(),
            encoding="utf-8",
        )

        if kindlegen_path == "trigger-fallback":
            raise FileNotFoundError("kindlegen not found")

        (oebps / "content.mobi").write_bytes(b"mobi")
        self.mobi_path = mobi_output_file_path


def test_export_one_success(builder: Builder, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("dictforge.builder.DictionaryCreator", DummyCreator)
    lang_file = tmp_path / "l.jsonl"
    lang_file.write_text("{}\n", encoding="utf-8")

    outdir = tmp_path / "out"
    outdir.mkdir()
    count = builder._export_one(
        "Serbian",
        "English",
        outdir,
        "kindlegen",
        "Title",
        "Short",
        True,
        True,
        0,
        lang_file,
        2,
        None,
    )
    assert count == 2


def test_export_one_fallback_runs_kindlegen(builder: Builder, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("dictforge.builder.DictionaryCreator", DummyCreator)
    base_file = tmp_path / "base.jsonl"
    base_file.write_text("{}\n", encoding="utf-8")

    def fake_run(kindlegen_path: str, opf_path: Path) -> None:
        mobi_dir = opf_path.parent
        (mobi_dir / "content.mobi").write_bytes(b"data")

    monkeypatch.setattr(builder, "_run_kindlegen", fake_run)

    outdir = tmp_path / "out"
    outdir.mkdir()

    count = builder._export_one(
        "Serbian",
        "English",
        outdir,
        "trigger-fallback",
        "Title",
        "Short",
        True,
        True,
        0,
        base_file,
        1,
        None,
    )
    assert count == 1
    assert (outdir / "Serbian-English.mobi").exists()


def test_build_dictionary_invokes_for_merge(builder: Builder, monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, Path, Path, int]] = []

    def fake_prepare(language: str, out_lang: str) -> tuple[Path, int]:
        data_path = tmp_path / f"{language}.jsonl"
        data_path.write_text("{}\n", encoding="utf-8")
        return (data_path, 3) if language == "Serbian" else (data_path, 1)

    def fake_export(
        language: str,
        out_lang: str,
        outdir: Path,
        kindlegen_path: str,
        title: str,
        shortname: str,
        include_pos: bool,
        try_fix_inflections: bool,
        max_entries: int,
        language_file: Path,
        entry_count: int,
        kindle_lang_override: str | None = None,
    ) -> int:
        calls.append((language, out_lang, outdir, language_file, entry_count))
        return entry_count

    monkeypatch.setattr(builder, "_prepare_combined_entries", fake_prepare)
    monkeypatch.setattr(builder, "_export_one", fake_export)

    counts = builder.build_dictionary(
        in_langs=["Serbian", "Croatian"],
        out_lang="English",
        title="Title",
        shortname="Short",
        outdir=tmp_path,
        kindlegen_path="kindle",
        include_pos=True,
        try_fix_inflections=True,
        max_entries=0,
    )

    assert counts == {"Serbian": 3, "Croatian": 1}
    assert calls[0][0] == "Serbian"
    assert calls[0][4] == 3
    assert calls[1][0] == "Croatian"
    assert calls[1][4] == 1


def test_kaikki_parse_error_extracts_excerpt(tmp_path: Path) -> None:
    sample_path = tmp_path / "response.html"
    sample_path.write_text("<html><body><p>Error</p></body></html>", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError) as exc:
        json.loads("not json")
    error = KaikkiParseError(sample_path, exc.value)
    assert "Failed to parse Kaikki JSON" in str(error)
    assert error.excerpt == ["Error"]
