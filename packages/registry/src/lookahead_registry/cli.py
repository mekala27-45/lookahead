"""The pipeline, one command per stage, in the order the Makefile runs them."""

from __future__ import annotations

import typer

app = typer.Typer(add_completion=False, help="lookahead: demand forecasting for the grid and the meter")


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo("lookahead 0.1.0")


if __name__ == "__main__":
    app()
