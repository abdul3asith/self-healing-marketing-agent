"""
THE WORKER  —  the PATIENT. Keep it dumb.

One model call: (trend, brand, prompt_version) -> ContentDraft | None.
It does NOT scrape Apify, rank trends, or compare to our data — that's upstream.
After generating, its only job is to emit a scored Run (a LOG). The fixer reads
those logs; it never touches anything in here.

Owner: Person A (Eval & Worker).
"""

from __future__ import annotations

import json
import uuid

from worker.prompts import build_prompt
from eval.scorecard import score_output
from eval.gate1 import content_draft
from fixer.runstep import run_step

# These imports only succeed once pydantic is installed; the worker is runtime code.
from core.contracts import ContentDraft, Run


def _parse(raw: str) -> ContentDraft | None:
    """Best-effort JSON parse. Strips ```json fences. Returns None on failure so the
    scorecard scores it 0/total (the valid_output check)."""
    if not raw:
        return None
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
        return ContentDraft(
            hook=str(data.get("hook", "")),
            caption=str(data.get("caption", "")),
            hashtags=list(data.get("hashtags", []) or []),
        )
    except Exception:
        return None


def run_worker(trend, brand, prompt_version: str, *, on_event=None) -> Run:
    """Generate one post and return a fully scored Run.

    prompt_version is read from the store at the call site so the demo can flip
    'good' -> 'degraded' (and later a promoted fix) at runtime.

    The single model call now flows through run_step (Kalibr goal
    'outreach_generation'), so a down/garbled model self-heals across NEAR models
    before we ever score it. Gate-1 (content_draft) checks output USABILITY only —
    the brand scorecard below stays the source of truth for quality and remains the
    signal the fixer's drop detector watches.
    """
    prompt = build_prompt(prompt_version, trend, brand)
    step = run_step("outreach_generation", [{"role": "user", "content": prompt}],
                    content_draft, on_event=on_event)
    draft = _parse(step.output)
    score, checks = score_output(draft, brand, trend)
    return Run(
        id=str(uuid.uuid4()),
        trend_id=trend.id,
        prompt_version=prompt_version if prompt_version in ("good", "degraded") else "fix",
        output=draft,
        score=score,
        checks=checks,
    )
