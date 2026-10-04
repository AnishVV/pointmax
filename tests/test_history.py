import csv
from datetime import date

import pytest
from synthetic import FakeBackend, pinned_settings, scenario
from test_cli import fake_search, home, runner  # noqa: F401  (fixtures)

from pointmax import cli, config
from pointmax.history import RESULT_COLUMNS, History, RunFilter
from pointmax.models import Cabin
from pointmax.planner import plan as pl
from pointmax.rank import filters as flt


def query(**kw):
    base = dict(
        homes=["AUS", "DFW"],
        dest="LHR",
        start=date(2026, 12, 22),
        end=date(2026, 12, 24),
        filters=flt.Filters(cabin=Cabin.BUSINESS),
        yes=True,
    )
    return pl.Query(**(base | kw))


@pytest.fixture
async def searched():
    q = query()
    res = await pl.Planner(FakeBackend(scenario()), pinned_settings()).run(q)
    return q, res, flt.sort_itineraries(res.itineraries)


def test_record_round_trips_query_and_results(searched):
    q, res, ranked = searched
    h = History(":memory:", clock=lambda: "2026-10-03T12:00:00-05:00")
    run_id = h.record(q, res, ranked, sort="eff")
    run = h.run(run_id)
    assert run["origins"] == "AUS,DFW" and run["dest"] == "LHR"
    assert (run["depart_start"], run["depart_end"]) == ("2026-12-22", "2026-12-24")
    assert run["cabin"] == "business" and run["pax"] == 1 and run["status"] == "ok"
    assert run["n_results"] == len(ranked)
    assert run["best_eff_usd"] == pytest.approx(ranked[0].value.c_eff, abs=0.01)
    assert run["best_program"] == "Air Canada Aeroplan"
    assert run["searches"] == sum(r.tasks for r in res.rings)
    back = h.itineraries(run_id)
    assert [i.model_dump() for i in back] == [i.model_dump() for i in ranked]


def test_flattened_result_row(searched):
    q, res, ranked = searched
    h = History(":memory:")
    run_id = h.record(q, res, ranked)
    row = h._db.execute(
        f"SELECT {', '.join(RESULT_COLUMNS)} FROM results WHERE run_id = ? AND rank = 1",
        (run_id,),
    ).fetchone()
    top = dict(row)
    assert top["route"].endswith("→[IAH]→LHR") and top["gateway"] == "IAH" and top["ring"] == 1
    assert top["program"] == "Air Canada Aeroplan" and top["miles"] == 60000
    assert top["depart_date"] == "2026-12-23" and top["flights"] == "UA900"
    assert top["positioning_usd"] > 0 and top["cpp"] is not None and top["funding"]
    assert top["effective_usd"] == pytest.approx(
        top["positioning_usd"] + 1278, abs=0.01
    )  # 60k Aeroplan via Chase @2.0c + $78 taxes, plus positioning


def test_filters(searched):
    q, res, ranked = searched
    clock = iter(["2026-09-30T09:00:00", "2026-10-02T09:00:00", "2026-10-03T09:00:00"])
    h = History(":memory:", clock=lambda: next(clock))
    a = h.record(q, res, ranked)
    b = h.record(query(homes=["AUS"], dest="NRT", filters=flt.Filters()), res, [])
    c = h.record(query(homes=["DFW"]), res, ranked[:1])
    ids = lambda **kw: [r["run_id"] for r in h.runs(RunFilter(**kw))]  # noqa: E731
    assert ids() == [c, b, a]
    assert ids(origin="dfw") == [c, a]
    assert ids(origin="AUS") == [b, a]  # "AUS" must not match a substring of another code
    assert ids(dest="NRT") == [b]
    assert ids(cabin="business") == [c, a]
    assert ids(program="alaska") == [a]
    assert ids(since="2026-10-02") == [c, b]
    assert ids(limit=1) == [c]


def test_export_results_and_runs(searched, tmp_path):
    q, res, ranked = searched
    h = History(":memory:")
    h.record(q, res, ranked)
    h.record(q, res, [])
    out = tmp_path / "res.csv"
    assert h.export_csv(out) == len(ranked)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["dest"] == "LHR" and rows[0]["result_dest"] == "LHR"
    assert rows[0]["program"] == "Air Canada Aeroplan" and rows[0]["rank"] == "1"
    aeroplan = sum(i.main.program == "Air Canada Aeroplan" for i in ranked)
    assert 0 < aeroplan < len(ranked)
    assert h.export_csv(out, RunFilter(program="aeroplan")) == aeroplan
    assert h.export_csv(out, runs_only=True) == 2
    assert {r["n_results"] for r in csv.DictReader(out.open())} == {str(len(ranked)), "0"}


def test_delete_cascades_to_results_and_return_leg(searched):
    q, res, ranked = searched
    h = History(":memory:")
    out = h.record(q, res, ranked)
    h.record(q, res, ranked, leg="return", parent_id=out)
    assert h.delete(out) and h.runs() == []
    assert h._db.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0
    assert not h.delete(out)


# ---- CLI ---------------------------------------------------------------------------------

SEARCH = ["search", "AUS,DFW", "LHR", "--date", "2026-12-23", "--cabin", "business", "--yes"]


def test_search_is_logged_and_history_commands(fake_search, home):  # noqa: F811
    result = runner.invoke(cli.app, [*SEARCH, "--return", "2027-01-03"], terminal_width=200)
    assert result.exit_code == 0, result.output
    assert config.history_path().exists()
    h = History(config.history_path())
    out, back = sorted(h.runs(), key=lambda r: r["run_id"])
    h.close()
    assert out["leg"] == "outbound" and back["leg"] == "return"
    assert back["parent_id"] == out["run_id"] and back["dest"] == "AUS"

    listed = runner.invoke(cli.app, ["history", "list", "--to", "LHR"], terminal_width=200)
    assert listed.exit_code == 0 and "AUS/DFW→LHR" in listed.output
    assert "(return)" not in listed.output

    shown = runner.invoke(cli.app, ["history", "show", str(out["run_id"])], terminal_width=200)
    assert shown.exit_code == 0 and "[IAH]→LHR" in shown.output
    detail = runner.invoke(cli.app, ["show", "1"], terminal_width=200)
    assert detail.exit_code == 0 and "UA900" in detail.output

    csv_path = home / "h.csv"
    exp = runner.invoke(cli.app, ["history", "export", str(csv_path), "--cabin", "business"])
    assert exp.exit_code == 0 and csv_path.exists()
    assert runner.invoke(cli.app, ["history", "show", "999"]).exit_code == 1
    assert runner.invoke(cli.app, ["history", "delete", str(out["run_id"])]).exit_code == 0
    assert "No searches recorded" in runner.invoke(cli.app, ["history", "list"]).output


def test_history_failure_does_not_break_search(fake_search, monkeypatch):  # noqa: F811
    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(cli, "History", boom)
    result = runner.invoke(cli.app, SEARCH, terminal_width=200)
    assert result.exit_code == 0 and "Could not save to search history" in result.output


def test_history_bad_filters():
    assert runner.invoke(cli.app, ["history", "list", "--since", "yesterday"]).exit_code != 0
    assert runner.invoke(cli.app, ["history", "list", "--cabin", "steerage"]).exit_code != 0
