"""
APIFY SOURCE  —  scrape recent posts for a domain's seed hashtags.

Returns a flat list of normalized posts (caption + hashtags + engagement). The
candidate-trend extraction and the compare-to-our-data scoring happen in compare.py.

Stub behavior (handoff: "stub behind the interface, keep moving"):
  * If APIFY_STUB=1 OR no APIFY_API_TOKEN is set, return a fixed sample of skincare
    posts so the whole pipeline runs with zero network. Flagged via source="apify_stub".
  * Otherwise hit the real Apify actor.

Note: Apify actor input/output schemas vary by actor. _normalize() is best-effort and
defensive; tune the field names to whichever actor you point APIFY_INSTAGRAM_ACTOR at.
"""

from __future__ import annotations

import os

APIFY_STUB = os.getenv("APIFY_STUB", "0") == "1"
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
ACTOR = os.getenv("APIFY_INSTAGRAM_ACTOR", "apify/instagram-hashtag-scraper")


def fetch_posts(seeds: list[str], results_limit: int = 50) -> tuple[list[dict], str]:
    """Returns (posts, source_tag). Each post: {caption, hashtags, likes, comments}."""
    if APIFY_STUB or not APIFY_TOKEN:
        return _stub_posts(seeds), "apify_stub"
    return _live_posts(seeds, results_limit), "apify:live"


def _live_posts(seeds: list[str], results_limit: int) -> list[dict]:
    from apify_client import ApifyClient  # pip install apify-client

    client = ApifyClient(APIFY_TOKEN)
    run_input = {
        "hashtags": [s.lstrip("#") for s in seeds],
        "resultsLimit": results_limit,
    }
    run = client.actor(ACTOR).call(run_input=run_input)
    items = client.dataset(run["defaultDatasetId"]).iterate_items()
    return [_normalize(it) for it in items]


def _normalize(item: dict) -> dict:
    """Best-effort map of an Apify post item -> our shape. Field names are actor-dependent."""
    hashtags = item.get("hashtags") or _extract_hashtags(item.get("caption", ""))
    return {
        "caption": item.get("caption", "") or "",
        "hashtags": [h if h.startswith("#") else f"#{h}" for h in hashtags],
        "likes": float(item.get("likesCount", item.get("likes", 0)) or 0),
        "comments": float(item.get("commentsCount", item.get("comments", 0)) or 0),
    }


def _extract_hashtags(text: str) -> list[str]:
    return [tok for tok in text.split() if tok.startswith("#")]


# ---------------------------------------------------------------------------
# STUB sample (skincare domain). Engagement numbers vary so momentum ranks them.
# ---------------------------------------------------------------------------
def _stub_posts(seeds: list[str]) -> list[dict]:
    return [
        {"caption": "Glass skin glow up routine that actually works",
         "hashtags": ["#glassskin", "#skincare", "#glowup"], "likes": 9200, "comments": 410},
        {"caption": "My honest skincare routine for clean beauty lovers",
         "hashtags": ["#cleanbeauty", "#skincare", "#skintok"], "likes": 3100, "comments": 120},
        {"caption": "Glass skin in 3 steps, no filter",
         "hashtags": ["#glassskin", "#skintok", "#dewyskin"], "likes": 8700, "comments": 380},
        {"caption": "Slugging before bed changed my skin barrier",
         "hashtags": ["#slugging", "#skinbarrier", "#skincare"], "likes": 6400, "comments": 290},
        {"caption": "That girl morning routine, skincare edition",
         "hashtags": ["#thatgirl", "#morningroutine", "#skincare"], "likes": 5200, "comments": 200},
        {"caption": "Dewy skin makeup look for spring",
         "hashtags": ["#dewyskin", "#springmakeup", "#glowup"], "likes": 4100, "comments": 150},
        {"caption": "Skin cycling explained for beginners",
         "hashtags": ["#skincycling", "#skintok", "#skincare"], "likes": 7300, "comments": 330},
        {"caption": "Slugging vs moisturizer, which wins",
         "hashtags": ["#slugging", "#skincare", "#skintok"], "likes": 5900, "comments": 260},
    ]
