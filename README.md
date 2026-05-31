# Self-Healing Agent — Organic Social Pipeline (Instagram)

**Theme: "Agents That Act."** The act: an agent diagnoses and ships a *verified* fix to another agent — no human in the loop.

A **worker agent** (the *patient*) writes Instagram content from a trend, under hard
constraints. It silently degrades (a bad prompt deploy). A **fixer agent + pipeline**
(the *product*) reads the worker's logs, detects the quality drop, diagnoses it,
generates a candidate prompt fix, **validates that fix against a frozen eval set inside
an isolated Daytona sandbox**, and promotes it to production **only if the score
actually improves** — otherwise discards and retries. Then it goes back to watching.

> **Pivot from the original handoff:** the worker writes *organic* content (FB/IG/TikTok)
> instead of paid ad copy. Trends come from **Apify** (or our own channels), compared to
> our data **upstream**. The single live platform for the demo is **Instagram**
> (`platform` is just a field — flipping to TikTok is a one-line change). Everything
> else in the locked design is unchanged: the scorecard is still the single source of
> truth, the fixer still reads logs only, fixes are still sandbox-validated before promotion.

---

## The one idea that matters

The **scorecard** (`eval/scorecard.py`) is three things at once:
1. our **definition of quality** (7 deterministic checks → one number),
2. our **failure detector** (rolling avg trips a threshold),
3. our **proof-of-fix** (a candidate is promoted only if it *beats* this score in the sandbox).

It's deterministic Python — **never an LLM-as-judge** — and it's duck-typed, so it grades
any log-shaped object. That decoupling is the pitch: *works on any agent that emits logs.*

---

## Team split (4 people)

Freeze `core/contracts.py` together first (5 min), then parallelize.

| Person | Owns | Files |
|---|---|---|
| **A — Eval & Worker** (the patient) | scorecard, frozen eval set, dumb worker, the two prompts | `eval/scorecard.py`, `eval/trends.py`, `worker/agent.py`, `worker/prompts.py` |
| **B — Fixer reasoning** | drop detection + the two LLM steps | `fixer/detect.py`, `fixer/diagnose.py`, `fixer/generate.py` |
| **C — Sandbox & orchestration** | Daytona validation, the loop, the model client | `fixer/validate.py`, `fixer/orchestrate.py`, `llm_client.py` |
| **D — Backend, dashboard, demo** | Insforge store, dashboard UI, demo driver | `backend/store.py`, `dashboard/`, `demo.py` |

Everyone codes against the same interfaces, so any unfinished sponsor integration is
stubbed and the loop still runs (in-memory store + local-validate fallback ship working).

---

## Setup

```bash
git clone <repo> && cd self-healing-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in keys (see checklist below)
```

Verify the core with **zero keys / zero network**:
```bash
python run_scorecard.py       # GOOD=1.00, DEGRADED low, INVALID=0.00
```

Run the full self-healing demo (needs a model key, or set `DAYTONA_STUB=1` + a model key):
```bash
python demo.py
```

---

## Logins / accounts to create (and what each unlocks)

Create these accounts and paste the keys into `.env`. **Memory store + local validate
work with no setup**, so the only key you *truly* need to see the loop run end-to-end is
one model key (OpenAI).

| # | Service | Where to sign up | What you get | `.env` keys | Needed for |
|---|---|---|---|---|---|
| 1 | **OpenAI** | platform.openai.com → API keys → add billing | OpenAI-compatible model endpoint (override `OPENAI_BASE_URL`/`OPENAI_MODEL` for any compatible provider) | `OPENAI_API_KEY` | all LLM calls |
| 2 | **Daytona** | daytona.io → Dashboard → API keys | isolated sandboxes (<90ms) to validate fixes | `DAYTONA_API_KEY`, `DAYTONA_TARGET` | the credibility/proof-of-fix step |
| 3 | **Insforge** | insforge.dev → create project → Project URL + API Key | Postgres BaaS for the audit trail | `INSFORGE_API_KEY`, `INSFORGE_BASE_URL` | persistence + audit (item 6) |
| 4 | **Apify** | apify.com → Console → Settings → Integrations → API token | trend scraping ($5/mo free credits) | `APIFY_API_TOKEN` | live trend ingestion |
| 5 | **Kalibr** | kalibr.systems (+ hackathon access) | orchestration / autonomous routing layer | `KALIBR_API_KEY` | orchestration (else native loop) |
| 6 | **GitHub** | github.com → new repo, invite the 4 of you | shared repo | — | collaboration |
| 7 | *(stretch)* **Render** | render.com | deploy the dashboard | — | stretch deploy |

Priority order if time is short: **#1 → #2 → #3 → #4 → #5**. (#6 first.)

---

## Build order (definition of done — protect items 1–5)

1. ✅ Scorecard + eval set produce a score — **done, verified** (`run_scorecard.py`).
2. Worker produces scored runs on good vs degraded prompts; scores differ. *(Person A — wire `llm_client`.)*
3. Detection fires when rolling score drops below threshold. *(Person B — `detect.py` done; feed it real runs.)*
4. Fixer generates a candidate, validates in a **real Daytona sandbox**, returns a score. *(Person C.)*
5. Promote-if-better works; live prompt updates; score recovers. *(Person C — `orchestrate.py` done; needs real validate + store.)*
6. Everything persists to Insforge; dashboard shows live chart + fix log. *(Person D.)*
7. `demo.py` runs the section-9 sequence end to end, deterministically. *(Lead/Person D — driver done.)*
8. *(Stretch)* auto-deploy.

If time runs out, cut in reverse. Items 1–5 are the irreducible core.

---

## The demo (the money moment)

Steady green (~1.0) → deploy degraded prompt → score craters (~0.4, red) → fixer
auto-detects → **first candidate FAILS the sandbox eval and is discarded** → second
candidate PASSES → promoted → score recovers to green, no human touched it → show the
audit trail of the promoted fix.

Step 4 (fail-then-recover) is engineered to fire reliably: `attempt_self_heal(...,
force_first_fail=True)` uses a deliberately weak first hypothesis. Set `False` for pure
autonomous behavior.

---

## Critical gotcha — keep these two separate

**Live Apify** feeds the *running* worker (the stream the detector watches).
The **frozen eval set** (`eval/trends.py`, 8 committed trends) is the *only* thing the
Daytona sandbox grades candidates against. The sandbox must **never** hit live Apify —
a non-deterministic eval set would destroy the proof-of-fix. Same schema, different jobs.

---

## Defaults (open decision #4, confirmed)

8 eval trends · threshold **0.8** · window **10 runs** · max **3** fix retries.
