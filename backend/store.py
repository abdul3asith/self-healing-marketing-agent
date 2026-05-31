"""
STORE  —  persistence + audit trail.

Tables: runs, detections, fix_attempts, prompt_versions (and a tiny config row for
the live prompt_version flag the demo flips).

Insforge (verified: docs.insforge.dev) is an agent-native BaaS: managed Postgres with
auto-generated REST endpoints (PostgREST-style), auth, storage. There's no official
Python SDK yet, so from Python we hit the REST API directly with httpx using the
Project URL + API Key.

Owner: Person D (Backend, dashboard, demo).

This file ships TWO backends behind one interface:
  * InsforgeStore  — real, talks to Insforge REST (fill in endpoints once provisioned).
  * MemoryStore    — in-memory, zero-dependency. The whole loop + demo runs on this so
                     nobody is ever blocked waiting on backend provisioning.
Pick with STORE_BACKEND=insforge|memory (default memory).
"""

from __future__ import annotations

import os
from collections import deque


# ---------------------------------------------------------------------------
# IN-MEMORY STORE  (default; makes the loop runnable today)
# ---------------------------------------------------------------------------
class MemoryStore:
    def __init__(self, initial_prompt_version: str = "good"):
        self._runs: list = []
        self._detections: list = []
        self._fix_attempts: list = []
        self._live_prompt = initial_prompt_version   # "good" | "degraded" | raw fix template
        self.prompt_versions = [initial_prompt_version]

    # --- runs ---
    def save_run(self, run):
        self._runs.append(run)
        return run

    def recent_runs(self, limit: int = 10):
        return list(reversed(self._runs[-limit:]))    # newest first

    def runs_by_ids(self, ids):
        idset = set(ids)
        return [r for r in self._runs if r.id in idset]

    def all_runs(self):
        return list(self._runs)

    # --- detections ---
    def save_detection(self, data: dict) -> dict:
        self._detections.append(data)
        return data

    # --- fix attempts ---
    def save_fix_attempt(self, data: dict) -> dict:
        self._fix_attempts.append(data)
        return data

    def mark_promoted(self, fix_id: str):
        for f in self._fix_attempts:
            if f["id"] == fix_id:
                f["promoted"] = True

    def fix_attempts(self):
        return list(self._fix_attempts)

    def detections(self):
        return list(self._detections)

    # --- live prompt flag (the demo flips this) ---
    def get_live_prompt(self) -> str:
        return self._live_prompt

    def set_live_prompt(self, version: str):
        self._live_prompt = version

    def promote(self, candidate_prompt: str):
        self.prompt_versions.append("fix")
        self._live_prompt = candidate_prompt


# ---------------------------------------------------------------------------
# INSFORGE STORE  (real backend; same interface)
# ---------------------------------------------------------------------------
class InsforgeStore:
    """TODO(Person D): implement against Insforge REST endpoints.

    Setup: create the project at insforge.dev, grab Project URL + API Key, create the
    four tables, then back each method below with an httpx call. PostgREST-style:
        POST {base}/rest/v1/runs            (insert)
        GET  {base}/rest/v1/runs?order=ts.desc&limit=10
    Keep method signatures identical to MemoryStore so the loop is backend-agnostic.
    """

    def __init__(self):
        import httpx  # pip install httpx
        self.base = os.environ["INSFORGE_BASE_URL"].rstrip("/")
        self.key = os.environ["INSFORGE_API_KEY"]
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            timeout=15,
        )

    def _post(self, table, row):
        r = self._http.post(f"{self.base}/rest/v1/{table}", json=row)
        r.raise_for_status()
        return row

    # The methods below mirror MemoryStore. Fill in the HTTP calls.
    def save_run(self, run): raise NotImplementedError
    def recent_runs(self, limit: int = 10): raise NotImplementedError
    def runs_by_ids(self, ids): raise NotImplementedError
    def all_runs(self): raise NotImplementedError
    def save_detection(self, data): raise NotImplementedError
    def save_fix_attempt(self, data): raise NotImplementedError
    def mark_promoted(self, fix_id): raise NotImplementedError
    def fix_attempts(self): raise NotImplementedError
    def detections(self): raise NotImplementedError
    def get_live_prompt(self): raise NotImplementedError
    def set_live_prompt(self, version): raise NotImplementedError
    def promote(self, candidate_prompt): raise NotImplementedError


def get_store():
    backend = os.getenv("STORE_BACKEND", "memory")
    if backend == "insforge":
        return InsforgeStore()
    return MemoryStore()
