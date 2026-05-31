"""
FROZEN DATA CONTRACTS  —  do not change field names without telling the whole team.

These are the schemas every module agrees on. The fixer reads Runs (LOGS), never
the worker's internals, so these contracts are the only coupling between components.

Pivot note: the worker now writes ORGANIC SOCIAL CONTENT (Instagram) from a trend,
not paid ad copy. The *shape* is unchanged: one input + one model call -> one
structured output that a deterministic scorecard can grade.

    Brief      -> Trend          (the per-run input, sourced from Apify or our own channel)
    (added)    -> BrandProfile   (our static "own data": voice, required CTA/hashtag, banned words)
    AdOutput   -> ContentDraft   (hook + caption + hashtags)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# INPUTS
# ---------------------------------------------------------------------------

class Trend(BaseModel):
    """One trend handed to the worker. Trend SELECTION (Apify scrape + compare to
    our data) happens UPSTREAM — the worker never scrapes or ranks. It just gets
    one trend and writes a compliant post about it."""
    id: str
    platform: str                 # "instagram" for the demo (field kept so the story is "works across FB/IG/TikTok")
    trend_label: str              # human-readable theme, e.g. "POV: my 5am morning routine"
    trend_keyword: str            # the token that MUST appear in the output (deterministic "did we ride the trend" check)
    source: str = "apify"         # "apify:<dataset_id>" or "own_channel:@handle" — audit trail only


class BrandProfile(BaseModel):
    """Our static 'own data'. A single committed constant for the demo, NOT a pipeline.
    These are the hard, gradeable brand rules."""
    niche: str
    required_cta: str             # must appear verbatim, e.g. "Follow for more"
    required_hashtag: str         # must appear, e.g. "#glowroutine"
    banned_words: list[str]       # brand-safety list
    voice_note: str = ""          # one-line tone guidance — NOT scored (kept out of the deterministic scorecard)


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------

class ContentDraft(BaseModel):
    """What the worker returns. None (not an empty draft) if the model produced
    unparseable output — the scorecard scores that as 0/total."""
    hook: str                     # first-line scroll-stopper
    caption: str                  # main body
    hashtags: list[str]           # list of "#..." strings


# ---------------------------------------------------------------------------
# LOGS / AUDIT  (the fixer reads these, never the worker internals)
# ---------------------------------------------------------------------------

class Run(BaseModel):
    id: str
    trend_id: str
    prompt_version: str           # which worker prompt produced this ("good" / "degraded" / "fix_<n>")
    output: Optional[ContentDraft] = None   # None if the worker returned invalid output
    score: float                  # 0.0–1.0 = fraction of scorecard checks passed
    checks: dict[str, bool]       # check_name -> passed
    ts: datetime = Field(default_factory=datetime.utcnow)


class Detection(BaseModel):
    id: str
    window_avg_score: float       # rolling avg that tripped the threshold
    threshold: float
    failing_run_ids: list[str]
    ts: datetime = Field(default_factory=datetime.utcnow)


class FixAttempt(BaseModel):
    id: str
    detection_id: str
    hypothesis: str               # diagnose() output
    candidate_prompt: str         # generate() output
    sandbox_score: float          # score on the eval set inside Daytona
    promoted: bool                # True only if sandbox_score beats current AND >= threshold
    ts: datetime = Field(default_factory=datetime.utcnow)
