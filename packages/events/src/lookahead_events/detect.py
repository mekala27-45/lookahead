"""Detection: standardized short horizon residuals, a persistence rule, and runs of abnormal hours.

The residual is the relative error of the forecast issued at the day's own origin, ``(raw - f) / f``
at horizons 1 to 24, so every target hour has exactly one residual. It is standardized per
authority by the median and the scaled median absolute deviation of the same residual over
the validation year, which is the robust scale the brief asks for and the year the conformal
offsets were calibrated on. An hour is abnormal when its standardized residual passes the
threshold or when a quarantine rule flagged its raw value (missing, at or below zero, a
duplicated hour, a skipped hour, a spike). A run of consecutive abnormal hours becomes an alert
when it is at least the persistence length, or when every hour in it is a flagged one, because
a feed that reports a single zero is a defect however short.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from lookahead_events.classify import classify_run

HOUR = timedelta(hours=1)
FLAG_COLUMNS: tuple[str, ...] = (
    "demand_missing",
    "demand_nonpositive",
    "demand_spike",
    "duplicate_hour",
    "missing_hour",
)
MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class ResidualScale:
    center: float
    scale: float
    rows: int


@dataclass(frozen=True)
class Alert:
    authority: str
    start: datetime
    end: datetime
    """The last hour of the run, inclusive."""
    hours: int
    kind: str
    """demand_event or data_defect."""
    direction: str
    """low when demand ran under the forecast, high when over, mixed otherwise; defect for defects."""
    peak_z: float
    mean_z: float
    flagged_hours: int
    flags: str
    """The quarantine rules that fired in the run, comma separated, or none."""


def residual_scale(residuals: np.ndarray) -> ResidualScale:
    """Median and scaled median absolute deviation of the finite residuals."""
    r = residuals[np.isfinite(residuals)]
    if len(r) < 100:
        raise ValueError(f"a residual scale needs at least 100 residuals, got {len(r)}")
    center = float(np.median(r))
    mad = float(np.median(np.abs(r - center)))
    scale = MAD_TO_SIGMA * mad
    if scale <= 0:
        raise ValueError("the residuals have no spread")
    return ResidualScale(center=center, scale=scale, rows=int(len(r)))


def standardize(frame: pl.DataFrame, scales: dict[str, ResidualScale]) -> pl.DataFrame:
    """Add ``residual`` and ``z`` to a frame of authority, utc_hour, pred, demand_raw and the flag
    columns; z is null where the raw value is flagged or the forecast is missing."""
    missing = [c for c in ("authority", "utc_hour", "pred", "demand_raw") if c not in frame.columns]
    if missing:
        raise ValueError(f"the detector frame lacks {missing}")
    flags = [c for c in FLAG_COLUMNS if c in frame.columns]
    for c in FLAG_COLUMNS:
        if c not in frame.columns:
            frame = frame.with_columns(pl.lit(False).alias(c))
    flagged = pl.any_horizontal([pl.col(c).fill_null(False) for c in FLAG_COLUMNS])
    centers = pl.DataFrame(
        {
            "authority": list(scales),
            "residual_center": [s.center for s in scales.values()],
            "residual_scale": [s.scale for s in scales.values()],
        }
    )
    out = (
        frame.join(centers, on="authority", how="left")
        .with_columns(flagged.alias("flagged"))
        .with_columns(
            pl.when(
                ~pl.col("flagged")
                & pl.col("pred").is_not_null()
                & (pl.col("pred") > 0)
                & pl.col("demand_raw").is_not_null()
            )
            .then((pl.col("demand_raw").cast(pl.Float64) - pl.col("pred")) / pl.col("pred"))
            .otherwise(None)
            .alias("residual")
        )
        .with_columns(
            ((pl.col("residual") - pl.col("residual_center")) / pl.col("residual_scale")).alias("z")
        )
        .sort(["authority", "utc_hour"])
    )
    _ = flags
    return out


def find_alerts(standardized: pl.DataFrame, threshold: float, persistence: int) -> list[Alert]:
    """Runs of abnormal hours per authority, classified. The frame is the output of ``standardize``."""
    if threshold <= 0 or persistence < 1:
        raise ValueError("the threshold has to be positive and the persistence at least one hour")
    alerts: list[Alert] = []
    for authority in sorted(standardized["authority"].unique().to_list()):
        rows = standardized.filter(pl.col("authority") == authority).sort("utc_hour")
        hours = rows["utc_hour"].to_list()
        z = rows["z"].cast(pl.Float64).fill_null(float("nan")).to_numpy()
        flagged = rows["flagged"].fill_null(False).to_numpy()
        flag_names = [
            rows[c].fill_null(False).to_numpy() if c in rows.columns else np.zeros(rows.height, dtype=bool)
            for c in FLAG_COLUMNS
        ]
        abnormal = flagged | (np.abs(np.nan_to_num(z, nan=0.0)) > threshold)
        n = len(hours)
        i = 0
        while i < n:
            if not abnormal[i]:
                i += 1
                continue
            j = i
            # A run continues through consecutive abnormal hours with no gap in the hourly index.
            while j + 1 < n and abnormal[j + 1] and hours[j + 1] - hours[j] == HOUR:
                j += 1
            run_flagged = flagged[i : j + 1]
            run_z = z[i : j + 1]
            all_flagged = bool(run_flagged.all())
            length = j - i + 1
            if length >= persistence or all_flagged:
                before = z[max(0, i - 3) : i]
                after = z[j + 1 : j + 4]
                neighbors = np.concatenate([before, after])
                neighbors_normal = bool(
                    np.all(np.abs(np.nan_to_num(neighbors, nan=0.0)) <= threshold)
                ) and not (flagged[max(0, i - 3) : i].any() or flagged[j + 1 : j + 4].any())
                kind = classify_run(run_flagged, run_z, neighbors_normal)
                finite = run_z[np.isfinite(run_z)]
                if kind == "data_defect":
                    direction = "defect"
                elif len(finite) == 0:
                    direction = "mixed"
                else:
                    low = float(np.mean(finite < 0))
                    direction = "low" if low >= 0.75 else "high" if low <= 0.25 else "mixed"
                fired = sorted(
                    {FLAG_COLUMNS[k] for k, arr in enumerate(flag_names) if bool(arr[i : j + 1].any())}
                )
                alerts.append(
                    Alert(
                        authority=authority,
                        start=hours[i],
                        end=hours[j],
                        hours=length,
                        kind=kind,
                        direction=direction,
                        peak_z=float(np.max(np.abs(finite))) if len(finite) else float("nan"),
                        mean_z=float(np.mean(finite)) if len(finite) else float("nan"),
                        flagged_hours=int(run_flagged.sum()),
                        flags=",".join(fired) if fired else "none",
                    )
                )
            i = j + 1
    return alerts


def alerts_frame(alerts: list[Alert]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "authority": [a.authority for a in alerts],
            "start": pl.Series([a.start for a in alerts], dtype=pl.Datetime("us", "UTC")),
            "end": pl.Series([a.end for a in alerts], dtype=pl.Datetime("us", "UTC")),
            "hours": [a.hours for a in alerts],
            "kind": [a.kind for a in alerts],
            "direction": [a.direction for a in alerts],
            "peak_z": [a.peak_z for a in alerts],
            "mean_z": [a.mean_z for a in alerts],
            "flagged_hours": [a.flagged_hours for a in alerts],
            "flags": [a.flags for a in alerts],
        }
    )
