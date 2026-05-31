"""
WORKER PROMPTS  —  the demo trigger lives here.

GOOD_PROMPT mirrors the 7 scorecard checks 1:1 (enumerates every constraint).
DEGRADED_PROMPT is vague — it's what we "deploy" mid-demo to crater the score.

The degraded prompt must fail checks 1–6 most of the time but STILL usually return
valid-shaped JSON (so `valid_output` passes and we land at ~0.4, not 0). We want
"right shape, wrong content" — a clean, legible failure on the dashboard.

Both prompts receive the same .format(...) fields, so they're swappable at runtime.
"""

# ---------------------------------------------------------------------------
GOOD_PROMPT = """You are a social content writer for a {niche} brand.
Write ONE Instagram post about this trend.

Trend: "{trend_label}"
You MUST follow every rule below:
1. The hook must be at most 60 characters.
2. The caption must be at most 150 characters.
3. Include this call-to-action VERBATIM somewhere in the hook or caption: "{required_cta}"
4. Naturally include the trend keyword "{trend_keyword}" in the hook or caption.
5. Provide 3 to 5 hashtags. Every hashtag must start with '#'. One of them MUST be "{required_hashtag}".
6. Do NOT use any of these banned words: {banned_words}.
7. Return ONLY valid JSON, no markdown, in exactly this shape:
   {{"hook": "...", "caption": "...", "hashtags": ["#a", "#b", "#c"]}}

Voice: {voice_note}
"""

# ---------------------------------------------------------------------------
DEGRADED_PROMPT = """Write a fun Instagram post about this trend: "{trend_label}".
Make it catchy. Return it as JSON with a hook, caption, and hashtags.
"""
# ^ Note what's MISSING vs GOOD_PROMPT: no char limits, no required CTA, no trend
#   keyword instruction, no hashtag count/required-tag rule, no banned-word list,
#   no strict format. It usually returns JSON-ish output (valid_output passes) but
#   violates the content rules -> ~0.4.


def build_prompt(prompt_version: str, trend, brand) -> str:
    """prompt_version: 'good' | 'degraded' | a promoted fix prompt is passed as raw text.
    For promoted fixes the orchestrator stores the full candidate prompt string and
    passes it through build_prompt as a literal template (it already contains rules)."""
    fields = dict(
        niche=brand.niche,
        trend_label=trend.trend_label,
        trend_keyword=trend.trend_keyword,
        required_cta=brand.required_cta,
        required_hashtag=brand.required_hashtag,
        banned_words=", ".join(brand.banned_words),
        voice_note=brand.voice_note,
    )
    if prompt_version == "good":
        template = GOOD_PROMPT
    elif prompt_version == "degraded":
        template = DEGRADED_PROMPT
    else:
        # A promoted candidate prompt (raw template text from generate.py).
        template = prompt_version
    return template.format(**fields)
