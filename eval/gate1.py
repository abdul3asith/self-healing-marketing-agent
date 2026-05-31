"""
GATE-1 CONTRACTS  —  per-goal output-usability checks for the self-healing loop.

Each pipeline step maps to a Kalibr GOAL (the standard taxonomy) and is validated by
a contract here. A contract answers ONE question: *"is this model output usable?"* —
i.e. non-empty, right-shaped, not a refusal, not an error. It returns a `Verdict`
that the orchestrator (`fixer/runstep.py`) turns into a Kalibr report-outcome.

CRITICAL design boundary (why this is NOT the scorecard):
  * Gate-1 catches a MODEL problem  -> HEAL by rerouting models via Kalibr.
  * eval/scorecard.py catches a PROMPT/quality problem -> HEAL by fixing the prompt
    in a Daytona sandbox (the existing fixer loop).
A vague (degraded) prompt still produces valid-SHAPED output, so it PASSES Gate-1 and
is correctly left for the scorecard + fixer to handle. If Gate-1 graded brand quality,
model-healing would mask the very degradation the fixer is built to detect.

`category` on a failed Verdict is a valid Kalibr failure_category (see
integrations/kalibr.FAILURE_CATEGORIES) so report-outcome can teach the bandit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

REFUSAL_MARKERS = ("i cannot", "i can't", "i am unable", "i'm sorry", "as an ai", "cannot assist")
ERROR_MARKERS = ("error", "exception", "traceback")

# Worker .format fields — used to verify a candidate prompt is a safe template.
_WORKER_FIELDS = dict(niche="x", trend_label="x", trend_keyword="x", required_cta="x",
                      required_hashtag="#x", banned_words="x", voice_note="x")


@dataclass
class Verdict:
    ok: bool
    score: float | None = None
    category: str | None = None   # a Kalibr failure_category when not ok
    detail: str = ""


def _empty(text: str) -> bool:
    return not text or not str(text).strip()


def _is_refusal(text: str) -> bool:
    head = text.strip().lower()[:80]
    return any(m in head for m in REFUSAL_MARKERS)


# =========================================================== GENERIC GOAL CONTRACTS
def summarization(output: str) -> Verdict:
    """Analyze step. Not empty / refusal; 30-1500 chars."""
    if _empty(output):
        return Verdict(False, category="empty_response", detail="empty")
    if _is_refusal(output):
        return Verdict(False, category="user_unsatisfied", detail="refusal")
    n = len(output.strip())
    if not (30 <= n <= 1500):
        return Verdict(False, category="malformed_output", detail=f"len {n} outside 30-1500")
    return Verdict(True, score=round(min(1.0, n / 300), 2))


def research(output: str) -> Verdict:
    """Ideate step. >= 200 chars; no error markers in the first 100 chars."""
    if _empty(output):
        return Verdict(False, category="empty_response", detail="empty")
    body = output.strip()
    if len(body) < 200:
        return Verdict(False, category="malformed_output", detail=f"len {len(body)} < 200")
    if any(m in body[:100].lower() for m in ERROR_MARKERS):
        return Verdict(False, category="provider_error", detail="error marker in head")
    return Verdict(True, score=round(min(1.0, len(body) / 600), 2))


def outreach_generation(output: str) -> Verdict:
    """Generate step (generic text variant). Non-empty; 50-2000 chars."""
    if _empty(output):
        return Verdict(False, category="empty_response", detail="empty")
    n = len(output.strip())
    if not (50 <= n <= 2000):
        return Verdict(False, category="malformed_output", detail=f"len {n} outside 50-2000")
    return Verdict(True, score=round(min(1.0, n / 500), 2))


def web_scraping(rows) -> Verdict:
    """Discover step. Valid list; field_completeness >= 0.8; >= 1 row."""
    if not isinstance(rows, list) or len(rows) < 1:
        return Verdict(False, category="empty_response", detail="no rows")
    fields = ("text", "reactions", "comments", "shares", "url", "time", "pageName")
    filled = sum(sum(1 for f in fields if r.get(f) not in (None, "")) for r in rows)
    completeness = filled / (len(rows) * len(fields))
    if completeness < 0.8:
        return Verdict(False, category="validation_failed", detail=f"field_completeness {completeness:.2f}")
    return Verdict(True, score=round(completeness, 2))


# ===================================================== SKELETON-SPECIFIC CONTRACTS
def content_draft(output: str) -> Verdict:
    """Worker content generation (Kalibr goal 'outreach_generation').

    STRUCTURAL gate: parseable JSON with non-empty hook + caption and a hashtag list.
    NOT the brand scorecard — see the module docstring for why that separation matters.
    """
    raw = output.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except Exception:
        return Verdict(False, category="malformed_output", detail="unparseable JSON")
    hook = str(data.get("hook", "")).strip()
    caption = str(data.get("caption", "")).strip()
    if not hook or not caption:
        return Verdict(False, category="empty_response", detail="missing hook/caption")
    if not isinstance(data.get("hashtags"), list):
        return Verdict(False, category="malformed_output", detail="hashtags not a list")
    return Verdict(True, score=1.0)


def candidate_prompt(output: str) -> Verdict:
    """fixer.generate output (Kalibr goal 'research').

    The candidate must be a usable Python .format() template (no KeyError/IndexError),
    so a malformed candidate can never crash the Daytona sandbox — it heals instead.
    """
    template = output.strip().removeprefix("```").removesuffix("```").strip()
    if _empty(template) or len(template) < 80:
        return Verdict(False, category="malformed_output", detail="too short to be a prompt")
    try:
        template.format(**_WORKER_FIELDS)
    except Exception as e:
        return Verdict(False, category="malformed_output", detail=f"unsafe template: {e}")
    return Verdict(True, score=1.0)
