"""
DETECT  —  rolling-score drop detection. Pure logic, no LLM.

Reads recent Runs (LOGS) from the store and decides whether quality has dropped
below threshold. This is the scorecard wearing its "failure detector" hat.

Owner: Person B (Fixer reasoning).
"""

from __future__ import annotations

import uuid

THRESHOLD = 0.8     # open decision #4 default
WINDOW = 10         # open decision #4 default


def rolling_avg(runs) -> float:
    if not runs:
        return 1.0
    return sum(r.score for r in runs) / len(runs)


def detect_drop(recent_runs, threshold: float = THRESHOLD):
    """recent_runs: the most recent <= WINDOW Runs (newest first or any order).
    Returns a dict describing a Detection if the rolling avg is below threshold,
    else None. The caller persists it via store.save_detection(...).
    """
    window = list(recent_runs)[:WINDOW]
    if len(window) < WINDOW:
        return None  # not enough signal yet — don't fire on a cold start
    avg = rolling_avg(window)
    if avg < threshold:
        failing = [r.id for r in window if r.score < threshold]
        return {
            "id": str(uuid.uuid4()),
            "window_avg_score": avg,
            "threshold": threshold,
            "failing_run_ids": failing,
        }
    return None
