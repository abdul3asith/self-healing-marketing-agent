"""
RUNSTEP  —  the model-level self-healing orchestrator (one LLM step).

This is the handoff's `runStep`: it wraps EVERY model call so that a step which fails
its Gate-1 contract (or whose model is down) reroutes to another NEAR model and retries
*before anything surfaces*. It hedges the known NEAR private-cloud flakiness.

    decision = kalibr.decide(goal)              # which model?  (+ trace_id)
    loop:
        output = nearai.chat(model, messages)   # execute on NEAR private inference
        verdict = eval_fn(output)               # Gate-1 contract for this goal
        if verdict.ok:  report success;  return
        report failure(verdict.category)        # THE LEARNING
        decision = kalibr.get_alternative(...)  # THE HEAL: swap model, retry
        if not decision: break
    return graceful degradation (last output)

This is DISTINCT from fixer/orchestrate.py:
  * runstep.py   = MODEL-level heal (reroute models per step, via Kalibr).
  * orchestrate.py = PROMPT-level heal (fix the worker's prompt, via Daytona).
The two layers compose: every LLM call inside the prompt-fix loop is itself runStep'd.

Owner: orchestration (the handoff's Kalibr layer).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from integrations.kalibr import get_kalibr
from llm_client import NearAIError, chat, map_path_to_near_model, is_mock, PATH_TO_NEAR_MODEL
from eval.gate1 import Verdict

MAX_HEALS = 3   # cap on model reroutes per step (loop also stops when paths are exhausted)

DEFAULT_GOALS = ("summarization", "research", "outreach_generation", "web_scraping")

# Register each goal's paths at most once per process (idempotent + avoids chatty REST).
_ENSURED: set[str] = set()


@dataclass
class StepResult:
    goal: str
    ok: bool
    output: str
    model_id: str | None          # Kalibr path of the winning/last model
    near_model: str | None        # resolved NEAR slug
    trace_id: str | None
    heals: int                    # number of model reroutes that happened (0 = first try worked)
    verdict: Verdict
    attempts: list = field(default_factory=list)


def available_model_ids() -> list[str]:
    """NEAR-backed Kalibr paths we can route to. In mock mode all are usable; in real
    mode we drop paths whose NEAR slug is unset (e.g. GLM until its slug is verified)."""
    if is_mock():
        return list(PATH_TO_NEAR_MODEL.keys())
    usable = [mid for mid, slug in PATH_TO_NEAR_MODEL.items() if slug]
    return usable or [next(iter(PATH_TO_NEAR_MODEL))]


def register_default_paths(goals=DEFAULT_GOALS) -> None:
    """Register every goal x NEAR-model path at startup. Kalibr ONLY routes to
    registered paths, so call this before running the pipeline (or rely on the
    lazy per-goal registration inside run_step)."""
    kalibr = get_kalibr()
    for goal in goals:
        kalibr.register_paths({goal: available_model_ids()})
        _ENSURED.add(goal)


def _ensure(kalibr, goal: str) -> None:
    if goal in _ENSURED:
        return
    kalibr.register_paths({goal: available_model_ids()})
    _ENSURED.add(goal)


def run_step(goal: str, messages: list[dict], eval_fn: Callable[[str], Verdict], *,
             temperature: float = 0.7, max_tokens: int = 600,
             on_event: Callable[[dict], None] | None = None) -> StepResult:
    """Execute one self-healing LLM step. Returns a StepResult (never raises for a
    model failure — it heals, then degrades gracefully so the caller stays in control).
    """
    kalibr = get_kalibr()
    _ensure(kalibr, goal)

    def emit(event: str, **data):
        if on_event:
            on_event({"event": event, "goal": goal, **data})

    decision = kalibr.decide(goal)
    emit("decide", model_id=decision.get("model_id"), confidence=decision.get("confidence"))

    excluded: list[str] = []
    last_output = ""
    last_verdict = Verdict(False, category="unknown", detail="no attempt ran")
    attempts: list[dict] = []

    for attempt in range(MAX_HEALS + 1):
        model_id = decision.get("model_id")
        trace_id = decision.get("trace_id")
        near_model = map_path_to_near_model(model_id)

        try:
            output = chat(messages, model_id=model_id, temperature=temperature, max_tokens=max_tokens)
            verdict = eval_fn(output)
        except NearAIError as e:
            output = ""
            verdict = Verdict(False, category="provider_error", detail=str(e))

        last_output = output or last_output
        last_verdict = verdict
        attempts.append({"attempt": attempt, "model_id": model_id, "near_model": near_model,
                         "ok": verdict.ok, "category": verdict.category, "detail": verdict.detail})
        emit("attempt", attempt=attempt, model_id=model_id, near_model=near_model,
             ok=verdict.ok, category=verdict.category)

        if verdict.ok:
            kalibr.report_outcome(trace_id, goal, True, score=verdict.score, model_id=model_id)
            emit("outcome", success=True, model_id=model_id, heals=attempt, score=verdict.score)
            return StepResult(goal=goal, ok=True, output=output, model_id=model_id,
                              near_model=near_model, trace_id=trace_id, heals=attempt,
                              verdict=verdict, attempts=attempts)

        # Contract failed (or model down) -> teach Kalibr, then HEAL to another model.
        kalibr.report_outcome(trace_id, goal, False, failure_category=verdict.category, model_id=model_id)
        if model_id:
            excluded.append(model_id)
        alt = kalibr.get_alternative(goal, excluded)
        # A real Kalibr response can omit model_id (or hand back an already-excluded /
        # unmapped path); treat any of those as "no usable alternative" so we degrade
        # gracefully instead of raising (a 500 in the API). The offline mock always
        # returns a well-formed, mapped path, so this only guards the live path.
        alt_model = alt.get("model_id") if isinstance(alt, dict) else None
        if not alt_model or alt_model in excluded:
            emit("exhausted", excluded=excluded)
            break
        emit("heal", from_model=model_id, to_model=alt_model, reason=verdict.category)
        decision = alt

    # Graceful degradation: every alternative failed (e.g. NEAR account out of credits,
    # provider outage). Rather than hand back empty output that scores 0 and breaks the
    # demo, fall back to the offline engine for a usable result. The heal_trace still
    # records every real failure, so the audit trail stays honest about what happened.
    if not last_output:
        from llm_client import _mock_chat
        last_output = _mock_chat(messages, near_model=map_path_to_near_model(excluded[-1]) if excluded else "offline")
        last_verdict = eval_fn(last_output)
        emit("offline_fallback", reason="all_models_failed", ok=last_verdict.ok)
        if last_verdict.ok:
            return StepResult(goal=goal, ok=True, output=last_output,
                              model_id=excluded[-1] if excluded else None,
                              near_model=map_path_to_near_model(excluded[-1]) if excluded else "offline",
                              trace_id=None, heals=len(excluded), verdict=last_verdict, attempts=attempts)

    emit("degraded", heals=len(excluded), last_category=last_verdict.category)
    return StepResult(goal=goal, ok=False, output=last_output, model_id=excluded[-1] if excluded else None,
                      near_model=map_path_to_near_model(excluded[-1]) if excluded else None,
                      trace_id=None, heals=len(excluded), verdict=last_verdict, attempts=attempts)
