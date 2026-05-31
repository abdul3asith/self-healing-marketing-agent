"""
THE SCORECARD  —  build #1, the heart of the whole project.

This single artifact is THREE things at once:
  1. our definition of "quality"  (what good content means)
  2. our failure detector         (rolling avg of these scores tripping a threshold)
  3. our proof-of-fix             (a candidate prompt is promoted only if it BEATS this score)

Rules:
  * Every check is deterministic pure Python. NO LLM-as-judge. Ever.
  * Each check takes (output, brand, trend) and returns bool.
  * Score = passed / total. If output is None (unparseable), score = 0.0.

Decoupling note: this module is DUCK-TYPED. It imports nothing from contracts and
reads plain attributes (output.hook, brand.required_cta, trend.trend_keyword). That
means it grades anything log-shaped — Pydantic models, SimpleNamespace, dataclasses —
which is exactly why "works on any agent that emits logs" is true. Do not couple it
to a concrete class.

Limits (60 / 150) are DELIBERATELY TIGHT artificial constraints, not real IG caption
caps (those are thousands of chars). The point is a rule the vague DEGRADED prompt
reliably breaks, so healthy ~1.0 and degraded ~0.4.
"""

from __future__ import annotations

HOOK_CHAR_LIMIT = 60
CAPTION_CHAR_LIMIT = 150
MIN_HASHTAGS = 3
MAX_HASHTAGS = 5


def _all_text(output) -> str:
    tags = " ".join(output.hashtags or [])
    return f"{output.hook} {output.caption} {tags}"


# --- individual checks ------------------------------------------------------
# Each returns True iff the rule is satisfied.

def hook_under_limit(output, brand, trend) -> bool:
    return len(output.hook) <= HOOK_CHAR_LIMIT


def caption_under_limit(output, brand, trend) -> bool:
    return len(output.caption) <= CAPTION_CHAR_LIMIT


def contains_cta(output, brand, trend) -> bool:
    # CTA must appear verbatim (case-insensitive) somewhere in hook+caption.
    text = f"{output.hook} {output.caption}".lower()
    return brand.required_cta.lower() in text


def references_trend(output, brand, trend) -> bool:
    # The trend keyword must appear — this is the deterministic "did we actually
    # ride the trend" check (the discount-code analog from the original spec).
    text = f"{output.hook} {output.caption}".lower()
    return trend.trend_keyword.lower() in text


def hashtag_rules(output, brand, trend) -> bool:
    tags = output.hashtags or []
    if not (MIN_HASHTAGS <= len(tags) <= MAX_HASHTAGS):
        return False
    if not all(isinstance(t, str) and t.startswith("#") for t in tags):
        return False
    return brand.required_hashtag.lower() in [t.lower() for t in tags]


def no_banned_words(output, brand, trend) -> bool:
    text = _all_text(output).lower()
    return not any(bad.lower() in text for bad in brand.banned_words)


# Order here is the order shown on the dashboard.
CHECKS = [
    ("hook_under_limit", hook_under_limit),
    ("caption_under_limit", caption_under_limit),
    ("contains_cta", contains_cta),
    ("references_trend", references_trend),
    ("hashtag_rules", hashtag_rules),
    ("no_banned_words", no_banned_words),
]
# Note: `valid_output` is handled below by the None-check, so the effective total
# is len(CHECKS) + 1. A parse failure scores 0/total (all checks counted as failed).


def score_output(output, brand, trend) -> tuple[float, dict[str, bool]]:
    """Returns (score in 0..1, {check_name: passed}).

    `output` may be None when the worker produced unparseable JSON; that scores
    0.0 with every check (including valid_output) marked False.
    """
    total = len(CHECKS) + 1  # +1 for valid_output

    if output is None or not getattr(output, "hook", "") or not getattr(output, "caption", ""):
        checks = {name: False for name, _ in CHECKS}
        checks["valid_output"] = False
        return 0.0, checks

    checks: dict[str, bool] = {}
    for name, fn in CHECKS:
        try:
            checks[name] = bool(fn(output, brand, trend))
        except Exception:
            checks[name] = False
    checks["valid_output"] = True

    passed = sum(1 for v in checks.values() if v)
    return passed / total, checks
