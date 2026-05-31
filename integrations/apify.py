"""
APIFY  —  data acquisition (the Discover step). The only HARD dependency.

Pulls trending Facebook posts via the apify~facebook-posts-scraper actor using the
SYNC run endpoint (returns dataset items directly):

    POST https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items?token=<APIFY_TOKEN>
    Content-Type: application/json
    Body: { actor input JSON }     # POST is required to pass input

Token: Apify Console -> Integrations. Items are normalized to a stable shape:
    { text, reactions, comments, shares, url, time, pageName }

Mock-fallback: if no token is set, return deterministic mock posts so Discover runs
offline. Apify is the one integration you truly want live for the demo.

CRITICAL (see README): LIVE Apify feeds the RUNNING worker's trend stream. It must
NEVER replace eval/trends.py (the frozen eval set the Daytona sandbox grades against) —
a non-deterministic eval set would destroy the proof-of-fix.

Owner: data acquisition (the handoff's Apify layer).
"""

from __future__ import annotations

import os
import re

APIFY_TOKEN = os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN")
APIFY_FACEBOOK_ACTOR = os.getenv("APIFY_FACEBOOK_ACTOR", "apify~facebook-posts-scraper")
APIFY_BASE = "https://api.apify.com/v2"

# Default seed pages to scrape when the caller doesn't supply its own actor input.
DEFAULT_PAGE_URLS = [
    "https://www.facebook.com/Sephora",
    "https://www.facebook.com/glossier",
]

NORMALIZED_FIELDS = ("text", "reactions", "comments", "shares", "url", "time", "pageName")


def is_mock() -> bool:
    return not APIFY_TOKEN


# ------------------------------------------------------------------ normalization
def _to_int(value) -> int:
    """Coerce the many count shapes Facebook actors emit (int, str, {count}, list)."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        return int(digits) if digits else 0
    if isinstance(value, dict):
        for k in ("count", "totalCount", "total"):
            if k in value:
                return _to_int(value[k])
        return sum(_to_int(v) for v in value.values())
    if isinstance(value, list):
        return len(value)
    return 0


def normalize_item(item: dict) -> dict:
    """Map one raw actor item to the stable normalized shape. Defensive across the
    field-name variations different facebook-posts-scraper versions return."""
    reactions = (item.get("reactions") or item.get("likes") or item.get("reactionsCount")
                 or item.get("likesCount"))
    comments = item.get("comments") if "commentsCount" not in item else item.get("commentsCount")
    shares = item.get("shares") if "sharesCount" not in item else item.get("sharesCount")
    page_name = (item.get("pageName") or item.get("pageTitle")
                 or (item.get("user") or {}).get("name") or item.get("author") or "")
    return {
        "text": item.get("text") or item.get("message") or item.get("postText") or "",
        "reactions": _to_int(reactions),
        "comments": _to_int(comments),
        "shares": _to_int(shares),
        "url": item.get("url") or item.get("postUrl") or item.get("topLevelUrl") or "",
        "time": item.get("time") or item.get("date") or item.get("timestamp") or "",
        "pageName": page_name,
    }


def facebook_trends(page_urls: list[str] | None = None, *, results_limit: int = 20,
                    actor_input: dict | None = None) -> list[dict]:
    """Discover: fetch + normalize trending Facebook posts. Returns a list of
    normalized dicts (see NORMALIZED_FIELDS). Falls back to deterministic mock data
    when APIFY_TOKEN is unset so the demo runs offline."""
    if is_mock():
        return _mock_trends(results_limit)

    body = actor_input or {
        "startUrls": [{"url": u} for u in (page_urls or DEFAULT_PAGE_URLS)],
        "resultsLimit": results_limit,
    }

    import httpx  # lazy: mock mode needs zero deps
    url = f"{APIFY_BASE}/acts/{APIFY_FACEBOOK_ACTOR}/run-sync-get-dataset-items"
    resp = httpx.post(url, params={"token": APIFY_TOKEN}, json=body,
                      headers={"Content-Type": "application/json"}, timeout=120)
    resp.raise_for_status()
    items = resp.json()
    if not isinstance(items, list):
        items = items.get("items", []) if isinstance(items, dict) else []
    return [normalize_item(it) for it in items]


# --------------------------------------------------------- normalized -> Trend
def _keyword(text: str) -> str:
    """Heuristic 'rideable' keyword for the scorecard's references_trend check:
    first hashtag, else first TitleCase token, else first word."""
    tags = re.findall(r"#(\w+)", text)
    if tags:
        return tags[0]
    caps = re.findall(r"\b([A-Z][a-z]{2,})\b", text)
    if caps:
        return caps[0]
    words = text.split()
    return words[0] if words else "trend"


def to_trends(normalized: list[dict], *, platform: str = "facebook", source: str = "apify:facebook"):
    """Convert normalized posts into the worker's Trend contract for the LIVE stream.
    Uses core.contracts.Trend when available, else a SimpleNamespace (zero-dep)."""
    try:
        from core.contracts import Trend
    except Exception:
        from types import SimpleNamespace
        def Trend(**kw):  # type: ignore
            return SimpleNamespace(**kw)

    trends = []
    for i, post in enumerate(normalized):
        text = post.get("text", "").strip()
        label = (text[:80] + "…") if len(text) > 80 else (text or f"trend {i+1}")
        trends.append(Trend(id=f"live_{i+1}", platform=platform, trend_label=label,
                            trend_keyword=_keyword(text), source=source))
    return trends


# ------------------------------------------------------------------------ mock
def _mock_trends(limit: int) -> list[dict]:
    base = [
        {"text": "POV: my 5am skincare routine that changed everything #glowup", "reactions": 12400,
         "comments": 880, "shares": 320, "url": "https://facebook.com/p/1", "time": "2026-05-30", "pageName": "GlowDaily"},
        {"text": "GRWM for spring — the dewy look everyone is copying", "reactions": 9800,
         "comments": 540, "shares": 210, "url": "https://facebook.com/p/2", "time": "2026-05-30", "pageName": "BeautyHub"},
        {"text": "That girl aesthetic: 3 habits for a glass skin glow up", "reactions": 15200,
         "comments": 1320, "shares": 610, "url": "https://facebook.com/p/3", "time": "2026-05-29", "pageName": "CleanBeautyCo"},
        {"text": "Sunday reset routine: declutter, hydrate, repeat", "reactions": 7300,
         "comments": 410, "shares": 150, "url": "https://facebook.com/p/4", "time": "2026-05-29", "pageName": "SelfCareDaily"},
        {"text": "Things in my cart this month — underrated skincare finds", "reactions": 6100,
         "comments": 330, "shares": 120, "url": "https://facebook.com/p/5", "time": "2026-05-28", "pageName": "ShelfieReviews"},
        {"text": "Day in the life of a skincare lover ✨", "reactions": 8800,
         "comments": 470, "shares": 190, "url": "https://facebook.com/p/6", "time": "2026-05-28", "pageName": "GlowDaily"},
    ]
    # Deterministic: sort by engagement so "trending" is meaningful, then cap.
    base.sort(key=lambda p: p["reactions"] + p["comments"] + p["shares"], reverse=True)
    return base[:limit]
