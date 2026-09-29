"""Classification by rule: a data defect when the abnormal hours are the ones a quarantine rule
flagged (a zero, a negative, a duplicated hour, a missing hour, a spike) and the hours around
the run are normal; a demand event otherwise. A dead feed never becomes a demand collapse."""

from __future__ import annotations

import numpy as np

DEFECT = "data_defect"
DEMAND_EVENT = "demand_event"


def classify_run(run_flagged: np.ndarray, run_z: np.ndarray, neighbors_normal: bool) -> str:
    """``run_flagged`` marks the hours a quarantine rule fired on, ``run_z`` holds the standardized
    residuals (NaN where flagged). A run that is at least half flagged, with normal neighbors, is a
    defect; a run with unflagged hours past the threshold is a demand event."""
    if len(run_flagged) == 0:
        raise ValueError("an empty run has no class")
    share_flagged = float(np.mean(run_flagged))
    if share_flagged >= 0.5 and neighbors_normal:
        return DEFECT
    if share_flagged == 1.0:
        # Every hour flagged but the neighbors are not normal: still a defect in the data, reported
        # as one, because there is no demand to have moved.
        return DEFECT
    return DEMAND_EVENT
