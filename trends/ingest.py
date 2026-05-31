"""
INGEST  —  the upstream entry point. Scrape -> extract -> compare-to-our-data -> rank
-> emit Trend objects for the LIVE worker.

    select_trends(seeds, your_posts_path, n) -> list[Trend]

CLI (see what the pipeline picks):
    python -m trends.ingest --domain skincare
    APIFY_STUB=1 python -m trends.ingest          # offline, uses the stub scrape

Your-data file (CSV or JSON), one row/object per past post:
    {"caption": "...", "likes": 1234, "comments": 56}
Defaults to trends/sample_past_posts.json so it runs out of the box.

REMINDER: output feeds the live worker ONLY — never eval/trends.py (the frozen set).
"""

from __future__ import annotations

import argparse
import csv
import json
import os

from trends.apify_source import fetch_posts
from trends.compare import extract_candidates, score_and_rank

try:
    from core.contracts import Trend
    from eval.trends import BRAND_PROFILE
except Exception:  # pragma: no cover - offline fallback
    from types import SimpleNamespace

    def Trend(**kw):  # type: ignore
        return SimpleNamespace(**kw)

    BRAND_PROFILE = SimpleNamespace(banned_words=[])

_DEFAULT_POSTS = os.path.join(os.path.dirname(__file__), "sample_past_posts.json")
_DOMAIN_SEEDS = {
    "skincare": ["#skincare", "#cleanbeauty"],
    "fitness": ["#fitness", "#gymtok"],
    "food": ["#food", "#recipes"],
}


def load_your_posts(path: str) -> list[dict]:
    """Load your past posts; returns [{text, engagement}]. Missing file -> []."""
    if not path or not os.path.exists(path):
        return []
    if path.endswith(".json"):
        with open(path) as f:
            rows = json.load(f)
    else:
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
    posts = []
    for r in rows:
        caption = r.get("caption") or r.get("text") or ""
        likes = float(r.get("likes", 0) or 0)
        comments = float(r.get("comments", 0) or 0)
        posts.append({"text": caption, "engagement": likes + comments})
    return posts


def select_trends(seeds: list[str], your_posts_path: str = _DEFAULT_POSTS,
                  n: int = 8, brand=BRAND_PROFILE) -> list[Trend]:
    """Full upstream pipeline -> top-n Trend objects for the live worker."""
    posts, source_tag = fetch_posts(seeds)
    candidates = extract_candidates(posts, seeds)
    your_posts = load_your_posts(your_posts_path)
    ranked = score_and_rank(candidates, your_posts, brand, n)

    trends = []
    for i, c in enumerate(ranked):
        trends.append(Trend(
            id=f"live_{i}",
            platform="instagram",
            trend_label=c["label"],
            trend_keyword=c["keyword"],
            source=source_tag,
        ))
    return trends


def _cli():
    ap = argparse.ArgumentParser(description="Select live trends by comparing to your data.")
    ap.add_argument("--domain", default="skincare", help=f"one of {list(_DOMAIN_SEEDS)} or comma-separated #hashtags")
    ap.add_argument("--posts", default=_DEFAULT_POSTS, help="your past-posts file (CSV/JSON)")
    ap.add_argument("-n", type=int, default=8)
    args = ap.parse_args()

    seeds = _DOMAIN_SEEDS.get(args.domain) or [s if s.startswith("#") else f"#{s}"
                                               for s in args.domain.split(",")]

    posts, source_tag = fetch_posts(seeds)
    candidates = extract_candidates(posts, seeds)
    your_posts = load_your_posts(args.posts)
    ranked = score_and_rank(candidates, your_posts, BRAND_PROFILE, args.n)

    method = ranked[0]["relevance_method"] if ranked else "n/a"
    print(f"source={source_tag}  your_posts={len(your_posts)}  relevance_method={method}")
    print(f"candidates found={len(candidates)}  picking top {args.n}\n")
    print(f"{'rank':<5}{'score':<8}{'relev':<8}{'momtm':<8}trend")
    for i, c in enumerate(ranked):
        print(f"{i:<5}{c['score']:<8.2f}{c['relevance']:<8.2f}{c['momentum']:<8.2f}{c['label']}")


if __name__ == "__main__":
    _cli()
