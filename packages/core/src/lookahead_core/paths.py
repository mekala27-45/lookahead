"""Where everything lives. Resolved once from the repository root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _find_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        marker = candidate / "pyproject.toml"
        if marker.is_file() and (candidate / "packages" / "core").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not find the lookahead repository root above {start}")


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def external(self) -> Path:
        """Raw public files, fetched by `make data` or placed by hand, never committed."""
        return self.data / "external"

    @property
    def external_eia(self) -> Path:
        return self.external / "eia930"

    @property
    def external_london(self) -> Path:
        return self.external / "london"

    @property
    def eia(self) -> Path:
        """Derived EIA-930 parquet: the hourly panel, the quarantine report, the hierarchy tables; committed."""
        return self.data / "eia930"

    @property
    def weather(self) -> Path:
        """Hourly weather per authority location, committed with attribution."""
        return self.data / "weather"

    @property
    def london(self) -> Path:
        """Derived household tables; the raw release is never committed."""
        return self.data / "london"

    @property
    def sim(self) -> Path:
        return self.data / "sim"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def manifest(self) -> Path:
        return self.results / "manifest.json"

    @property
    def marts(self) -> Path:
        return self.results / "marts"

    @property
    def report(self) -> Path:
        return self.root / "report"

    @property
    def docs(self) -> Path:
        return self.root / "docs"

    @property
    def web_data(self) -> Path:
        return self.root / "web" / "public" / "data"

    @property
    def logs(self) -> Path:
        return self.root / "logs"


@lru_cache(maxsize=1)
def paths() -> Paths:
    override = os.environ.get("LOOKAHEAD_ROOT")
    root = Path(override).resolve() if override else _find_root(Path(__file__).resolve())
    return Paths(root=root)
