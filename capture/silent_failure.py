"""
SILENT FAILURE  —  the guardrail trigger. The most important window of all.

The dangerous failure isn't the loud error — it's the QUIET bad output that slips
through and gets passed downstream while nobody notices. That's exactly the spot where,
if you handed the job to an agent, it would fail silently and no one would catch it.

We don't reinvent the detector: the repo already grades scrape-data usability in
eval/gate1.web_scraping (field_completeness >= 0.8, >= 1 row). We REUSE it here as the
kit's guardrail. When it fails on a step nobody flagged, we record a system observation
tagged FLAG_SILENT_FAILURE — and the blueprint translator turns every such flag into a
"put a human checkpoint right here" guardrail.
"""

from __future__ import annotations

from eval.gate1 import web_scraping

from capture.contracts import (
    FLAG_SILENT_FAILURE,
    KIND_SILENT_FAILURE,
    WINDOW_SYSTEM,
    Observation,
)
from capture.trace import new_observation_id

CHECK_LABEL = "web_scraping.field_completeness >= 0.8"


def flag_silent_failure(store, trace, *, step: str, rows) -> tuple[bool, Observation | None]:
    """Run the scrape data through the existing Gate-1 web_scraping contract. If it
    passes, return (True, None) — the data is usable, nothing to flag. If it FAILS, the
    bad data would have slipped through unnoticed, so we record + return (False, obs).
    """
    verdict = web_scraping(rows)
    if verdict.ok:
        return True, None

    obs = Observation(
        id=new_observation_id(),
        trace_id=trace.trace_id,
        window=WINDOW_SYSTEM,
        kind=KIND_SILENT_FAILURE,
        actor="kit",
        summary=f"SILENT FAILURE at '{step}': {verdict.detail} (bad data passed downstream unnoticed)",
        data={
            "step": step,
            "check": CHECK_LABEL,
            "category": verdict.category,
            "detail": verdict.detail,
            "rows_seen": len(rows) if isinstance(rows, list) else 0,
        },
        flags=[FLAG_SILENT_FAILURE],
    )
    return False, store.save_observation(obs)
