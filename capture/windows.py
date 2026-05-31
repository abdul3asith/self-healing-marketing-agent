"""
WINDOWS  —  the three connectors. Each watches the job through one window and emits an
Observation stamped with the job-level trace_id.

  Window 1  record_tool_use      — the tools they touch + WHAT they chose to feed them.
  Window 2  record_doc_revision  — the document evolving between saves (the transformation).
  Window 3  record_decision      — the choice in their head: considered / picked / rejected / why.

Design note: the valuable signal is rarely "they ran a tool" or "they wrote a doc" — it's
the INPUTS they chose (window 1), the way the artifact CHANGED (window 2), and the
reasons they REJECTED options (window 3). Those are exactly the things an agent would
otherwise have no way to learn.
"""

from __future__ import annotations

from capture.contracts import (
    KIND_DECISION,
    KIND_DOC_REVISION,
    KIND_TOOL_USE,
    WINDOW_DECISION,
    WINDOW_DOCUMENT,
    WINDOW_TOOL,
    Observation,
)
from capture.trace import new_observation_id


# --------------------------------------------------------- WINDOW 1: tools
def record_tool_use(store, trace, *, tool: str, inputs: dict,
                    output_meta: dict | None = None, child_trace_id: str | None = None,
                    flags: list | None = None, summary: str | None = None) -> Observation:
    """The strategist fired a tool. We note WHAT they chose to feed it (the decision the
    agent will eventually have to make too). `child_trace_id` lets a per-step Kalibr
    trace_id reference up to this job without replacing the job trace."""
    obs = Observation(
        id=new_observation_id(),
        trace_id=trace.trace_id,
        window=WINDOW_TOOL,
        kind=KIND_TOOL_USE,
        summary=summary or f"ran {tool} with inputs {sorted(inputs)}",
        data={
            "tool": tool,
            "inputs": inputs,
            "output_meta": output_meta or {},
            "child_trace_id": child_trace_id,
        },
        flags=list(flags or []),
    )
    return store.save_observation(obs)


# ------------------------------------------------------ WINDOW 2: documents
def _diff(before: dict, after: dict) -> dict:
    """Cheap, deterministic delta between two document snapshots. For list-valued fields
    we report a count change (the 'three ideas became two' transformation); for scalars
    we report old -> new. Keys only in one side are added/removed."""
    delta: dict = {}
    for key in sorted(set(before) | set(after)):
        b, a = before.get(key), after.get(key)
        if b == a:
            continue
        if isinstance(b, list) or isinstance(a, list):
            bn, an = len(b or []), len(a or [])
            delta[key] = {"from_count": bn, "to_count": an,
                          "removed": [x for x in (b or []) if x not in (a or [])],
                          "added": [x for x in (a or []) if x not in (b or [])]}
        else:
            delta[key] = {"from": b, "to": a}
    return delta


def record_doc_revision(store, trace, *, doc_id: str, before: dict, after: dict,
                        summary: str | None = None) -> Observation:
    """The kit watched the doc change between saves — it sees the proposal EVOLVE without
    anyone having to narrate it. `before`/`after` are snapshots (dicts of fields)."""
    delta = _diff(before, after)
    obs = Observation(
        id=new_observation_id(),
        trace_id=trace.trace_id,
        window=WINDOW_DOCUMENT,
        kind=KIND_DOC_REVISION,
        summary=summary or f"{doc_id} changed: {', '.join(delta) or 'no field changes'}",
        data={"doc_id": doc_id, "before": before, "after": after, "delta": delta},
    )
    return store.save_observation(obs)


# ------------------------------------------------------ WINDOW 3: decisions
def record_decision(store, trace, *, question: str, considered: list, picked,
                    rejected: list, confidence: float, summary: str | None = None) -> Observation:
    """The one nothing else can see. `rejected` is a list of {"option", "reason"} — the
    'why I rejected it' is the gold. `confidence` is 0..1; a low value is the signal that
    this step is judgment, not rote, and should stay human-in-the-loop."""
    n_rej = len(rejected)
    obs = Observation(
        id=new_observation_id(),
        trace_id=trace.trace_id,
        window=WINDOW_DECISION,
        kind=KIND_DECISION,
        summary=summary or f"chose {picked!r} (rejected {n_rej}, {int(confidence * 100)}% sure)",
        data={
            "question": question,
            "considered": considered,
            "picked": picked,
            "rejected": rejected,
            "confidence": confidence,
        },
    )
    return store.save_observation(obs)
