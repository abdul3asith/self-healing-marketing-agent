"""
HTTP API  —  expose the self-healing marketing agent as TOOLS a Claude chat/agent can call.

Every endpoint under /tools is a clean, single-purpose JSON action. FastAPI auto-publishes
an OpenAPI schema at /openapi.json (and interactive docs at /docs) — that schema is exactly
what you paste into an Anthropic tool definition (or wrap in an MCP server) so a Claude window
on a live site can invoke this pipeline on demand.

Tools exposed:
  POST /tools/scrape_trends       — Apify: scrape trending posts from a Facebook page.
  POST /tools/generate_post       — Worker: write an on-brand IG post, MODEL-level self-healing.
  POST /tools/run_self_heal       — Fixer: full PROMPT-level detect->diagnose->fix->validate loop.
  GET  /tools/kalibr_intelligence — Kalibr: per-goal routing stats (the model-healing brain).
  GET  /health                    — liveness + which integrations are LIVE vs MOCK.

Run locally:
    uvicorn api:app --reload --port 8000
    open http://localhost:8000/docs

Expose to a live Claude window:
    ngrok http 8000          # or deploy anywhere; CORS is open so a browser chat can call it.
"""

from __future__ import annotations

import os

# Load .env before any module reads env vars (Apify/NEAR/Kalibr all read at import time).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import fixer.validate as _validate_mod
from backend.store import MemoryStore
from core.contracts import Trend
from eval.gate1 import content_draft
from eval.scorecard import score_output
from eval.trends import BRAND_PROFILE
from fixer.detect import rolling_avg
from fixer.orchestrate import attempt_self_heal
from fixer.runstep import register_default_paths, run_step
from integrations.apify import _keyword, facebook_trends, is_mock as apify_is_mock
from integrations.kalibr import get_kalibr
from llm_client import is_mock as llm_is_mock
from worker.agent import _parse
from worker.prompts import build_prompt


# ---------------------------------------------------------------------------
# App + lifespan (register Kalibr paths once at startup)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        register_default_paths()  # Kalibr only routes to registered NEAR-backed paths
    except Exception:
        pass  # Kalibr may be unreachable; mock/skip so the API still serves.
    yield


app = FastAPI(
    title="Self-Healing Marketing Agent API",
    description=(
        "Tool surface for a Claude agent: scrape live trends, generate on-brand posts with "
        "model-level self-healing (Kalibr + NEAR), and run the prompt-level self-heal loop."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Open CORS so a Claude chat widget on any live site can call these tools from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ScrapeTrendsRequest(BaseModel):
    page_url: str = Field("https://www.facebook.com/natgeo",
                          description="Facebook page URL to scrape trending posts from.")
    limit: int = Field(5, ge=1, le=50, description="Max posts to return.")


class TrendItem(BaseModel):
    label: str = Field(..., description="Short human-readable trend label (feed into generate_post).")
    keyword: str = Field(..., description="Keyword that must appear in generated content.")
    text: str
    reactions: int
    comments: int
    shares: int
    engagement: int
    url: str
    page_name: str


class ScrapeTrendsResponse(BaseModel):
    mode: str = Field(..., description="LIVE if APIFY_TOKEN is set, else MOCK.")
    page_url: str
    count: int
    trends: list[TrendItem]


class GeneratePostRequest(BaseModel):
    trend_label: str = Field(..., description="The trend to write about, e.g. a scraped Nat Geo post.")
    trend_keyword: str | None = Field(None, description="Keyword the post must include; auto-derived if omitted.")
    prompt_version: str = Field("good", description="'good' (full rules) or 'degraded' (vague) for demos.")
    niche: str | None = Field(None, description="Override brand niche.")
    required_cta: str | None = Field(None, description="Override required call-to-action.")
    required_hashtag: str | None = Field(None, description="Override required hashtag.")


class GeneratePostResponse(BaseModel):
    hook: str | None
    caption: str | None
    hashtags: list[str]
    brand_score: float = Field(..., description="0..1 fraction of deterministic brand checks passed.")
    checks: dict[str, bool]
    gate1_ok: bool = Field(..., description="Did the model output pass the Gate-1 usability contract?")
    model_id: str | None = Field(..., description="Kalibr path of the NEAR model that produced the post.")
    near_model: str | None = Field(..., description="Resolved NEAR model slug.")
    heals: int = Field(..., description="How many times the step rerouted to another model before succeeding.")
    raw_output: str = Field(..., description="The raw model output (pre-parse).")
    heal_trace: list[dict] = Field(default_factory=list, description="decide/attempt/heal/outcome events.")


class SelfHealRequest(BaseModel):
    n_runs: int = Field(10, ge=4, le=50, description="Degraded runs to seed so a drop is detectable.")
    force_first_fail: bool = Field(True, description="Demo: first candidate fails, second promotes.")
    use_sandbox: bool = Field(False, description="True = real Daytona sandbox; False = local stub (reliable).")


class SelfHealResponse(BaseModel):
    detected: bool
    promoted: bool | None = None
    score_before: float
    score_after: float | None = None
    attempts: list[dict] = Field(default_factory=list)
    attestation: str | None = None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@app.get("/health", summary="Liveness + integration modes")
def health():
    """Report which integrations are LIVE (keys present) vs MOCK (offline fallback)."""
    kalibr = get_kalibr()
    return {
        "status": "ok",
        "integrations": {
            "apify": "live" if not apify_is_mock() else "mock",
            "llm_near": "live" if not llm_is_mock() else "mock",
            "kalibr": "live" if not kalibr.mock else "mock",
            "daytona": "stub" if _validate_mod.DAYTONA_STUB else "live",
        },
    }


@app.post("/tools/scrape_trends", response_model=ScrapeTrendsResponse,
          summary="Scrape trending Facebook posts (Apify)")
def scrape_trends(req: ScrapeTrendsRequest) -> ScrapeTrendsResponse:
    """Pull the top trending posts from a Facebook page and return them ranked by engagement.
    Feed any returned `label`/`keyword` straight into generate_post."""
    posts = facebook_trends(page_urls=[req.page_url], results_limit=req.limit)
    items: list[TrendItem] = []
    for p in posts:
        text = (p.get("text") or "").strip()
        reactions, comments, shares = p.get("reactions", 0), p.get("comments", 0), p.get("shares", 0)
        label = (text[:80] + "…") if len(text) > 80 else (text or "trend")
        items.append(TrendItem(
            label=label, keyword=_keyword(text), text=text,
            reactions=reactions, comments=comments, shares=shares,
            engagement=reactions + comments + shares,
            url=p.get("url", ""), page_name=p.get("pageName", ""),
        ))
    return ScrapeTrendsResponse(
        mode="MOCK" if apify_is_mock() else "LIVE",
        page_url=req.page_url, count=len(items), trends=items,
    )


@app.post("/tools/generate_post", response_model=GeneratePostResponse,
          summary="Generate an on-brand IG post (model-level self-healing)")
def generate_post(req: GeneratePostRequest) -> GeneratePostResponse:
    """Write ONE on-brand Instagram post for a trend. The single model call flows through
    run_step, so a down/garbled NEAR model self-heals (reroutes via Kalibr) before scoring."""
    brand = BRAND_PROFILE.model_copy(update={
        k: v for k, v in {
            "niche": req.niche, "required_cta": req.required_cta,
            "required_hashtag": req.required_hashtag,
        }.items() if v is not None
    })
    trend = Trend(id="api", platform="facebook", trend_label=req.trend_label,
                  trend_keyword=req.trend_keyword or _keyword(req.trend_label), source="api")

    events: list[dict] = []
    prompt = build_prompt(req.prompt_version, trend, brand)
    step = run_step("outreach_generation", [{"role": "user", "content": prompt}],
                    content_draft, on_event=events.append)
    draft = _parse(step.output)
    score, checks = score_output(draft, brand, trend)

    return GeneratePostResponse(
        hook=getattr(draft, "hook", None),
        caption=getattr(draft, "caption", None),
        hashtags=list(getattr(draft, "hashtags", []) or []),
        brand_score=score, checks=checks,
        gate1_ok=step.ok, model_id=step.model_id, near_model=step.near_model,
        heals=step.heals, raw_output=step.output, heal_trace=events,
    )


@app.post("/tools/run_self_heal", response_model=SelfHealResponse,
          summary="Run the prompt-level self-heal loop (detect→diagnose→fix→validate→promote)")
def run_self_heal(req: SelfHealRequest) -> SelfHealResponse:
    """Seed a quality drop (degraded prompt), then run the full self-heal cycle and report
    before/after scores. Uses a fresh in-memory store per call so the tool is deterministic."""
    from worker.agent import run_worker
    from eval.trends import EVAL_TRENDS
    import itertools

    store = MemoryStore(initial_prompt_version="degraded")
    cycle = itertools.cycle(EVAL_TRENDS)
    for _ in range(req.n_runs):
        store.save_run(run_worker(next(cycle), BRAND_PROFILE, store.get_live_prompt()))
    score_before = rolling_avg(store.recent_runs(limit=req.n_runs))

    # Default to the local validator so the tool never stalls on Daytona auth/SSL.
    prev = _validate_mod.DAYTONA_STUB
    if not req.use_sandbox:
        _validate_mod.DAYTONA_STUB = True
    try:
        result = attempt_self_heal(store, force_first_fail=req.force_first_fail)
    finally:
        _validate_mod.DAYTONA_STUB = prev

    score_after = None
    if result.get("promoted"):
        for _ in range(req.n_runs):
            store.save_run(run_worker(next(cycle), BRAND_PROFILE, store.get_live_prompt()))
        score_after = rolling_avg(store.recent_runs(limit=req.n_runs))

    return SelfHealResponse(
        detected=result.get("detected", False),
        promoted=result.get("promoted"),
        score_before=score_before, score_after=score_after,
        attempts=result.get("attempts", []),
        attestation=result.get("attestation"),
    )


@app.get("/tools/kalibr_intelligence", summary="Kalibr routing stats per goal")
def kalibr_intelligence():
    """Per-goal success rate, attempts, status and trend — the model-level self-healing brain."""
    kalibr = get_kalibr()
    out = {}
    for goal in ("outreach_generation", "summarization", "research", "web_scraping"):
        try:
            s = kalibr.stats(goal) or {}
            ins = kalibr.insights(goal) or {}
        except Exception as e:
            out[goal] = {"error": str(e)}
            continue
        out[goal] = {
            "success_rate": s.get("success_rate", ins.get("success_rate", 0.0)),
            "attempts": s.get("attempts", s.get("total_attempts", 0)),
            "status": ins.get("status", "unknown"),
            "trend": ins.get("trend", "n/a"),
        }
    return {"mode": "mock" if kalibr.mock else "live", "goals": out}


@app.get("/", summary="API index")
def index():
    return {
        "name": "Self-Healing Marketing Agent API",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "tools": ["/tools/scrape_trends", "/tools/generate_post",
                  "/tools/run_self_heal", "/tools/kalibr_intelligence"],
    }
