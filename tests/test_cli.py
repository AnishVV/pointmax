from typer.testing import CliRunner

from pointmax import __version__
from pointmax.cli import app

runner = CliRunner()


def test_help_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("login", "status", "search", "show", "config", "cache"):
        assert cmd in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_unimplemented_command_exits_cleanly():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 2
