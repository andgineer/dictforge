from __future__ import annotations

import json
from pathlib import Path

import pytest

from dictforge.builder import Builder, KindleBuildError


class StubKaikkiClient:
    def __init__(self, datasets: dict[str, Path]) -> None:
        self.datasets = datasets
        self.closed = False
        self.filtered_calls: list[str] = []

    def ensure_filtered_language(self, language: str) -> tuple[Path, int]:
        self.filtered_calls.append(language)
        try:
            path = self.datasets[language]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"No dataset for {language}") from exc
        count = sum(1 for _ in path.open("r", encoding="utf-8"))
        return path, count

    def ensure_translated_glosses(
        self, base_path: Path, source_lang: str, target_lang: str
    ) -> Path:  # noqa: ARG002
        return base_path

    def close(self) -> None:
        self.closed = True


class StubTatoeba:
    def __init__(self, mapping: dict[str, tuple[list[tuple[str, str]], str | None]]) -> None:
        self.mapping = mapping

    def vocabulary(self) -> set[str]:
        return {key for key in self.mapping}

    def get_examples_for(self, word: str) -> list[tuple[str, str]]:
        entry = self.mapping.get(word.lower())
        if not entry:
            return []
        examples, _ = entry
        return examples

    def get_gloss_for(self, word: str) -> str | None:
        entry = self.mapping.get(word.lower())
        if not entry:
            return None
        _, gloss = entry
        return gloss


class DummyCreator:
    def __init__(self, in_lang: str, out_lang: str, kaikki_file_path: str) -> None:
        self.in_lang = in_lang
        self.out_lang = out_lang
        self.kaikki_file_path = kaikki_file_path
        self.source_language = ""
        self.target_language = ""

    def create_database(self, database_path: str) -> None:  # pragma: no cover - trivial
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
        (oebps / "content.opf").write_text("<package><metadata/></package>", encoding="utf-8")
        Path(mobi_output_file_path).write_bytes(b"mobi")


@pytest.fixture
def builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Builder:
    sample_path = tmp_path / "english.jsonl"
    sample_path.write_text(
        json.dumps(
            {
                "word": "House",
                "language": "English",
                "senses": [
                    {
                        "glosses": [],
                        "examples": [],
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    stub = StubKaikkiClient({"English": sample_path})
    b = Builder(cache_dir=tmp_path, show_progress=False)
    b.kaikki = stub
    monkeypatch.setattr("dictforge.builder.DictionaryCreator", DummyCreator)
    return b


def test_prepare_dataset_merges_tatoeba(tmp_path: Path) -> None:
    sample_path = tmp_path / "english.jsonl"
    sample_path.write_text(
        json.dumps(
            {
                "word": "House",
                "language": "English",
                "senses": [
                    {
                        "glosses": [],
                        "examples": [],
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    builder = Builder(cache_dir=tmp_path, show_progress=False)
    builder.kaikki = StubKaikkiClient({"English": sample_path})

    tatoeba = StubTatoeba(
        {
            "house": ([("House", "Дом")], "дом"),
        }
    )

    combined_path, stats = builder._prepare_dataset(  # type: ignore[attr-defined]
        source_langs=["English"],
        primary_language="English",
        out_lang="Russian",
        normalize_serbian=False,
        tatoeba=tatoeba,
        max_entries=0,
    )

    content = [json.loads(line) for line in combined_path.read_text(encoding="utf-8").splitlines()]
    assert content[0]["word"] == "House"
    sense = content[0]["senses"][0]
    assert sense["glosses"] == ["дом"]
    assert sense["examples"][0] == {"text": "House", "translation": "Дом"}

    assert stats["kaikki_total"] == 1
    assert stats["tatoeba_total"] == 1
    assert stats["enriched_from_tatoeba"] == 1
    assert stats["final_headword_count"] == 1


def test_export_one_uses_combined_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    combined = tmp_path / "combined.jsonl"
    combined.write_text(
        json.dumps({"word": "Test", "language": "English", "senses": []}) + "\n", encoding="utf-8"
    )

    builder = Builder(cache_dir=tmp_path, show_progress=False)
    builder.kaikki = StubKaikkiClient({})

    monkeypatch.setattr(
        builder,
        "_prepare_dataset",
        lambda **kwargs: (
            combined,
            {  # type: ignore[misc]
                "kaikki_total": 1,
                "kaikki_unique": 1,
                "tatoeba_total": 0,
                "tatoeba_unique": 0,
                "overlap": 0,
                "enriched_from_tatoeba": 0,
                "final_headword_count": 1,
            },
        ),
    )

    monkeypatch.setattr("dictforge.builder.DictionaryCreator", DummyCreator)
    monkeypatch.setattr(builder, "_run_kindlegen", lambda *args, **kwargs: None)

    outdir = tmp_path / "out"
    outdir.mkdir()

    count = builder._export_one(
        "English",
        "Russian",
        outdir,
        "kindlegen",
        "Title",
        "Short",
        True,
        True,
        0,
        None,
    )

    assert count == 1
    mobi = outdir / "English-Russian.mobi"
    assert mobi.exists()


def test_build_dictionary_closes_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    combined = tmp_path / "combined.jsonl"
    combined.write_text(
        json.dumps({"word": "Test", "language": "English", "senses": []}) + "\n", encoding="utf-8"
    )

    builder = Builder(cache_dir=tmp_path, show_progress=False)
    stub = StubKaikkiClient({})
    builder.kaikki = stub

    monkeypatch.setattr(
        builder,
        "_prepare_dataset",
        lambda **kwargs: (
            combined,
            {  # type: ignore[misc]
                "kaikki_total": 1,
                "kaikki_unique": 1,
                "tatoeba_total": 0,
                "tatoeba_unique": 0,
                "overlap": 0,
                "enriched_from_tatoeba": 0,
                "final_headword_count": 1,
            },
        ),
    )
    monkeypatch.setattr("dictforge.builder.DictionaryCreator", DummyCreator)
    monkeypatch.setattr(builder, "_run_kindlegen", lambda *args, **kwargs: None)

    outdir = tmp_path / "out"
    outdir.mkdir()

    counts = builder.build_dictionary(
        in_langs=["English"],
        out_lang="Russian",
        title="Title",
        shortname="Short",
        outdir=outdir,
        kindlegen_path="kindle",
        include_pos=False,
        try_fix_inflections=True,
        max_entries=0,
        kindle_lang_override=None,
    )

    assert counts == {"English": 1}
    assert stub.closed is True


def test_run_kindlegen_failure(tmp_path: Path) -> None:
    builder = Builder(cache_dir=tmp_path, show_progress=False)
    opf_path = tmp_path / "content.opf"
    opf_path.parent.mkdir(parents=True, exist_ok=True)
    opf_path.write_text("<package><metadata/></package>", encoding="utf-8")

    with pytest.raises(KindleBuildError):
        builder._run_kindlegen("", opf_path)
