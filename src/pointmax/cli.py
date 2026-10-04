"""Typer app: login, status, search, show, history, config, cache."""

import asyncio
import json
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path

import typer
from rich.console import Console

from pointmax import __version__, config
from pointmax.cache import Cache
from pointmax.history import History, RunFilter
from pointmax.models import Cabin, Itinerary
from pointmax.planner.plan import Planner, Query, SearchResult
from pointmax.rank import filters as flt
from pointmax.ratelimit import RateLimiter
from pointmax.render import export, table
from pointmax.sources.pointsyeah import session as sess
from pointmax.sources.pointsyeah.client import PointsYeahClient
from pointmax.sources.pointsyeah.source import PointsYeahBackend

app = typer.Typer(
    help="Find the cheapest-in-real-terms award flight, including positioning legs.",
    no_args_is_help=True,
)
console = Console()
_live: dict[str, Planner] = {}  # the running planner, for a clean Ctrl-C


def _version(value: bool) -> None:
    if value:
        typer.echo(f"pointmax {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Print the version."
    ),
) -> None:
    """pointmax command-line interface."""


def _fail(msg: str, code: int = 1) -> None:
    console.print(f"[red]{msg}[/red]")
    raise typer.Exit(code)


# ---- login / status --------------------------------------------------------------------


@app.command()
def login(
    from_chrome: bool = typer.Option(
        False, "--from-chrome", help="Import cookies from your everyday Chrome instead."
    ),
) -> None:
    """One-time PointsYeah SSO login (opens Chrome; you finish Google/Apple sign-in yourself)."""
    try:
        if from_chrome:
            data = asyncio.run(sess.login_from_chrome())
        else:
            console.print("Opening Chrome. Sign in to PointsYeah; this window closes itself.")
            data = asyncio.run(sess.login_browser())
    except sess.SessionError as e:
        hint = (
            "" if from_chrome else "\nTry `pointmax login --from-chrome` if Google blocks sign-in."
        )
        _fail(f"{e}{hint}")
        return
    except Exception as e:  # browser launch failures, missing Chrome ...
        hint = "" if from_chrome else "\nTry `pointmax login --from-chrome`."
        _fail(f"Login failed: {type(e).__name__}: {e}{hint}")
        return
    path = sess.save_session(data)
    console.print(f"[green]Signed in.[/green] Session saved to {path} (mode 600).")


@app.command()
def status() -> None:
    """Session, plan limits, rate budget left, cache size."""
    try:
        data = sess.load_session()
    except sess.SessionError as e:
        _fail(str(e))
        return
    try:
        info = asyncio.run(sess.check_session(data))
    except Exception as e:
        _fail(f"Could not reach PointsYeah: {e}")
        return
    state = "[green]authenticated[/green]" if info.authenticated else "[red]expired[/red]"
    console.print(f"Session:      {state}")
    console.print(f"Session age:  {data.age_hours:.1f} h")
    console.print(
        f"Key section:  {sess.mask(info.request_key_section or data.request_key_section)}"
    )
    mdr = info.max_date_range or data.max_date_range
    console.print(f"Plan limits:  max date range {mdr if mdr else 'unknown'} days (one-way)")
    limiter = RateLimiter(db_path=config.cache_path())
    for limit, span, left in limiter.remaining():
        console.print(f"Rate budget:  {left}/{limit} left in {span:.0f}s window")
    limiter.close()
    cache = Cache(config.cache_path())
    st = cache.stats()
    console.print(f"Cache:        {st['searches']} searches, {st['options']} options")
    cache.close()
    if not info.authenticated:
        raise typer.Exit(1)


# ---- search ----------------------------------------------------------------------------


def _parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise typer.BadParameter(f"{text!r} is not YYYY-MM-DD") from None


def _origins(arg: str, settings: config.Settings) -> list[str]:
    if arg.lower() == "home":
        return settings.home
    return [a.strip().upper() for a in arg.split(",") if a.strip()]


async def _run_search(
    q: Query, settings: config.Settings, *, verbose: bool, save_raw: Path | None = None
) -> tuple[Planner, SearchResult]:
    cache = Cache(config.cache_path(), settings.cache_ttl_hours)
    limiter = RateLimiter(db_path=config.cache_path())
    data = await sess.ensure_session()
    sink = None
    raw_file = None
    if save_raw is not None:
        save_raw.mkdir(parents=True, exist_ok=True)
        raw_file = (save_raw / "traffic.jsonl").open("a", encoding="utf-8")
        raw_file.write(json.dumps(await sess.auth_exchange(data)) + "\n")

        def sink(entry: dict) -> None:
            raw_file.write(json.dumps(entry) + "\n")
            raw_file.flush()

    http_client = PointsYeahClient(
        data,
        limiter,
        on_exchange=sink,
        refresh=lambda: sess.silent_refresh(data),
        on_progress=(lambda p: console.print(f"  [dim]{p}[/dim]")) if verbose else None,
    )
    backend = PointsYeahBackend(http_client, cache, data.max_date_range)

    async def ask(prompt: str) -> bool:
        return typer.confirm(prompt, default=True)

    planner = Planner(backend, settings, echo=console.print, ask=ask)
    _live["planner"] = planner
    try:
        res = await planner.run(q)
    finally:
        if raw_file:
            raw_file.close()
        await http_client.aclose()
        limiter.close()
        cache.close()
    if backend.failures:
        res.warnings.extend(f"Search failed: {m}" for m in backend.failures)
    return planner, res


def _search_one(
    q: Query,
    settings: config.Settings,
    sort: str,
    top: int,
    verbose: bool,
    label: str,
    save_raw: Path | None = None,
    *,
    leg: str = "outbound",
    parent_id: int | None = None,
) -> tuple[list[Itinerary], int | None] | None:
    """Run, render and log one search. Returns the ranked results and the history run id."""
    console.rule(label)
    _live.pop("planner", None)
    status = "ok"
    try:
        _, res = asyncio.run(_run_search(q, settings, verbose=verbose, save_raw=save_raw))
    except sess.SessionError as e:
        console.print(f"[red]{e}[/red]")
        live = _live.get("planner")
        if live is None:  # no session at all: nothing to show
            return None
        res = live.partial
        status = "session_error"
    except KeyboardInterrupt:
        status = "interrupted"
        console.print(
            "\n[yellow]Interrupted. Showing what was found so far (it is all cached).[/yellow]"
        )
        live = _live.get("planner")
        res = live.partial if live else SearchResult([], [])
    its = [i for i in res.itineraries if i.value]
    from pointmax.rank import value as val

    val.apply_savings(its)
    ranked = flt.sort_itineraries(its, sort)
    table.render_results(console, res, ranked, top)
    return ranked, _log_run(q, res, ranked, sort, leg, parent_id, status)


def _log_run(
    q: Query,
    res: SearchResult,
    ranked: list[Itinerary],
    sort: str,
    leg: str,
    parent_id: int | None,
    status: str,
) -> int | None:
    """Append the run to the search history. A history failure never loses the search."""
    try:
        h = History(config.history_path())
        try:
            return h.record(q, res, ranked, sort=sort, leg=leg, parent_id=parent_id, status=status)
        finally:
            h.close()
    except Exception as e:
        console.print(f"[yellow]Could not save to search history: {e}[/yellow]")
        return None


@app.command()
def search(
    orig: str = typer.Argument(..., help="Origin IATA code, comma list, or 'home' (config)."),
    dest: str = typer.Argument(..., help="Destination IATA code."),
    date_: str = typer.Option(..., "--date", help="Departure date, YYYY-MM-DD."),
    flex: int = typer.Option(0, "--flex", help="Search +/- this many days."),
    cabin: str = typer.Option("", "--cabin", help="economy|premium|business|first"),
    pax: int = typer.Option(1, "--pax", min=1),
    rings: int = typer.Option(-1, "--rings", min=-1, max=3, help="Positioning rings 0-3."),
    budget_min: float = typer.Option(
        -1.0, "--budget-min", help="Stop widening after this many minutes."
    ),
    yes: bool = typer.Option(False, "--yes", help="Skip ring prompts."),
    top: int = typer.Option(15, "--top"),
    sort: str = typer.Option("eff", "--sort", help="eff|cpp|miles|duration|taxes"),
    min_premium: int = typer.Option(60, "--min-premium"),
    max_stops: int = typer.Option(-1, "--max-stops"),
    max_hours: float = typer.Option(-1.0, "--max-hours"),
    max_taxes: float = typer.Option(-1.0, "--max-taxes"),
    no_redeye: bool = typer.Option(False, "--no-redeye"),
    no_overnight: bool = typer.Option(False, "--no-overnight"),
    no_self_transfer: bool = typer.Option(False, "--no-self-transfer"),
    fresh: bool = typer.Option(False, "--fresh", help="Bypass the cache for this run."),
    json_out: Path | None = typer.Option(None, "--json", help="Write results to this JSON file."),
    return_date: str = typer.Option(
        "", "--return", help="Also plan the return one-way, YYYY-MM-DD."
    ),
    verbose: bool = typer.Option(False, "--verbose"),
    save_raw: Path | None = typer.Option(
        None,
        "--save-raw",
        help="Write raw API traffic here (UNSCRUBBED; run devtools.scrub before committing).",
    ),
) -> None:
    """Direct, then ring-by-ring positioning search, ranked by effective cost."""
    settings = config.load_settings()
    day = _parse_date(date_)
    homes = _origins(orig, settings)
    try:
        want = Cabin.parse(cabin) if cabin else None
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None
    filters = flt.Filters(
        cabin=want,
        min_premium=min_premium,
        max_stops=None if max_stops < 0 else max_stops,
        max_hours=None if max_hours < 0 else max_hours,
        max_taxes=None if max_taxes < 0 else max_taxes,
        no_redeye=no_redeye,
        no_overnight=no_overnight,
        no_self_transfer=no_self_transfer,
        pax=pax,
    )

    def query(origins: list[str], dest_: str, d: date, ring_n: int) -> Query:
        return Query(
            homes=origins,
            dest=dest_.upper(),
            start=d - timedelta(days=flex),
            end=d + timedelta(days=flex),
            pax=pax,
            filters=filters,
            rings=ring_n,
            budget_min=settings.budget_min if budget_min < 0 else budget_min,
            yes=yes,
            fresh=fresh,
        )

    ring_n = settings.default_rings if rings < 0 else rings
    out = _search_one(
        query(homes, dest, day, ring_n),
        settings,
        sort,
        top,
        verbose,
        f"{'/'.join(homes)} → {dest.upper()}  {day}",
        save_raw,
    )
    if out is None:
        raise typer.Exit(1)
    out, run_id = out
    export.save_last(config.last_search_path(), out)
    if return_date:
        back = _search_one(
            query([dest.upper()], homes[0], _parse_date(return_date), 0),
            settings,
            sort,
            top,
            verbose,
            f"{dest.upper()} → {homes[0]}  {return_date} (return)",
            save_raw,
            leg="return",
            parent_id=run_id,
        )
        console.print(
            "[dim]Return plans direct only; positioning for returns is not searched yet.[/dim]"
        )
        out = out + (back[0] if back else [])
    if json_out:
        export.export(json_out, SearchResult(out, []), out)
        console.print(f"Wrote {json_out}")
    console.print("[dim]Run `pointmax show N` for the legs, funding path and booking link.[/dim]")


@app.command()
def show(n: int = typer.Argument(..., help="Result number from the last search.")) -> None:
    """Full detail of result N from the last search."""
    try:
        its = export.load_last(config.last_search_path())
    except FileNotFoundError as e:
        _fail(str(e))
        return
    if not 1 <= n <= len(its):
        _fail(f"No result {n}; the last search has {len(its)}.")
        return
    table.detail(console, its[n - 1], n)


# ---- config / cache --------------------------------------------------------------------


@app.command(name="config")
def config_cmd(
    edit: bool = typer.Option(False, "--edit", help="Open the config in $EDITOR."),
) -> None:
    """Print or edit CPP table, home airports, buffers, ring radii."""
    path = config.write_default()
    if edit:
        editor = os.environ.get("EDITOR", "vi")
        subprocess.run([editor, str(path)], check=False)
        return
    console.print(f"[dim]{path}[/dim]\n")
    console.print(path.read_text())


@app.command()
def cache(clear: bool = typer.Option(False, "--clear", help="Delete all cached searches.")) -> None:
    """Inspect or clear cached searches."""
    c = Cache(config.cache_path(), config.load_settings().cache_ttl_hours)
    if clear:
        console.print(f"Cleared {c.clear()} cached searches.")
    else:
        st = c.stats()
        console.print(
            f"{st['searches']:.0f} searches, {st['options']:.0f} options; "
            f"entries older than {st['stale_after_hours']:g} h are ignored."
        )
    c.close()


# ---- history ---------------------------------------------------------------------------

history_app = typer.Typer(
    help="Past searches and their results, kept locally to compare and tune future searches.",
    no_args_is_help=True,
)
app.add_typer(history_app, name="history")


def _run_filter(
    origin: str, dest: str, cabin: str, program: str, since: str, limit: int | None = None
) -> RunFilter:
    if since:
        _parse_date(since)
    try:
        cab = Cabin.parse(cabin).name.lower() if cabin else None
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None
    return RunFilter(
        origin=origin or None,
        dest=dest or None,
        cabin=cab,
        program=program or None,
        since=since or None,
        limit=limit,
    )


_ORIGIN = typer.Option("", "--from", help="Runs that searched from this airport.")
_DEST = typer.Option("", "--to", help="Runs to this destination.")
_CABIN = typer.Option("", "--cabin", help="economy|premium|business|first")
_PROGRAM = typer.Option("", "--program", help="Runs with a result in this program (substring).")
_SINCE = typer.Option("", "--since", help="Runs on or after YYYY-MM-DD.")


@history_app.command("list")
def history_list(
    origin: str = _ORIGIN,
    dest: str = _DEST,
    cabin: str = _CABIN,
    program: str = _PROGRAM,
    since: str = _SINCE,
    limit: int = typer.Option(20, "--limit", min=1),
) -> None:
    """Past runs, newest first: route, dates, best effective cost and program."""
    h = History(config.history_path())
    runs = h.runs(_run_filter(origin, dest, cabin, program, since, limit))
    h.close()
    if not runs:
        console.print(
            "No searches recorded yet."
            if not any((origin, dest, cabin, program, since))
            else "No searches match."
        )
        return
    console.print(table.history_table(runs))
    console.print("[dim]`pointmax history show ID` for a run's results.[/dim]")


@history_app.command("show")
def history_show(
    run_id: int = typer.Argument(..., help="Run ID from `pointmax history list`."),
    top: int = typer.Option(15, "--top"),
) -> None:
    """The ranked results of a past run. They also become the target of `pointmax show N`."""
    h = History(config.history_path())
    run = h.run(run_id)
    its = h.itineraries(run_id) if run else []
    h.close()
    if run is None:
        _fail(f"No run {run_id} in the search history.")
        return
    dates = run["depart_start"]
    if run["depart_end"] != run["depart_start"]:
        dates += f" to {run['depart_end']}"
    console.rule(
        f"Run {run_id}: {run['origins'].replace(',', '/')} → {run['dest']}  {dates}  ({run['at']})"
    )
    if not its:
        console.print("[yellow]That run found no award space.[/yellow]")
        return
    console.print(table.results_table(its, top))
    export.save_last(config.last_search_path(), its)
    console.print("[dim]Run `pointmax show N` for the legs, funding path and booking link.[/dim]")


@history_app.command("export")
def history_export(
    path: Path = typer.Argument(..., help="CSV file to write."),
    runs_only: bool = typer.Option(
        False, "--runs", help="One row per run instead of one row per result."
    ),
    origin: str = _ORIGIN,
    dest: str = _DEST,
    cabin: str = _CABIN,
    program: str = _PROGRAM,
    since: str = _SINCE,
) -> None:
    """Write past runs and results to CSV (opens in Excel, Numbers, pandas)."""
    h = History(config.history_path())
    n = h.export_csv(path, _run_filter(origin, dest, cabin, program, since), runs_only=runs_only)
    h.close()
    console.print(f"Wrote {n} {'runs' if runs_only else 'results'} to {path}")


@history_app.command("delete")
def history_delete(run_id: int = typer.Argument(..., help="Run ID to remove.")) -> None:
    """Remove one run (and its return leg) from the history."""
    h = History(config.history_path())
    ok = h.delete(run_id)
    h.close()
    if not ok:
        _fail(f"No run {run_id} in the search history.")
        return
    console.print(f"Deleted run {run_id}.")
