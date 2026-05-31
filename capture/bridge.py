"""
BRIDGE  —  close gap #1: turn captured blueprint RULES into live SCORECARD checks.

This is the link that makes "the human improves the system" automatic. A rule distilled
from a human's REJECTION (capture/blueprint.py) — e.g. "reject '#sale' for a premium
brand" — is compiled into a deterministic (output, brand, trend) -> bool check and folded
into eval/scorecard.py via its `extra_checks` hook. No LLM-as-judge; same discipline as
the base scorecard. The generated checks generalize the existing `no_banned_words` check,
but sourced automatically from what the human chose NOT to do.

Enforcement nuance: a rejection is really a TREND-SELECTION rule (upstream). As a
CONTENT-level guardrail it stops the agent from leaning into the rejected angle in the
post itself — a faithful, conservative approximation that keeps the loop closed today.
"""

from __future__ import annotations

from eval.scorecard import score_output


def _norm(token: str) -> str:
    return str(token).strip().lower().lstrip("#").strip()


def _all_text(output) -> str:
    tags = " ".join(getattr(output, "hashtags", []) or [])
    return f"{getattr(output, 'hook', '')} {getattr(output, 'caption', '')} {tags}".lower()


def _make_avoid_check(token: str):
    def check(output, brand, trend) -> bool:
        return token not in _all_text(output)
    return check


def compile_rules_to_checks(blueprint) -> list[tuple]:
    """Compile a blueprint's rules into (name, fn) scorecard checks. One check per rule
    that names a concrete token to avoid; rules without an `avoid` token are skipped.
    De-dupes by token so two rejections of the same option don't double-count."""
    checks: list[tuple] = []
    seen: set[str] = set()
    for rule in getattr(blueprint, "rules", []):
        token = _norm(getattr(rule, "avoid", ""))
        if not token or token in seen:
            continue
        seen.add(token)
        name = "avoid_" + token.replace(" ", "_")
        checks.append((name, _make_avoid_check(token)))
    return checks


def evaluate_checks(checks, output, brand=None, trend=None) -> dict:
    """Run ONLY the compiled checks against an output (isolated from the base scorecard)."""
    return {name: bool(fn(output, brand, trend)) for name, fn in checks}


def score_with_blueprint(output, brand, trend, blueprint) -> tuple:
    """Score an output against the base scorecard PLUS the blueprint-derived checks."""
    return score_output(output, brand, trend, extra_checks=compile_rules_to_checks(blueprint))
