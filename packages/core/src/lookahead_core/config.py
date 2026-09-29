"""The stated constants of the forecasting protocol.

Every issue time, horizon, level, window, threshold and cost a figure depends on is
written here once, under a name, so docs/definitions.md and docs/protocol.md can cite
the field and a test can assert that the documents quote the value the code used.
"""

from __future__ import annotations

from lookahead_core.model import StrictModel

# EIA's regions in their fixed order, which is also the order of the tile map's rows.
REGIONS: tuple[str, ...] = (
    "CAL",
    "NW",
    "SW",
    "TEX",
    "CENT",
    "MIDW",
    "MIDA",
    "NY",
    "NE",
    "CAR",
    "SE",
    "TEN",
    "FLA",
)

REGION_LABELS: dict[str, str] = {
    "CAL": "California",
    "CAR": "Carolinas",
    "CENT": "Central",
    "FLA": "Florida",
    "MIDA": "Mid-Atlantic",
    "MIDW": "Midwest",
    "NE": "New England",
    "NW": "Northwest",
    "NY": "New York",
    "SE": "Southeast",
    "SW": "Southwest",
    "TEN": "Tennessee",
    "TEX": "Texas",
}

# EIA's three interconnections. The regions are assigned here from EIA's own documentation;
# the authorities are assigned to regions by the Region column in the balance files.
INTERCONNECTIONS: dict[str, tuple[str, ...]] = {
    "Eastern": ("CAR", "CENT", "FLA", "MIDA", "MIDW", "NE", "NY", "SE", "TEN"),
    "Western": ("CAL", "NW", "SW"),
    "Texas": ("TEX",),
}

LOWER_48 = "US48"

# The five levels the backends serve, in order. The 50 and 90 percent intervals are
# (0.25, 0.75) and (0.05, 0.95).
QUANTILE_LEVELS: tuple[float, ...] = (0.05, 0.25, 0.5, 0.75, 0.95)


class Policy(StrictModel):
    """The forecasting protocol. Quoted in the definitions; changed only with a DECISIONS entry."""

    issue_hour_utc: int = 0
    """One origin per day per authority at 00:00 UTC, the evening before in every U.S. time zone."""

    horizons: int = 48
    """Hours ahead of the origin that a forecast covers; horizon 1 is the first hour after it."""

    test_months: int = 12
    validation_months: int = 12
    """The last twelve months are the test period, the twelve before them are validation, the rest training."""

    seasonal_naive_lag_hours: int = 168
    """The seasonal naive baseline is demand at the same hour one week earlier."""

    ridge_penalties: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0)
    heating_thresholds_c: tuple[float, ...] = (8.0, 10.0, 12.0, 14.0, 16.0, 18.0)
    cooling_thresholds_c: tuple[float, ...] = (16.0, 18.0, 20.0, 22.0, 24.0, 26.0)
    """Candidate thresholds for the heating and cooling degree hours, chosen per authority on validation."""

    gbm_refit_months: int = 1
    """The global gradient boosted backend is refit at the start of every calendar month of the test year."""

    gbm_training_window_days: int = 1096
    """Each gbm refit trains on the origins of the three years before the refit date."""

    conformal_horizon_bucket_hours: int = 6
    """Conformal residual quantiles are pooled within buckets of this many horizon hours."""

    bootstrap_replicates: int = 500
    bootstrap_block_days: int = 7
    interval_level: float = 0.90
    """Block bootstrap over test days for every interval, blocks of a week, at least five hundred replicates."""

    bh_q: float = 0.05
    """Benjamini-Hochberg false discovery rate across the authorities in every family of comparisons."""

    spike_multiple_of_rolling_median: float = 3.0
    rolling_median_days: int = 30
    """Quarantine: demand above this multiple of the authority's trailing thirty day median is a defect."""

    alert_persistence_hours: int = 3
    """A standardized residual has to stay past the threshold for this many consecutive hours before an alert."""

    false_alarm_cost: float = 1.0
    missed_event_cost: float = 25.0
    """The operating point minimises false alarms at one unit each against missed event hours at this cost."""

    alert_threshold_grid: tuple[float, ...] = (2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0)

    recovery_seeds: int = 20
    """Seeds per condition of the recovery study on the simulator."""

    meter_test_days: int = 90
    """The last three months of the London release are the meter's test period."""

    meter_cluster_range: tuple[int, ...] = (3, 4, 5, 6, 7, 8)
    """Candidate numbers of load shape clusters, chosen by the silhouette score on the validation window."""

    meter_profile_window_days: int = 365
    """Household profiles are means over this many days before the test period."""

    peak_reduction_value_gbp_per_kw: float = 60.0
    """A stated value of a kilowatt of evening peak reduction, for the targeting view only."""

    coverage_band_90: tuple[float, float] = (0.85, 0.95)
    """Registry gate: empirical 90 percent coverage on validation has to sit in this band."""

    max_share_significantly_worse_than_operator: float = 0.5
    """Registry gate: no more than this share of authorities significantly worse than the operator after correction."""

    max_median_peak_timing_error_hours: float = 2.0
    """Registry gate: the median absolute peak timing error over the test year."""

    max_p99_latency_ms: float = 2000.0
    """Registry gate: the p99 latency of issuing a forecast through the API."""


POLICY = Policy()
