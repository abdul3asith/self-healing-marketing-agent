"""
CAPTURE CONTRACTS  —  the shapes every capture module agrees on.

Mirrors the spirit of core/contracts.py (one frozen schema the whole package codes
against) but uses stdlib dataclasses instead of pydantic so the kit runs with ZERO
dependencies — the capture side is meant to sit quietly beside a human's tools and
must never need a heavy install to start observing.

The atom is the Observation: every window emits these, and EVERY observation in one
job carries the same job-level trace_id. That shared label is the whole trick — it is
what lets the timeline assembler line up "how the human did April" later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

# --- the three windows (+ a system channel the kit itself writes to) -------
WINDOW_TOOL = "tool"          # window 1: the tools they touch (e.g. Apify) + chosen inputs
WINDOW_DOCUMENT = "document"  # window 2: the document they're building, between saves
WINDOW_DECISION = "decision"  # window 3: the choice in their head (considered/picked/rejected/why)
WINDOW_SYSTEM = "system"      # the kit's own observations (e.g. a flagged silent failure)

# Observation kinds (the verb of an observation).
KIND_TOOL_USE = "tool_use"
KIND_DOC_REVISION = "doc_revision"
KIND_DECISION = "decision"
KIND_SILENT_FAILURE = "silent_failure"

FLAG_SILENT_FAILURE = "silent_failure"  # the dangerous kind: bad output that slips through quietly


def _serialize(value: Any) -> Any:
    """JSON-friendly recursion: datetimes -> isoformat, dataclasses -> dict."""
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# JOB  +  OBSERVATION  (what the kit records)
# ---------------------------------------------------------------------------
@dataclass
class JobTrace:
    """One real job (e.g. 'April content cycle — Client X'). Its trace_id stamps every
    observation that happens during it, no matter which window captured it."""
    trace_id: str
    title: str
    ts: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {"trace_id": self.trace_id, "title": self.title, "ts": self.ts.isoformat()}


@dataclass
class Observation:
    """One thing the kit saw, through one window. The `seq` is assigned by the store on
    save (monotonic per process) so the timeline orders deterministically even when many
    observations share a wall-clock timestamp."""
    id: str
    trace_id: str            # job-level trace_id — the grouping key for the timeline
    window: str              # WINDOW_TOOL | WINDOW_DOCUMENT | WINDOW_DECISION | WINDOW_SYSTEM
    kind: str                # KIND_* — the verb
    summary: str             # human-readable one-liner
    actor: str = "human"     # "human" (the strategist) or "kit" (the observer itself)
    data: dict = field(default_factory=dict)   # window-specific payload (see capture/windows.py)
    flags: list = field(default_factory=list)   # e.g. [FLAG_SILENT_FAILURE]
    ts: datetime = field(default_factory=datetime.utcnow)
    seq: int = -1            # set by the store on save; -1 = not yet persisted

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        d["data"] = _serialize(self.data)
        return d


# ---------------------------------------------------------------------------
# BLUEPRINT  (what the kit produces — the agent build instructions)
# ---------------------------------------------------------------------------
@dataclass
class Capability:
    """A tool step -> 'the agent needs to be able to call this with these kinds of inputs.'"""
    tool: str
    example_inputs: dict
    derived_from: str        # observation id this was distilled from

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Rule:
    """A rejection reason -> a hard rule ('don't pick trends that cheapen a premium brand')."""
    rule: str
    rationale: str
    derived_from: str
    avoid: str = ""          # concrete token the agent must steer clear of (powers capture/bridge.py)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Guardrail:
    """A silent failure -> 'put a human checkpoint right here, this is where it breaks quietly.'"""
    at_step: str
    check: str
    action: str
    derived_from: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HumanCheckpoint:
    """A low-confidence judgment call -> 'keep a human in the loop: this is judgment, not rote.'"""
    step: str
    reason: str
    confidence: float
    derived_from: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentBlueprint:
    """The translation output: the human's real timeline, read backwards into agent specs."""
    trace_id: str
    title: str
    narrative: str                              # the one-line timeline chain
    capabilities: list = field(default_factory=list)        # list[Capability]
    rules: list = field(default_factory=list)               # list[Rule]
    guardrails: list = field(default_factory=list)          # list[Guardrail]
    human_in_the_loop: list = field(default_factory=list)   # list[HumanCheckpoint]

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "title": self.title,
            "narrative": self.narrative,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "rules": [r.to_dict() for r in self.rules],
            "guardrails": [g.to_dict() for g in self.guardrails],
            "human_in_the_loop": [h.to_dict() for h in self.human_in_the_loop],
        }
