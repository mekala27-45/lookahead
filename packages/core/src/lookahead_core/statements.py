"""The statement that appears on every surface.

Written once here. Pages, API responses, the memo, the cards and every rendered
document read it from this module, and a gate checks each surface.
"""

from __future__ import annotations

PROJECT = "lookahead"

STATEMENT = (
    "Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, "
    "public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' "
    "Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid "
    "operations."
)

WEATHER_CAVEAT = (
    "Weather features are observed weather at the target hour, which a real day ahead forecast does "
    "not have; the operator's forecast was made with a weather forecast."
)


def statement_markdown() -> str:
    """The statement as a Markdown block quote, for documents."""
    return f"> {STATEMENT}"


def statement_payload() -> dict[str, str]:
    """The statement as a JSON-ready mapping, for API response bodies."""
    return {"statement": STATEMENT}


def contains_statement(text: str) -> bool:
    """True when the statement appears verbatim, allowing for line wrapping."""
    flat = " ".join(text.split())
    return " ".join(STATEMENT.split()) in flat
