from dictforge import __version__
from dictforge.main import cli
from click.testing import CliRunner


def test_version():
    assert __version__


def test_version_option():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
