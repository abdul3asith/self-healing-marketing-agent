"""
GENERATE  —  LLM step. (hypothesis + current prompt) -> a candidate prompt.

The candidate is a full prompt template (same .format fields as worker/prompts.py)
that we hope fixes the diagnosed problem. It is NEVER deployed directly — it goes to
validate.py to be scored in a Daytona sandbox first.

Owner: Person B (Fixer reasoning).
"""

from __future__ import annotations

from fixer.runstep import run_step
from eval.gate1 import candidate_prompt

_REQUIRED_FIELDS = "{niche} {trend_label} {trend_keyword} {required_cta} {required_hashtag} {banned_words} {voice_note}"


def generate(hypothesis: str, current_prompt: str) -> str:
    """Returns a candidate prompt template string."""
    prompt = f"""You are improving the prompt that drives a social-content agent.

Diagnosed problem:
{hypothesis}

Current (failing) prompt:
---
{current_prompt}
---

Rewrite it into an improved prompt that fixes the problem. The new prompt MUST:
- be a Python .format() template that uses exactly these placeholders where relevant:
  {_REQUIRED_FIELDS}
- explicitly state the hard rules (60-char hook, 150-char caption, verbatim CTA,
  include the trend keyword, 3-5 hashtags including the required one, no banned words,
  return strict JSON {{"hook","caption","hashtags"}}).

Return ONLY the new prompt template text. No commentary, no code fences."""
    step = run_step("research", [{"role": "user", "content": prompt}],
                    candidate_prompt, temperature=0.4, max_tokens=800)
    candidate = step.output.strip()
    # Strip accidental fences.
    return candidate.removeprefix("```").removesuffix("```").strip()
