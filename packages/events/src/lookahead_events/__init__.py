"""Anomaly detection on the forecast residuals: demand events told apart from data defects, the
operating point chosen on a validation year by stated costs, graded on planted and known events."""

from lookahead_events.classify import classify_run
from lookahead_events.detect import Alert, ResidualScale, find_alerts, residual_scale, standardize
from lookahead_events.grade import Grade, grade
from lookahead_events.operating import OperatingPoint, choose_threshold
from lookahead_events.recovery_extension import register

register()

__all__ = [
    "Alert",
    "Grade",
    "OperatingPoint",
    "ResidualScale",
    "choose_threshold",
    "classify_run",
    "find_alerts",
    "grade",
    "residual_scale",
    "standardize",
]
