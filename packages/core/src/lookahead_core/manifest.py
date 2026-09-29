"""The manifest: every published figure, table and chart label, with where it came from.

Documents are rendered from this file and nothing else. Each entry names the data
source that produced it (the simulator, EIA-930, Open-Meteo or the London release),
the model or method where one was involved (own, gbm, a baseline, a reconciliation
method, the detector), its population, its seed where simulated, and its as of date.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import Field

from lookahead_core.formats import FORMATS, format_value
from lookahead_core.model import MutableStrictModel, StrictModel

Scalar = float | int | str | None

SOURCES = {
    "simulated",
    "real:eia930",
    "real:open_meteo",
    "real:lcl",
    "recorded",
    "mixed",
    "static",
}

MODELS = {
    "none",
    "own",
    "gbm",
    "both",
    "seasonal_naive",
    "operator",
    "bottom_up",
    "top_down",
    "mint",
    "detector",
    "kmeans",
    "did",
    "api",
}


class Provenance(StrictModel):
    source: str
    model: str
    population: str
    as_of: str
    origin: str
    seed: int | None = None
    seeds: int | None = None
    condition: str | None = None


class ValueEntry(StrictModel):
    value: Scalar
    fmt: str
    provenance: Provenance


class TableEntry(StrictModel):
    columns: list[str]
    formats: list[str]
    rows: list[list[Scalar]]
    provenance: Provenance


class FigureEntry(StrictModel):
    title: str
    callout: str
    provenance: Provenance
    data: str | None = None


class Manifest(MutableStrictModel):
    """Values, tables and figures keyed by dotted names such as ``backtest.own.mape.PJM``."""

    as_of: str
    seed: int
    values: dict[str, ValueEntry] = Field(default_factory=dict)
    tables: dict[str, TableEntry] = Field(default_factory=dict)
    figures: dict[str, FigureEntry] = Field(default_factory=dict)

    # Building

    def _check_key(self, key: str, bucket: Mapping[str, object]) -> None:
        if not key or "." not in key:
            raise ValueError(f"manifest keys are dotted, got {key!r}")
        if key in bucket:
            raise ValueError(f"manifest key {key!r} was written twice")

    def _prov(
        self,
        source: str,
        model: str,
        population: str,
        origin: str,
        seed: int | None,
        as_of: str | None,
        seeds: int | None,
        condition: str | None,
    ) -> Provenance:
        if source not in SOURCES:
            raise ValueError(f"unknown source {source!r}")
        if model not in MODELS:
            raise ValueError(f"unknown model backend {model!r}")
        if source == "simulated" and seed is None:
            seed = self.seed
        return Provenance(
            source=source,
            model=model,
            population=population,
            as_of=as_of or self.as_of,
            origin=origin,
            seed=seed,
            seeds=seeds,
            condition=condition,
        )

    def put(
        self,
        key: str,
        value: Scalar,
        fmt: str,
        *,
        source: str,
        population: str,
        origin: str,
        model: str = "none",
        seed: int | None = None,
        as_of: str | None = None,
        seeds: int | None = None,
        condition: str | None = None,
    ) -> None:
        self._check_key(key, self.values)
        if fmt not in FORMATS:
            raise KeyError(f"unknown format {fmt!r}")
        clean = _clean(value)
        self.values[key] = ValueEntry(
            value=clean,
            fmt=fmt,
            provenance=self._prov(source, model, population, origin, seed, as_of, seeds, condition),
        )

    def put_table(
        self,
        key: str,
        columns: Sequence[str],
        formats: Sequence[str],
        rows: Iterable[Sequence[Scalar]],
        *,
        source: str,
        population: str,
        origin: str,
        model: str = "none",
        seed: int | None = None,
        as_of: str | None = None,
        seeds: int | None = None,
        condition: str | None = None,
    ) -> None:
        self._check_key(key, self.tables)
        if len(columns) != len(formats):
            raise ValueError(f"table {key}: {len(columns)} columns but {len(formats)} formats")
        for fmt in formats:
            if fmt not in FORMATS:
                raise KeyError(f"unknown format {fmt!r}")
        materialised = [[_clean(cell) for cell in row] for row in rows]
        for row in materialised:
            if len(row) != len(columns):
                raise ValueError(f"table {key}: row width {len(row)} does not match {len(columns)} columns")
        if not materialised:
            raise ValueError(f"table {key} has no rows")
        self.tables[key] = TableEntry(
            columns=list(columns),
            formats=list(formats),
            rows=materialised,
            provenance=self._prov(source, model, population, origin, seed, as_of, seeds, condition),
        )

    def put_figure(
        self,
        key: str,
        title: str,
        callout: str,
        *,
        source: str,
        population: str,
        origin: str,
        model: str = "none",
        data: str | None = None,
        seed: int | None = None,
        as_of: str | None = None,
        seeds: int | None = None,
        condition: str | None = None,
    ) -> None:
        self._check_key(key, self.figures)
        self.figures[key] = FigureEntry(
            title=title,
            callout=callout,
            data=data,
            provenance=self._prov(source, model, population, origin, seed, as_of, seeds, condition),
        )

    # Reading

    def raw(self, key: str) -> Scalar:
        if key not in self.values:
            raise KeyError(f"manifest has no value {key!r}")
        return self.values[key].value

    def text(self, key: str) -> str:
        entry = self.values.get(key)
        if entry is None:
            raise KeyError(f"manifest has no value {key!r}")
        return format_value(entry.value, entry.fmt)

    def table_markdown(self, key: str) -> str:
        entry = self.tables.get(key)
        if entry is None:
            raise KeyError(f"manifest has no table {key!r}")
        header = "| " + " | ".join(entry.columns) + " |"
        align = "|" + "|".join("---" if f == "text" else "---:" for f in entry.formats) + "|"
        body = [
            "| "
            + " | ".join(format_value(cell, fmt) for cell, fmt in zip(row, entry.formats, strict=True))
            + " |"
            for row in entry.rows
        ]
        return "\n".join([header, align, *body])

    def label(self, key: str) -> str:
        """The one line provenance label printed under a figure or table."""
        entry: FigureEntry | TableEntry | ValueEntry | None = (
            self.figures.get(key) or self.tables.get(key) or self.values.get(key)
        )
        if entry is None:
            raise KeyError(f"manifest has no entry {key!r}")
        p = entry.provenance
        parts = [f"Source: {p.source}"]
        if p.model != "none":
            parts.append(f"model {p.model}")
        parts.append(p.population)
        if p.condition is not None:
            parts.append(f"condition {p.condition}")
        if p.seeds is not None:
            parts.append(f"{p.seeds} seeds")
        elif p.seed is not None:
            parts.append(f"seed {p.seed}")
        parts.append(f"as of {p.as_of}")
        return ", ".join(parts) + "."

    # Persistence

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump(mode="json")
        path.write_text(
            json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> Manifest:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def merge(self, other: Manifest) -> None:
        for key, value in other.values.items():
            self._check_key(key, self.values)
            self.values[key] = value
        for key, table in other.tables.items():
            self._check_key(key, self.tables)
            self.tables[key] = table
        for key, figure in other.figures.items():
            self._check_key(key, self.figures)
            self.figures[key] = figure

    def counts(self) -> dict[str, int]:
        return {"values": len(self.values), "tables": len(self.tables), "figures": len(self.figures)}


def _clean(value: Any) -> Scalar:
    """Round floats to a stable precision so reruns produce byte-identical manifests."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"manifest cannot store {type(value).__name__}") from exc
    if math.isnan(number) or math.isinf(number):
        return None
    if number.is_integer() and abs(number) < 2**53 and not isinstance(value, float):
        return int(number)
    return float(f"{number:.10g}")


class Scribe:
    """A manifest writer bound to one provenance, so a stage states its source once."""

    def __init__(
        self,
        manifest: Manifest,
        *,
        source: str,
        population: str,
        origin: str,
        model: str = "none",
        seed: int | None = None,
        seeds: int | None = None,
        condition: str | None = None,
    ) -> None:
        self.manifest = manifest
        self.source = source
        self.population = population
        self.origin = origin
        self.model = model
        self.seed = seed
        self.seeds = seeds
        self.condition = condition

    def put(self, key: str, value: Scalar, fmt: str, *, condition: str | None = None) -> None:
        self.manifest.put(
            key,
            value,
            fmt,
            source=self.source,
            model=self.model,
            population=self.population,
            origin=self.origin,
            seed=self.seed,
            seeds=self.seeds,
            condition=condition or self.condition,
        )

    def table(
        self,
        key: str,
        columns: Sequence[str],
        formats: Sequence[str],
        rows: Iterable[Sequence[Scalar]],
        *,
        condition: str | None = None,
    ) -> None:
        self.manifest.put_table(
            key,
            columns,
            formats,
            rows,
            source=self.source,
            model=self.model,
            population=self.population,
            origin=self.origin,
            seed=self.seed,
            seeds=self.seeds,
            condition=condition or self.condition,
        )

    def figure(self, key: str, title: str, callout: str, *, data: str | None = None) -> None:
        self.manifest.put_figure(
            key,
            title,
            callout,
            source=self.source,
            model=self.model,
            population=self.population,
            origin=self.origin,
            data=data,
            seed=self.seed,
            seeds=self.seeds,
            condition=self.condition,
        )
