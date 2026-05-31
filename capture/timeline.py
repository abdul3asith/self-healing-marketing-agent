"""
TIMELINE  —  assemble scattered observations into one honest story.

Takes all observations sharing a job-level trace_id, orders them by `seq` (the store's
monotonic real-time counter), and renders the clean chain:

    scraped trends -> wrote proposal -> chose #spring (rejected 2, 60% sure)
        -> tracked performance -> bad data slipped through (flagged)

That's the human's ACTUAL workflow — not the idealized version in a process doc, but
the real one, including the judgment call and the mistake.
"""

from __future__ import annotations

from capture.contracts import KIND_SILENT_FAILURE, Observation


def assemble(store, trace_id: str) -> list[Observation]:
    """All observations for one job, ordered by time (seq)."""
    return store.observations(trace_id)


def _phrase(o: Observation) -> str:
    if o.kind == KIND_SILENT_FAILURE:
        return "bad data slipped through (flagged)"
    return o.summary


def render(timeline: list[Observation]) -> str:
    """The one-line chain. Each step is its observation's summary, joined in time order."""
    if not timeline:
        return "(empty timeline)"
    return "  ->  ".join(_phrase(o) for o in timeline)
