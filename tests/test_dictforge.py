from pathlib import Path

import pytest
from click.testing import CliRunner

from dictforge import __version__
from dictforge.builder import Builder, KindleBuildError
from dictforge.main import cli


def test_version():
    assert __version__


def test_version_option():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_kindle_lang_override_accepts_supported(tmp_path: Path) -> None:
    builder = Builder(tmp_path)
    assert builder._kindle_lang_code("sr", override="hr") == "hr"


def test_kindle_lang_override_rejects_unsupported(tmp_path: Path) -> None:
    builder = Builder(tmp_path)
    with pytest.raises(KindleBuildError):
        builder._kindle_lang_code("sr", override="xx")
