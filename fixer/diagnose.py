"""
DIAGNOSE  —  LLM step. (failing runs + current prompt) -> a hypothesis about what broke.

The fixer looks ONLY at the logs (failing Runs: their outputs and which checks failed)
plus the current prompt text. It never inspects the worker's code.

Owner: Person B (Fixer reasoning).

`weak` mode exists to engineer the demo's "first candidate fails" moment (section 9,
step 4): a deliberately shallow hypothesis that produces a candidate which won't pass
the sandbox. The second pass uses the full hypothesis.
"""

from __future__ import annotations

from llm_client import complete


def _summarize_failures(failing_runs) -> str:
    lines = []
    for r in failing_runs[:6]:
        failed = [name for name, ok in r.checks.items() if not ok]
        out = r.output
        sample = "" if out is None else f' hook="{out.hook[:50]}" caption="{out.caption[:60]}"'
        lines.append(f"- run {r.id[:8]}: failed {failed}{sample}")
    return "\n".join(lines)


def diagnose(failing_runs, current_prompt: str, *, weak: bool = False) -> str:
    """Returns a short natural-language hypothesis of the root cause."""
    failure_summary = _summarize_failures(failing_runs)
    detail = (
        "Give a one-sentence shallow guess only."
        if weak else
        "List EVERY constraint the current prompt fails to state clearly, mapped to the failing checks."
    )
    prompt = f"""A content-writing agent's quality dropped. Here are failing examples and which
deterministic checks they failed:

{failure_summary}

This is the prompt currently driving the agent:
---
{current_prompt}
---

Diagnose the root cause. {detail}
Respond with the hypothesis only, no preamble."""
    return complete(prompt, temperature=0.3 if not weak else 0.9).strip()
