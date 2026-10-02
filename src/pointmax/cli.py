"""Typer app: login, status, search, show, config, cache."""

import typer

from pointmax import __version__

app = typer.Typer(
    help="Find the cheapest-in-real-terms award flight, including positioning legs.",
    no_args_is_help=True,
)


def _not_yet(milestone: str) -> None:
    typer.echo(f"Not implemented yet (arrives in {milestone}).", err=True)
    raise typer.Exit(code=2)


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


@app.command()
def login(
    from_chrome: bool = typer.Option(
        False, "--from-chrome", help="Import cookies from your everyday Chrome instead."
    ),
) -> None:
    """One-time PointsYeah SSO login."""
    _not_yet("M1")


@app.command()
def status() -> None:
    """Session, plan limits, rate budget left, cache size."""
    _not_yet("M1")


@app.command()
def search(
    orig: str = typer.Argument(..., help="Origin IATA code."),
    dest: str = typer.Argument(..., help="Destination IATA code."),
    date: str = typer.Option(..., "--date", help="Departure date, YYYY-MM-DD."),
) -> None:
    """Direct, then ring-by-ring positioning search, ranked."""
    _not_yet("M3")


@app.command()
def show(n: int = typer.Argument(..., help="Result number from the last search.")) -> None:
    """Full detail of result N from the last search."""
    _not_yet("M4")


@app.command()
def config(edit: bool = typer.Option(False, "--edit", help="Open the config in $EDITOR.")) -> None:
    """Print or edit CPP table, home airports, buffers, ring radii."""
    _not_yet("M3")


@app.command()
def cache(clear: bool = typer.Option(False, "--clear", help="Delete all cached searches.")) -> None:
    """Inspect or clear cached searches."""
    _not_yet("M3")
