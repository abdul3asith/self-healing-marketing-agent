# Capture Kit — Human Workflow → Agent Blueprint

**The inverse of the rest of this repo.** The self-healing agent is the *run-time back
half*: it watches an **agent** and heals it, with **no human in the loop**. This package
is the *design-time front half*: it watches a **human** do a real job through three
windows, stitches what it sees into one honest timeline (grouped by a job-level
`trace_id`), and reads that timeline **backwards** into an agent blueprint — tools the
agent must have, rules distilled from rejected options, guardrails where output slips
through silently, and explicit "keep a human here" markers on low-confidence judgment
calls.

> **One-sentence version:** watch a human through three windows, stitch it into one
> honest timeline, then read that timeline backwards to figure out exactly what an agent
> would need — and, crucially, where it shouldn't be trusted alone.

---

## The setup: one job, watched from three angles

A strategist runs the April content cycle for Client X. That whole cycle gets **one
`trace_id`**. Everything that happens during it — no matter which window captures it —
is stamped with that same id. That shared label is the trick that lets you later line up
*"how the human did April"* against *"how the agent did April"* side by side.

| Window | Watches | Captures | Module |
|---|---|---|---|
| **1 — tools they touch** | tool calls (e.g. Apify) | not *that* they ran it, but **what they chose to feed it** (pages, hashtags, last 7 days) | `record_tool_use` in `capture/windows.py` |
| **2 — the document** | the proposal between saves | the **transformation** (3 post ideas became 2), no narration needed | `record_doc_revision` in `capture/windows.py` |
| **3 — the choice in their head** | a quick form at decision time | considered / picked / **rejected + why** + confidence. The *"why I rejected it"* is the gold | `record_decision` in `capture/windows.py` |

## Then something goes wrong — and that matters most

The dangerous failure isn't the loud error — it's the **quiet bad output that slips
through** and gets passed downstream unnoticed. In the demo, the performance-tracking
scrape returns bad data. The kit flags it **hard**, because that's exactly the spot
where an agent would fail silently and nobody would catch it.

We don't reinvent the detector — we **reuse** the repo's existing
`eval.gate1.web_scraping` contract (`field_completeness >= 0.8`). See
`capture/silent_failure.py`.

## Assembling the story

`capture/timeline.py` groups observations by `trace_id`, orders them by time, and renders
the clean chain:

```
scraped trends  ->  wrote proposal (3 ideas -> 2)  ->  chose #spring (rejected 2, only 60% sure)
    ->  tracked April performance  ->  bad data slipped through (flagged)
```

That's the human's **actual** workflow — including the judgment call and the mistake.

## Turning the story into an agent blueprint

`capture/blueprint.py` reads the timeline backwards, **deterministically** (no
LLM-as-judge — same discipline as `eval/scorecard.py`):

| Timeline piece | Becomes | Example |
|---|---|---|
| tool step | **Capability** | "agent must call `apify` with inputs like these" |
| rejection + reason | **Rule** | "reject `#sale` for Client X — a premium brand" |
| silent failure | **Guardrail** | "human verification checkpoint at the performance scrape" |
| low-confidence call | **Human-in-the-loop** | "`which trend to ride` (60%): judgment, not rote" |

---

## trace_id strategy (the key design decision)

The repo already has a `trace_id`, but it's **per LLM step**: Kalibr's `decide()` /
`get_alternative()` mint `mock-trace::<uuid>` for a single model call (see
`integrations/kalibr.py` and `fixer/runstep.py`). That's the wrong granularity for a
human job spanning many tools, edits, and decisions.

So we mint a **job-level** `trace_id` (`job::<uuid>`) in `capture/trace.py`. Everything
the three windows record is stamped with it. Any per-step Kalibr trace_id that occurs
inside the job is kept as a **child** reference in a tool observation's
`data["child_trace_id"]` — it points *up* to the job trace, never replaces it.

## Data model (`capture/contracts.py`)

Stdlib `dataclass`es (not pydantic) so the kit runs **zero-dependency** — it's meant to
sit quietly beside a human's tools without a heavy install.

- **`Observation`** — the atom. `{id, trace_id, window, kind, summary, actor, data, flags, ts, seq}`. Every window emits these; all share the job `trace_id`. `seq` is assigned by the store in real-time order for deterministic timelines.
- **`AgentBlueprint`** — `{capabilities[], rules[], guardrails[], human_in_the_loop[], narrative}`, each item carrying `derived_from` (the observation id it was distilled from) for a full audit trail.

---

## How this fits the existing repo

It **sits beside** the self-healing agent and **feeds** it. The blueprint this kit emits
is the upstream source of the very artifacts the run-time loop enforces:

| Blueprint output | Becomes, in the run-time half |
|---|---|
| **Rules** (from rejections) | new deterministic checks in `eval/scorecard.py` (the definition of quality) |
| **Guardrails** (from silent failures) | Gate-1 / sandbox gates in `eval/gate1.py` + `fixer/validate.py` |
| **Human-in-the-loop** markers | the steps you *don't* let `worker/agent.py` run autonomously |
| **Capabilities** (from tools) | the tool surface in `api.py` (e.g. `/tools/scrape_trends`) |

**Reused as-is:** `eval.gate1.web_scraping` (silent-failure detector), the
`MemoryStore`/`InsforgeStore` dual-backend pattern (`backend/store.py` → mirrored in
`capture/store.py`), the mock-first / zero-key ethos, and the deterministic,
never-LLM-as-judge grading discipline.

**Newly built here (no equivalent existed):** the job-level trace, the document watcher
(Window 2), the reasoning capture (Window 3 — the inverse of `fixer/diagnose.py`, which
makes the *agent* reason; here we capture the *human's* reasoning), the timeline
assembler, and the blueprint translator.

---

## Run it (zero keys, zero network)

```bash
python -m capture.demo      # preferred
python capture/demo.py      # also works (path bootstrap inside)
```

Deterministic offline output: a job trace, a flagged silent failure
(`field_completeness 0.10`), the honest timeline, and a blueprint with 2 capabilities,
2 rules, 1 guardrail, and 1 human-in-the-loop marker.

## File map

```
capture/
  contracts.py       Observation, JobTrace, AgentBlueprint (zero-dep dataclasses)
  trace.py           job-level trace_id minting (job::<uuid>)
  store.py           Memory + Insforge capture store behind one interface
  windows.py         the 3 connectors: record_tool_use / record_doc_revision / record_decision
  silent_failure.py  reuses eval.gate1.web_scraping as the guardrail trigger
  timeline.py        assemble + render observations for one trace_id
  blueprint.py       translate timeline -> AgentBlueprint (deterministic)
  demo.py            the April / Client-X scenario, end to end
```

## What's stubbed / next

- **`InsforgeCaptureStore`** — interface only; back the methods with REST (same as `backend/store.py`). Can share one Insforge project with the agent audit trail (different tables).
- **Real Window-2 watcher** — `record_doc_revision` takes snapshots; a production hook would diff Google Docs / Notion saves automatically.
- **Real Window-3 capture** — `record_decision` is the data shape; the UI is a quick in-context form fired at decision time.
- **Optional LLM-assisted distillation** — the translator is deterministic today; an LLM layer (run through `fixer/runstep.py` for model-level self-healing) could phrase richer rules from free-text rejection reasons. Keep the deterministic path as the source of truth.
