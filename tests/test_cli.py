import json

import pytest
from synthetic import FakeBackend, scenario
from typer.testing import CliRunner

from pointmax import __version__, cli, config
from pointmax.planner.plan import Planner

runner = CliRunner()


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("POINTMAX_HOME", str(tmp_path))
    monkeypatch.setenv("COLUMNS", "200")
    return tmp_path


@pytest.fixture
def fake_search(monkeypatch):
    async def run(q, settings, *, verbose, save_raw=None):
        planner = Planner(FakeBackend(scenario()), settings, echo=cli.console.print)
        cli._live["planner"] = planner
        return planner, await planner.run(q)

    monkeypatch.setattr(cli, "_run_search", run)


def test_help_lists_all_commands():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("login", "status", "search", "show", "config", "cache"):
        assert cmd in result.output


def test_version():
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0 and __version__ in result.output


def test_status_without_session_explains():
    result = runner.invoke(cli.app, ["status"])
    assert result.exit_code == 1 and "pointmax login" in result.output


def test_search_table_ring_table_and_show(fake_search, home):
    args = [
        "search",
        "AUS,DFW",
        "LHR",
        "--date",
        "2026-12-23",
        "--flex",
        "1",
        "--cabin",
        "business",
        "--yes",
        "--rings",
        "2",
    ]
    result = runner.invoke(cli.app, args, terminal_width=200)
    assert result.exit_code == 0, result.output
    assert "[IAH]→LHR" in result.output and "Ring tradeoff" in result.output
    assert "Aeroplan" in result.output
    shown = runner.invoke(cli.app, ["show", "1"], terminal_width=200)
    assert shown.exit_code == 0 and "funding:" in shown.output and "UA900" in shown.output
    assert runner.invoke(cli.app, ["show", "99"]).exit_code == 1


def test_search_json_export(fake_search, home):
    out = home / "out.json"
    result = runner.invoke(
        cli.app,
        [
            "search",
            "AUS,DFW",
            "LHR",
            "--date",
            "2026-12-23",
            "--cabin",
            "business",
            "--yes",
            "--json",
            str(out),
        ],
        terminal_width=200,
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert data["itineraries"] and data["itineraries"][0]["value"]["c_eff"] > 0


def test_search_bad_date_and_cabin(fake_search):
    assert runner.invoke(cli.app, ["search", "AUS", "LHR", "--date", "tomorrow"]).exit_code != 0
    bad = ["search", "AUS", "LHR", "--date", "2026-12-23", "--cabin", "steerage"]
    assert runner.invoke(cli.app, bad).exit_code != 0


def test_show_without_previous_search():
    result = runner.invoke(cli.app, ["show", "1"])
    assert result.exit_code == 1 and "No previous search" in result.output


def test_config_prints_and_creates_default(home):
    result = runner.invoke(cli.app, ["config"], terminal_width=200)
    assert result.exit_code == 0 and "home = " in result.output
    assert config.config_path().exists()


def test_cache_stats_and_clear():
    assert "0 searches" in runner.invoke(cli.app, ["cache"]).output
    assert "Cleared 0" in runner.invoke(cli.app, ["cache", "--clear"]).output
