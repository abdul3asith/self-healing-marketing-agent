"""
COMPARE  —  score scraped trends against OUR data, then rank.

This is the "compare to our data upstream" step. Two axes per candidate trend:

  * momentum  : is it hot right now in the domain?   (from Apify engagement)
  * relevance : does it fit US?                       (from YOUR past posts)

relevance = engagement-weighted average similarity between the candidate trend and the
topics that performed well on your own channel. Computed with embeddings when an
OPENAI_API_KEY is available; otherwise a deterministic keyword-overlap fallback so the
pipeline never stalls. Banned-word / off-brand candidates are penalized.

    final = W_RELEVANCE * relevance_norm + W_MOMENTUM * momentum_norm   (penalized)
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

from llm_client import embed

W_RELEVANCE = 0.6
W_MOMENTUM = 0.4


# ---------------------------------------------------------------------------
# 1. candidate extraction: aggregate co-occurring hashtags into trends
# ---------------------------------------------------------------------------
def extract_candidates(posts: list[dict], seeds: list[str]) -> list[dict]:
    """Group posts by hashtag (excluding the domain seeds themselves). Each candidate:
    {keyword, label, text, engagement, count}."""
    seed_set = {s.lstrip("#").lower() for s in seeds}
    agg: dict[str, dict] = defaultdict(lambda: {"engagement": 0.0, "count": 0, "captions": []})

    for p in posts:
        eng = p.get("likes", 0) + p.get("comments", 0)
        for tag in p.get("hashtags", []):
            key = tag.lstrip("#").lower()
            if not key or key in seed_set:
                continue
            agg[key]["engagement"] += eng
            agg[key]["count"] += 1
            if p.get("caption"):
                agg[key]["captions"].append(p["caption"])

    candidates = []
    for key, data in agg.items():
        candidates.append({
            "keyword": key,
            "label": f"#{key}",
            "text": f"#{key} " + " ".join(data["captions"][:3]),
            "engagement": data["engagement"],
            "count": data["count"],
        })
    return candidates


# ---------------------------------------------------------------------------
# 2. relevance: how much each candidate resembles YOUR top-performing posts
# ---------------------------------------------------------------------------
def _relevance_scores(candidates: list[dict], your_posts: list[dict]) -> tuple[list[float], str]:
    if not your_posts:
        return [0.0] * len(candidates), "none"

    cand_texts = [c["text"] for c in candidates]
    post_texts = [p["text"] for p in your_posts]
    weights = [max(p.get("engagement", 0.0), 1.0) for p in your_posts]

    vecs = embed(cand_texts + post_texts)
    if vecs is not None:
        cand_vecs = vecs[:len(cand_texts)]
        post_vecs = vecs[len(cand_texts):]
        scores = [_weighted_mean_sim(cv, post_vecs, weights) for cv in cand_vecs]
        return scores, "embedding"

    # Fallback: engagement-weighted keyword overlap (deterministic, offline).
    scores = [_keyword_relevance(c["text"], post_texts, weights) for c in candidates]
    return scores, "keyword-overlap"


def _weighted_mean_sim(cand_vec, post_vecs, weights) -> float:
    num = sum(w * _cosine(cand_vec, pv) for pv, w in zip(post_vecs, weights))
    return num / sum(weights)


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _keyword_relevance(cand_text: str, post_texts, weights) -> float:
    cand = _tokens(cand_text)
    if not cand:
        return 0.0
    total = 0.0
    for pt, w in zip(post_texts, weights):
        overlap = len(cand & _tokens(pt)) / len(cand)
        total += w * overlap
    return total / sum(weights)


# ---------------------------------------------------------------------------
# 3. combine, penalize, rank
# ---------------------------------------------------------------------------
def score_and_rank(candidates: list[dict], your_posts: list[dict], brand, n: int) -> list[dict]:
    """Returns the top-n candidates, each annotated with score components."""
    if not candidates:
        return []

    relevance, method = _relevance_scores(candidates, your_posts)
    momentum = [c["engagement"] for c in candidates]

    rel_n = _minmax(relevance)
    mom_n = _minmax(momentum)
    banned = [b.lower() for b in getattr(brand, "banned_words", [])]

    for c, r, m in zip(candidates, rel_n, mom_n):
        penalty = 0.5 if any(b in c["text"].lower() for b in banned) else 1.0
        c["relevance"] = r
        c["momentum"] = m
        c["score"] = penalty * (W_RELEVANCE * r + W_MOMENTUM * m)
        c["relevance_method"] = method

    return sorted(candidates, key=lambda c: c["score"], reverse=True)[:n]


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]
