from pathlib import Path

import pytest
from click.testing import CliRunner

from dictforge import __version__
from dictforge.builder import KaikkiDownloadError, KindleBuildError
from dictforge.kindle import kindle_lang_code
from dictforge.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _base_config(tmp_path: Path) -> dict[str, object]:
    return {
        "default_out_lang": "English",
        "merge_in_langs": "Croatian",
        "include_pos": False,
        "try_fix_inflections": False,
        "cache_dir": str(tmp_path / "cache"),
        "kindlegen_path": "",
    }


def test_version() -> None:
    assert __version__


def test_version_option(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_requires_input_language(runner: CliRunner) -> None:
    result = runner.invoke(cli, [])
    assert result.exit_code != 0
    assert "Input language is required" in result.output


def test_cli_success_path(monkeypatch, runner: CliRunner, tmp_path: Path) -> None:
    config = _base_config(tmp_path)
    monkeypatch.setattr("dictforge.main.load_config", lambda: config)
    monkeypatch.setattr("dictforge.main.guess_kindlegen_path", lambda: "/usr/bin/kindlegen")
    monkeypatch.setattr(
        "dictforge.main.make_defaults",
        lambda in_lang, out_lang: {
            "title": "Title",
            "shortname": "Short",
            "outdir": str(tmp_path / "out"),
            "in_code": "sr",
            "out_code": "en",
        },
    )

    calls: dict[str, object] = {}

    monkeypatch.setattr("dictforge.main.guess_kindlegen_path", lambda: "/usr/bin/kindlegen")

    class DummyBuilder:
        def __init__(
            self,
            cache_dir: Path,
            *,
            show_progress: bool | None = None,
            reset_cache: bool = False,
        ) -> None:
            calls["cache_dir"] = cache_dir
            calls["show_progress"] = show_progress
            calls["reset_cache"] = reset_cache

        def ensure_download_dirs(self, force: bool = False) -> None:
            calls["ensure_download_dirs"] = force

        def build_dictionary(self, **kwargs):  # type: ignore[no-untyped-def]
            calls["build_kwargs"] = kwargs
            return {"Serbo-Croatian": 5, "Croatian": 2}

    monkeypatch.setattr("dictforge.main.Builder", DummyBuilder)

    result = runner.invoke(cli, ["sr"])

    assert result.exit_code == 0
    assert "DONE" in result.output
    assert "extra Croatian" in result.output

    assert isinstance(calls["cache_dir"], Path)
    assert calls["ensure_download_dirs"] is False
    build_kwargs = calls["build_kwargs"]
    assert build_kwargs["in_langs"] == ["Serbo-Croatian", "Croatian"]
    assert build_kwargs["title"] == "Title"
    assert build_kwargs["outdir"] == Path(tmp_path / "out")
    assert build_kwargs["export_format"] == "mobi"
    assert build_kwargs["export_options"]["kindlegen_path"] == "/usr/bin/kindlegen"


def test_cli_reset_cache_triggers_cleanup(monkeypatch, runner: CliRunner, tmp_path: Path) -> None:
    config = _base_config(tmp_path)
    monkeypatch.setattr("dictforge.main.load_config", lambda: config)
    monkeypatch.setattr("dictforge.main.guess_kindlegen_path", lambda: "/usr/bin/kindlegen")
    monkeypatch.setattr(
        "dictforge.main.make_defaults",
        lambda *_: {
            "title": "Title",
            "shortname": "Short",
            "outdir": str(tmp_path / "out"),
            "in_code": "sr",
            "out_code": "en",
        },
    )

    calls: dict[str, object] = {}

    class DummyBuilder:
        def __init__(
            self,
            cache_dir: Path,
            *,
            show_progress: bool | None = None,
            reset_cache: bool = False,
        ) -> None:
            calls["cache_dir"] = cache_dir
            calls["show_progress"] = show_progress
            calls["reset_cache"] = reset_cache

        def ensure_download_dirs(self, force: bool = False) -> None:
            calls["ensure_download_dirs"] = force

        def build_dictionary(self, **_: object) -> dict[str, int]:  # pragma: no cover - simple stub
            return {"Serbo-Croatian": 5}

    monkeypatch.setattr("dictforge.main.Builder", DummyBuilder)

    result = runner.invoke(cli, ["--reset-cache", "sr"])

    assert result.exit_code == 0
    assert calls["ensure_download_dirs"] is True


def test_cli_download_error(monkeypatch, runner: CliRunner, tmp_path: Path) -> None:
    config = _base_config(tmp_path)
    monkeypatch.setattr("dictforge.main.load_config", lambda: config)
    monkeypatch.setattr("dictforge.main.guess_kindlegen_path", lambda: "/usr/bin/kindlegen")
    monkeypatch.setattr(
        "dictforge.main.make_defaults",
        lambda *_: {
            "title": "Title",
            "shortname": "Short",
            "outdir": str(tmp_path / "out"),
            "in_code": "sr",
            "out_code": "en",
        },
    )

    class FailingBuilder:
        def __init__(
            self,
            cache_dir: Path,
            *,
            show_progress: bool | None = None,
            reset_cache: bool = False,
        ) -> None:  # pragma: no cover - trivial
            self.cache_dir = cache_dir
            self.show_progress = show_progress
            self.reset_cache = reset_cache

        def ensure_download_dirs(self, force: bool = False) -> None:  # pragma: no cover
            return

        def build_dictionary(self, **_: object) -> None:
            raise KaikkiDownloadError("network down")

    monkeypatch.setattr("dictforge.main.Builder", FailingBuilder)

    result = runner.invoke(cli, ["sr"])
    assert result.exit_code == 1
    assert "network down" in result.output


def test_cli_kindlegen_missing(monkeypatch, runner: CliRunner, tmp_path: Path) -> None:
    config = _base_config(tmp_path)
    monkeypatch.setattr("dictforge.main.load_config", lambda: config)
    monkeypatch.setattr("dictforge.main.guess_kindlegen_path", lambda: "")

    result = runner.invoke(cli, ["sr"])
    assert result.exit_code == 1
    assert "kindlegen not found" in result.output


def test_cli_init_updates_config(monkeypatch, runner: CliRunner, tmp_path: Path) -> None:
    config = _base_config(tmp_path)
    saved: dict[str, object] = {}

    monkeypatch.setattr("dictforge.main.load_config", lambda: config.copy())
    monkeypatch.setattr("dictforge.main.guess_kindlegen_path", lambda: "/detected/kindlegen")

    def fake_save(data: dict[str, object]) -> None:
        saved.update(data)

    monkeypatch.setattr("dictforge.main.save_config", fake_save)

    result = runner.invoke(cli, ["init"], input="Spanish\n\n")
    assert result.exit_code == 0
    assert saved["default_out_lang"] == "Spanish"
    assert saved["kindlegen_path"] == "/detected/kindlegen"
    assert "Saved" in result.output


def test_kindle_lang_override_accepts_supported(tmp_path: Path) -> None:
    assert kindle_lang_code("sr", override="hr") == "hr"


def test_kindle_lang_override_rejects_unsupported(tmp_path: Path) -> None:
    with pytest.raises(KindleBuildError):
        kindle_lang_code("sr", override="xx")


def test_cli_init_hints_when_kindlegen_missing(
    monkeypatch, runner: CliRunner, tmp_path: Path
) -> None:
    config = _base_config(tmp_path)
    saved: dict[str, object] = {}

    monkeypatch.setattr("dictforge.main.load_config", lambda: config.copy())
    monkeypatch.setattr("dictforge.main.guess_kindlegen_path", lambda: "")

    def fake_save(data: dict[str, object]) -> None:
        saved.update(data)

    monkeypatch.setattr("dictforge.main.save_config", fake_save)

    path_input = str(tmp_path / "Kindle Previewer" / "kindlegen")
    result = runner.invoke(cli, ["init"], input=f"\n{path_input}\n")

    assert result.exit_code == 0
    assert "Common locations include" in result.output
    assert "Kindle Previewer 3.app" in result.output
    assert saved["kindlegen_path"] == path_input
