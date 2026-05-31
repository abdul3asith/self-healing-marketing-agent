"""
KALIBR INTELLIGENCE API  —  the "brain" (decoupled / provider-agnostic mode).

Kalibr's native Router only calls OpenAI/Anthropic/DeepSeek/Gemini/HF — NOT NEAR AI.
So we use Kalibr in DECOUPLED "Intelligence API" mode:

    1. ask Kalibr WHICH model to use for a goal        (decide)
    2. WE execute the call ourselves on NEAR AI         (llm_client.chat)
    3. report the outcome back so Kalibr LEARNS         (report_outcome)
    4. on failure, ask for the next-best model          (get_alternative)  <- THE HEAL

This is the only clean way to keep generation on NEAR private inference while still
using Kalibr's routing + self-healing + bandit learning. It is provider-agnostic and
portable into any stack.

Mock-fallback: if KALIBR_API_KEY / KALIBR_TENANT_ID are missing, every method returns
deterministic in-memory data so the whole demo runs offline (critical for an
unreliable hackathon network). The mock even tracks outcomes so insights/stats counts
climb as the loop runs — useful for narrating "it's learning".

Auth: every call except /health sends X-API-Key + X-Tenant-ID (dashboard.kalibr.systems
-> settings; key looks like sk_..., tenant user_/org_...).

Owner: orchestration (the handoff's Kalibr layer).
"""

from __future__ import annotations

import os
import uuid

KALIBR_BASE_URL = os.getenv("KALIBR_BASE_URL", "https://kalibr-intelligence.fly.dev")
KALIBR_API_KEY = os.getenv("KALIBR_API_KEY")
KALIBR_TENANT_ID = os.getenv("KALIBR_TENANT_ID")

# Kalibr only accepts these failure_category values on report-outcome.
FAILURE_CATEGORIES = frozenset({
    "timeout", "context_exceeded", "tool_error", "rate_limited", "validation_failed",
    "hallucination_detected", "user_unsatisfied", "empty_response", "malformed_output",
    "auth_error", "provider_error", "unknown",
})

# Neutral prior used by the mock bandit before any outcomes are observed.
_PRIOR_SUCCESS_RATE = 0.5


class KalibrClient:
    """Decoupled Intelligence API client with a deterministic offline mock.

    Real mode talks REST over httpx (imported lazily, so mock mode needs zero deps).
    """

    def __init__(self, api_key: str | None = KALIBR_API_KEY,
                 tenant_id: str | None = KALIBR_TENANT_ID,
                 base_url: str = KALIBR_BASE_URL):
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.mock = not (api_key and tenant_id)

        # --- mock state (also a handy in-process registry in real mode) ---
        # goal -> ordered list of registered model_ids (registration order = tiebreak)
        self._paths: dict[str, list[str]] = {}
        # goal -> model_id -> {"success", "failure", "score_sum", "score_n"}
        self._stats: dict[str, dict[str, dict]] = {}
        # goal -> ordered list of bools (for a cheap trend signal)
        self._outcomes: dict[str, list[bool]] = {}

        self._http = None  # lazy httpx.Client

    # ------------------------------------------------------------------ HTTP
    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key or "", "X-Tenant-ID": self.tenant_id or "",
                "Content-Type": "application/json"}

    def _client(self):
        if self._http is None:
            import httpx  # lazy: mock mode never imports it
            self._http = httpx.Client(base_url=self.base, headers=self._headers(), timeout=20)
        return self._http

    # =============================================================== ROUTING
    def register_path(self, goal: str, model_id: str) -> dict:
        """Register a goal x model path. Kalibr ONLY routes to registered paths, so
        call this for every goal x NEAR-model at startup. Idempotent."""
        if self.mock:
            self._paths.setdefault(goal, [])
            if model_id not in self._paths[goal]:
                self._paths[goal].append(model_id)
            self._stats.setdefault(goal, {}).setdefault(
                model_id, {"success": 0, "failure": 0, "score_sum": 0.0, "score_n": 0})
            return {"path_id": f"mock-path::{goal}::{model_id}", "goal": goal, "model_id": model_id}

        r = self._client().post("/api/v1/routing/paths", json={"goal": goal, "model_id": model_id})
        # 409 Conflict = path already registered on Kalibr -> idempotent success.
        if r.status_code != 409:
            r.raise_for_status()
        # mirror locally so get_alternative ordering works even against real Kalibr
        self._paths.setdefault(goal, [])
        if model_id not in self._paths[goal]:
            self._paths[goal].append(model_id)
        try:
            return r.json()
        except Exception:
            return {"goal": goal, "model_id": model_id, "status": r.status_code}

    def register_paths(self, goal_to_models: dict[str, list[str]]) -> None:
        """Bulk-register at startup, e.g. {"summarization": ["near-qwen3.5", ...], ...}."""
        for goal, models in goal_to_models.items():
            for model_id in models:
                self.register_path(goal, model_id)

    def decide(self, goal: str) -> dict:
        """Ask Kalibr which model to use. Returns {model_id, trace_id, confidence, params}.
        trace_id MUST be passed back to report_outcome so Kalibr can learn."""
        if self.mock:
            model_id = self._mock_pick(goal, exclude=[])
            if model_id is None:
                raise RuntimeError(f"No paths registered for goal '{goal}'. Call register_path first.")
            return {"model_id": model_id, "trace_id": f"mock-trace::{uuid.uuid4()}",
                    "confidence": self._mock_confidence(goal, model_id), "params": {}}

        r = self._client().post("/api/v1/routing/decide", json={"goal": goal})
        r.raise_for_status()
        return r.json()

    def get_alternative(self, goal: str, exclude_models: list[str]) -> dict | None:
        """THE HEAL: ask for the next-best path, excluding models that already failed.
        Returns a decision dict (same shape as decide) or None when alternatives are
        exhausted (Kalibr answers 404)."""
        if self.mock:
            model_id = self._mock_pick(goal, exclude=exclude_models)
            if model_id is None:
                return None
            return {"model_id": model_id, "trace_id": f"mock-trace::{uuid.uuid4()}",
                    "confidence": self._mock_confidence(goal, model_id), "params": {}}

        import httpx
        try:
            r = self._client().post("/api/v1/intelligence/get-alternative",
                                    json={"goal": goal, "exclude_models": exclude_models})
            if r.status_code == 404:
                return None  # alternatives exhausted
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    # ========================================================= INTELLIGENCE
    def report_outcome(self, trace_id: str, goal: str, success: bool, *,
                       score: float | None = None, failure_category: str | None = None,
                       model_id: str | None = None) -> dict:
        """THE LEARNING: report how the executed call went. trace_id comes from decide/
        get_alternative. failure_category (on failures) must be in FAILURE_CATEGORIES."""
        if failure_category and failure_category not in FAILURE_CATEGORIES:
            failure_category = "unknown"

        if self.mock:
            self._mock_record(goal, model_id, success, score)
            return {"ok": True, "trace_id": trace_id, "recorded": True}

        body: dict = {"trace_id": trace_id, "goal": goal, "success": success}
        if score is not None:
            body["score"] = score
        if failure_category:
            body["failure_category"] = failure_category
        if model_id:
            body["model_id"] = model_id
        r = self._client().post("/api/v1/intelligence/report-outcome", json=body)
        r.raise_for_status()
        # mirror locally so the dashboard's mock stats stay coherent in hybrid runs
        self._mock_record(goal, model_id, success, score)
        return r.json()

    def insights(self, goal: str, window_hours: int = 24) -> dict:
        """Per-goal status/success_rate/trend/actionable_signals."""
        if self.mock:
            return self._mock_insights(goal)
        r = self._client().get("/api/v1/intelligence/insights",
                               params={"goal": goal, "window_hours": window_hours})
        r.raise_for_status()
        return r.json()

    def stats(self, goal: str) -> dict:
        """Success rates + per-path performance (for the dashboard)."""
        if self.mock:
            return self._mock_stats(goal)
        r = self._client().get("/api/v1/routing/stats", params={"goal": goal})
        r.raise_for_status()
        return r.json()

    def health(self) -> dict:
        """Liveness check. No auth required."""
        if self.mock:
            return {"status": "ok", "mode": "mock"}
        import httpx
        r = httpx.get(f"{self.base}/api/v1/intelligence/health", timeout=10)
        r.raise_for_status()
        return r.json()

    # ============================================================ MOCK BANDIT
    def _ensure(self, goal: str, model_id: str) -> dict:
        self._stats.setdefault(goal, {})
        return self._stats[goal].setdefault(
            model_id, {"success": 0, "failure": 0, "score_sum": 0.0, "score_n": 0})

    def _success_rate(self, goal: str, model_id: str) -> float:
        s = self._stats.get(goal, {}).get(model_id)
        if not s:
            return _PRIOR_SUCCESS_RATE
        n = s["success"] + s["failure"]
        return s["success"] / n if n else _PRIOR_SUCCESS_RATE

    def _mock_pick(self, goal: str, exclude: list[str]) -> str | None:
        """Deterministic "bandit": prefer highest success_rate, tie-break by
        registration order. On a cold start every rate is the prior, so the first
        registered model wins — exactly the "mostly explore early" behaviour."""
        candidates = [m for m in self._paths.get(goal, []) if m not in set(exclude)]
        if not candidates:
            return None
        order = {m: i for i, m in enumerate(self._paths[goal])}
        candidates.sort(key=lambda m: (-self._success_rate(goal, m), order[m]))
        return candidates[0]

    def _mock_confidence(self, goal: str, model_id: str) -> float:
        s = self._stats.get(goal, {}).get(model_id, {})
        total = s.get("success", 0) + s.get("failure", 0)
        # rises with sample size; blends in observed success rate
        base = 0.5 + 0.45 * (total / (total + 8))
        return round(0.5 * base + 0.5 * (self._success_rate(goal, model_id)), 2)

    def _mock_record(self, goal: str, model_id: str | None, success: bool, score):
        if not model_id:
            return
        s = self._ensure(goal, model_id)
        s["success" if success else "failure"] += 1
        if score is not None:
            s["score_sum"] += float(score)
            s["score_n"] += 1
        self._outcomes.setdefault(goal, []).append(bool(success))

    def _mock_insights(self, goal: str) -> dict:
        per = self._mock_stats(goal)["per_path"]
        rate = self._mock_stats(goal)["success_rate"]
        status = "healthy" if rate >= 0.8 else ("watch" if rate >= 0.5 else "degraded")
        signals: list[str] = []
        if per:
            best = max(per, key=lambda p: (p["success_rate"], p["attempts"]))
            signals.append(f"best_model:{best['model_id']}")
        total = sum(p["attempts"] for p in per)
        if total < 20:
            signals.append("needs_more_samples")  # bandit converges at ~20-50/path
        outs = self._outcomes.get(goal, [])
        trend = "flat"
        if len(outs) >= 4:
            half = len(outs) // 2
            first = sum(outs[:half]) / half
            second = sum(outs[half:]) / (len(outs) - half)
            trend = "improving" if second > first + 0.05 else ("declining" if second < first - 0.05 else "flat")
        return {"goal": goal, "status": status, "success_rate": round(rate, 2),
                "trend": trend, "samples": total, "actionable_signals": signals, "mode": "mock"}

    def _mock_stats(self, goal: str) -> dict:
        paths = self._paths.get(goal, [])
        per_path = []
        tot_s = tot_n = 0
        for model_id in paths:
            s = self._stats.get(goal, {}).get(model_id, {"success": 0, "failure": 0, "score_sum": 0.0, "score_n": 0})
            attempts = s["success"] + s["failure"]
            tot_s += s["success"]
            tot_n += attempts
            per_path.append({
                "model_id": model_id, "attempts": attempts, "successes": s["success"],
                "success_rate": round(self._success_rate(goal, model_id), 2),
                "avg_score": round(s["score_sum"] / s["score_n"], 2) if s["score_n"] else None,
            })
        return {"goal": goal, "success_rate": round(tot_s / tot_n, 2) if tot_n else _PRIOR_SUCCESS_RATE,
                "attempts": tot_n, "per_path": per_path, "mode": "mock"}


# --- module singleton: keeps mock bandit state across calls in one process --------
_SINGLETON: KalibrClient | None = None


def get_kalibr() -> KalibrClient:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = KalibrClient()
    return _SINGLETON
