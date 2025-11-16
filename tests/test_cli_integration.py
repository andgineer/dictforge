import gzip
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from dictforge.main import cli


class RecordingCreator:
    instances: list["RecordingCreator"] = []

    def __init__(
        self, source_language: str, target_language: str, *, kaikki_file_path: str
    ) -> None:
        self.source_language = source_language
        self.target_language = target_language
        self.kaikki_file_path = Path(kaikki_file_path)
        self.database_path: Path | None = None
        self.export_args: dict[str, Any] | None = None
        RecordingCreator.instances.append(self)

    def create_database(self, database_path: str) -> None:
        self.database_path = Path(database_path)

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
        oebps = temp_dir / "OEBPS"
        oebps.mkdir(parents=True, exist_ok=True)
        # Minimal OPF payload so Builder's success path runs without fallback.
        (oebps / "content.opf").write_text("<package></package>", encoding="utf-8")
        (oebps / "content.mobi").write_bytes(b"mobi")
        self.export_args = {
            "kindlegen_path": kindlegen_path,
            "try_fix": try_to_fix_failed_inflections,
            "author": author,
            "title": title,
            "temp_path": Path(mobi_temp_folder_path),
            "output_path": Path(mobi_output_file_path),
        }


def _fake_config(tmp_path: Path) -> dict[str, object]:
    return {
        "default_out_lang": "English",
        "merge_in_langs": "",
        "include_pos": False,
        "try_fix_inflections": False,
        "cache_dir": str(tmp_path / "cache"),
        "kindlegen_path": "",
    }


@contextmanager
def _noop_progress() -> Any:
    def advance(_: int) -> None:
        return None

    yield advance


def test_cli_filters_and_invokes_kindlegen(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    cache_dir = tmp_path / "cache"
    raw_dir = tmp_path / "downloads"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "raw-wiktextract-data.jsonl.gz"

    RecordingCreator.instances.clear()

    raw_entries = [
        {
            "language": "Serbian",
            "word": "priča",
            "senses": [
                {"glosses": ["story"], "examples": [{"text": "Ovo je priča."}]},
            ],
        },
        {
            "language": "Serbian",
            "word": "brod",
            "senses": [
                {"glosses": ["ship"], "examples": [{"text": "Veliki brod."}]},
            ],
        },
        {"language": "English", "word": "story", "senses": []},
    ]
    with gzip.open(raw_path, "wt", encoding="utf-8") as fh:
        for entry in raw_entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Create fake kindlegen executable
    fake_kindlegen = tmp_path / "fake_kindlegen"
    fake_kindlegen.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_kindlegen.chmod(0o755)

    config = _fake_config(tmp_path)
    output_dir = tmp_path / "output"
    defaults = {
        "title": "Serbian → English (Test)",
        "shortname": "SR→EN",
        "outdir": str(output_dir),
        "in_code": "sr",
        "out_code": "en",
    }

    monkeypatch.setattr("dictforge.main.load_config", lambda: config)
    monkeypatch.setattr("dictforge.main.guess_kindlegen_path", lambda: str(fake_kindlegen))
    monkeypatch.setattr("dictforge.main.make_defaults", lambda *_: defaults)
    monkeypatch.setattr("dictforge.export_mobi.DictionaryCreator", RecordingCreator)
    monkeypatch.setattr(
        "dictforge.source_kaikki.KaikkiSource._ensure_raw_dump",
        lambda self: raw_path,
    )

    def fake_progress_bar(**_: Any) -> Any:  # noqa: ANN001
        return _noop_progress()

    monkeypatch.setattr("dictforge.progress_bar.progress_bar", fake_progress_bar)

    result = runner.invoke(cli, ["--kindlegen-path", str(fake_kindlegen), "Serbian", "English"])

    assert result.exit_code == 0, result.output
    assert "Starting build: Serbian → English" in result.output

    # Validate data forwarded to the dictionary creator (recorded via import patch).
    assert RecordingCreator.instances, "DictionaryCreator was not instantiated"
    creator = RecordingCreator.instances[-1]
    assert creator.source_language == "hr"
    assert creator.target_language in {"en", "en-us"}
    assert "filtered" in creator.kaikki_file_path.parts

    filtered_entries = [
        json.loads(line)
        for line in creator.kaikki_file_path.read_text(encoding="utf-8").splitlines()
    ]
    filtered_words = {entry["word"] for entry in filtered_entries}
    assert filtered_words == {"priča", "brod"}
    assert any(
        sense.get("examples") and sense["examples"][0]["text"] == "Ovo je priča."
        for entry in filtered_entries
        for sense in entry.get("senses", [])
    )

    assert creator.export_args is not None
    assert creator.export_args["kindlegen_path"] == str(fake_kindlegen)
    assert creator.export_args["output_path"].name.endswith("Serbian-English.mobi")
    assert creator.export_args["title"] == "Serbian → English (Test)"
    assert creator.export_args["try_fix"] is False
