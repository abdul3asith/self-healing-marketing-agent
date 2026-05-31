"""
THE FROZEN EVAL SET  —  8 held-out trends + our brand profile.

CRITICAL: this is a FIXED, COMMITTED snapshot. The Daytona sandbox validates every
candidate fix against THIS list, forever. It must never hit live Apify, because a
non-deterministic / network-dependent eval set would destroy the credibility of the
"proof of fix" step (which is the whole reason Daytona is in the stack).

  * LIVE Apify  -> feeds the running worker (the ongoing stream the detector watches).
  * THIS file   -> the frozen yardstick the sandbox grades candidates against.

They share a schema; they are not the same thing. To refresh the eval set, scrape
once, hand-pick clean trends, commit them here, and tell the team.

Schema matches core.contracts (Trend, BrandProfile). We try to use the real Pydantic
models; if pydantic isn't installed yet we fall back to a lightweight object with the
same fields so the scorecard self-test runs with zero dependencies.
"""

from __future__ import annotations

try:
    from core.contracts import Trend, BrandProfile          # real frozen contracts
except Exception:                                            # offline / deps not installed yet
    from types import SimpleNamespace

    def Trend(**kw):           # type: ignore
        return SimpleNamespace(**kw)

    def BrandProfile(**kw):    # type: ignore
        return SimpleNamespace(**kw)


# --- our "own data": a single static brand profile -------------------------
BRAND_PROFILE = BrandProfile(
    niche="skincare / clean beauty",
    required_cta="Follow for more",
    required_hashtag="#glowroutine",
    banned_words=["miracle", "cure", "guaranteed", "clinically proven", "anti-aging"],
    voice_note="Warm, upbeat, Gen-Z friendly. Short sentences.",  # NOT scored
)


# --- the held-out trends (snapshot; e.g. from apify/instagram-search-scraper) ---
EVAL_TRENDS = [
    Trend(id="t1", platform="instagram", trend_label="POV: my 5am morning routine",
          trend_keyword="POV", source="apify:snapshot_2026_05"),
    Trend(id="t2", platform="instagram", trend_label="Get ready with me (GRWM) for spring",
          trend_keyword="GRWM", source="apify:snapshot_2026_05"),
    Trend(id="t3", platform="instagram", trend_label="That girl aesthetic glow up",
          trend_keyword="that girl", source="apify:snapshot_2026_05"),
    Trend(id="t4", platform="instagram", trend_label="Sunday reset routine",
          trend_keyword="Sunday reset", source="apify:snapshot_2026_05"),
    Trend(id="t5", platform="instagram", trend_label="Things in my cart this month",
          trend_keyword="in my cart", source="apify:snapshot_2026_05"),
    Trend(id="t6", platform="instagram", trend_label="Day in the life of a skincare lover",
          trend_keyword="day in the life", source="apify:snapshot_2026_05"),
    Trend(id="t7", platform="instagram", trend_label="Glass skin challenge",
          trend_keyword="glass skin", source="apify:snapshot_2026_05"),
    Trend(id="t8", platform="instagram", trend_label="Underrated products you need",
          trend_keyword="underrated", source="apify:snapshot_2026_05"),
]

assert len(EVAL_TRENDS) == 8, "Eval set size is locked at 8 (open decision #4)."
