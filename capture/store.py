"""
CAPTURE STORE  —  persistence for observations + blueprints.

Same dual-backend pattern as backend/store.py: one in-memory store that makes the kit
runnable today, and an Insforge REST stub with an identical interface so nobody is
blocked on backend provisioning. Pick with CAPTURE_STORE_BACKEND=insforge|memory.

The store is the only component that assigns Observation.seq — a monotonic counter in
insertion (i.e. real-time) order. The timeline assembler sorts by seq, so ordering is
deterministic even when many observations share a wall-clock timestamp.
"""

from __future__ import annotations

import os
import sys

from capture.contracts import AgentBlueprint, JobTrace, Observation


# ---------------------------------------------------------------------------
# IN-MEMORY STORE  (default; makes the kit runnable today)
# ---------------------------------------------------------------------------
class MemoryCaptureStore:
    def __init__(self):
        self._traces: dict[str, JobTrace] = {}
        self._obs: list[Observation] = []
        self._blueprints: list[AgentBlueprint] = []
        self._counter = 0

    # --- jobs ---
    def save_trace(self, trace: JobTrace) -> JobTrace:
        self._traces[trace.trace_id] = trace
        return trace

    def trace(self, trace_id: str) -> JobTrace | None:
        return self._traces.get(trace_id)

    # --- observations ---
    def save_observation(self, obs: Observation) -> Observation:
        obs.seq = self._counter
        self._counter += 1
        self._obs.append(obs)
        return obs

    def observations(self, trace_id: str | None = None) -> list[Observation]:
        rows = self._obs if trace_id is None else [o for o in self._obs if o.trace_id == trace_id]
        return sorted(rows, key=lambda o: o.seq)

    # --- blueprints ---
    def save_blueprint(self, bp: AgentBlueprint) -> AgentBlueprint:
        self._blueprints.append(bp)
        return bp

    def blueprints(self, trace_id: str | None = None) -> list[AgentBlueprint]:
        if trace_id is None:
            return list(self._blueprints)
        return [b for b in self._blueprints if b.trace_id == trace_id]


# ---------------------------------------------------------------------------
# INSFORGE STORE  (real backend; same interface)  — mirrors backend/store.py
# ---------------------------------------------------------------------------
class InsforgeCaptureStore:
    """TODO: implement against Insforge REST. Create three tables — `traces`,
    `observations`, `blueprints` — then back each method with an httpx call:
        POST {base}/rest/v1/observations             (insert)
        GET  {base}/rest/v1/observations?trace_id=eq.<id>&order=seq.asc
    Keep signatures identical to MemoryCaptureStore so the kit is backend-agnostic. A
    production deploy can point this at the SAME Insforge project backend/store.py uses
    (different tables) so the human-capture audit trail and the agent audit trail live
    side by side under one project.
    """

    def __init__(self):
        import httpx  # pip install httpx
        self.base = os.environ["INSFORGE_BASE_URL"].rstrip("/")
        self.key = os.environ["INSFORGE_API_KEY"]
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            timeout=15,
        )

    def save_trace(self, trace): raise NotImplementedError
    def trace(self, trace_id): raise NotImplementedError
    def save_observation(self, obs): raise NotImplementedError
    def observations(self, trace_id=None): raise NotImplementedError
    def save_blueprint(self, bp): raise NotImplementedError
    def blueprints(self, trace_id=None): raise NotImplementedError


def get_capture_store():
    """In-memory by default so the kit runs locally with zero setup. If CAPTURE_STORE_BACKEND
    =insforge but the backend can't be constructed (e.g. missing INSFORGE_* creds locally),
    fall back to memory with a warning instead of crashing — local should always work."""
    backend = os.getenv("CAPTURE_STORE_BACKEND", "memory").lower()
    if backend == "insforge":
        try:
            return InsforgeCaptureStore()
        except Exception as e:
            print(f"[capture.store] insforge unavailable ({e}); using in-memory store.", file=sys.stderr)
    return MemoryCaptureStore()
