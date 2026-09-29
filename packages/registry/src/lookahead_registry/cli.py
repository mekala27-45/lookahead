"""The pipeline, one command per stage, in the order the Makefile runs them."""

from __future__ import annotations

import datetime as dt
import os

import typer
from lookahead_core.paths import paths

app = typer.Typer(add_completion=False, help="lookahead: demand forecasting for the grid and the meter")

DEMONSTRATION_SEED = 13


def as_of() -> str:
    return os.environ.get("LOOKAHEAD_AS_OF", dt.date.today().isoformat())


@app.command()
def data(
    skip_london: bool = typer.Option(False, help="ingest the grid only; the meter step is not done"),
) -> None:
    """EIA-930 in full with the quarantine, the hierarchy, and the London release into DuckDB."""
    from lookahead_registry.stages import data as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED, require_london=not skip_london)
    typer.echo(f"data: {manifest.counts()}")


@app.command()
def weather(no_pull: bool = typer.Option(False, help="use the cache only, never try the host")) -> None:
    """Hourly weather per authority location from the Open-Meteo cache, committed as parquet."""
    from lookahead_registry.stages import weather as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED, attempt_pull=not no_pull)
    typer.echo(f"weather: {manifest.counts()}")


@app.command()
def simulate() -> None:
    """The synthetic grid with known truth for the demonstration seed."""
    from lookahead_registry.stages import simulate as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"simulate: {manifest.counts()}")


@app.command()
def recovery(
    seeds: int = typer.Option(0, help="seeds per condition; 0 means the policy's twenty"),
    conditions: str = typer.Option("", help="comma separated condition names; empty means all"),
    workers: int = typer.Option(2, help="worker processes"),
) -> None:
    """The recovery study over conditions and seeds on the simulator."""
    from lookahead_registry.stages import recovery as stage

    chosen = [c.strip() for c in conditions.split(",") if c.strip()] or None
    manifest = stage.run(
        paths(), as_of(), DEMONSTRATION_SEED, seeds=seeds or None, conditions=chosen, workers=workers
    )
    typer.echo(f"recovery: {manifest.counts()}")


@app.command()
def backtest(
    backend: str = typer.Option("own", help="own, gbm or seasonal_naive"),
    authorities: str = typer.Option("", help="comma separated subset, for a quick run"),
    rescore: bool = typer.Option(False, help="score the saved predictions again without refitting"),
) -> None:
    """The rolling origin backtest of one backend on the real grid."""
    from lookahead_registry.stages import backtest as stage

    chosen = [a.strip() for a in authorities.split(",") if a.strip()] or None
    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED, backend, authorities=chosen, rescore=rescore)
    typer.echo(f"backtest {backend}: {manifest.counts()}")


@app.command()
def skill() -> None:
    """Skill against the operator with wins, losses and ties, and the cross check table."""
    from lookahead_registry.stages import skill as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"skill: {manifest.counts()}")


@app.command()
def hierarchy(authorities: str = typer.Option("", help="comma separated subset, for a quick run")) -> None:
    """Reconciliation across the hierarchy with coherence tests and accuracy by level."""
    from lookahead_registry.stages import hierarchy as stage

    chosen = [a.strip() for a in authorities.split(",") if a.strip()] or None
    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED, authorities=chosen)
    typer.echo(f"hierarchy: {manifest.counts()}")


@app.command()
def events(
    known: bool = typer.Option(True, help="grade the known events table (fits a window per row)"),
) -> None:
    """Anomaly detection with its operating point, graded on the known events."""
    from lookahead_registry.stages import events as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED, known=known)
    typer.echo(f"events: {manifest.counts()}")


@app.command()
def meter() -> None:
    """The meter: clusters, the pre-registered time of use analysis, the cluster forecast reconciled."""
    from lookahead_registry.stages import meter as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"meter: {manifest.counts()}")


@app.command()
def registry() -> None:
    """Every candidate backend through the seven gates; the served model chosen."""
    from lookahead_registry.stages import registry as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"registry: {manifest.counts()}")


@app.command()
def latency() -> None:
    """Record the load test results into the manifest."""
    from lookahead_registry.stages import latency as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"latency: {manifest.counts()}")


@app.command()
def marts() -> None:
    """The marts and the bundle the control room queries in the browser."""
    from lookahead_registry.stages import marts as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"marts: {manifest.counts()}")


@app.command()
def manifest() -> None:
    """Merge every stage manifest into results/manifest.json."""
    from lookahead_registry.stages import assemble

    merged = assemble.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"manifest: {merged.counts()}")


if __name__ == "__main__":
    app()
