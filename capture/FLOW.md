# Where we are now — the full flow

Your two whiteboard sketches are the two halves of one self-improving system:

- **Whiteboard #1** (identify → propose → track, looping) = the **human / business cycle** the capture kit watches.
- **Whiteboard #2** (prompt → Claude → Agent → Apify → output, with feedback) = the **agent self-heal runtime**.

They meet at the **scorecard** — the shared definition of "good." The human *writes* the
checks (top-down); the outside systems *optimize against* them (bottom-up).

```mermaid
flowchart TB
    subgraph A["LOOP A — Human / business cycle  (whiteboard #1)"]
        direction LR
        A1["1. Identify trends<br/>(Apify)"] --> A2["2. Propose ideas<br/>(doc: 3 -> 2)"] --> A3["3. Track performance<br/>(logs / Apify)"]
        A3 -. next cycle .-> A1
    end

    subgraph B["LOOP B — Capture kit / TEACH  (capture/)  [BUILT]"]
        B1["3 windows<br/>tool | document | decision"] --> B2["honest timeline<br/>(one job trace_id)"] --> B3["AgentBlueprint<br/>rules | guardrails | HITL | capabilities"]
    end

    SC["SCORECARD — shared 'definition of good'<br/>(eval/scorecard.py)"]

    subgraph C["LOOP C — Agent self-heal  (whiteboard #2)  [BUILT]"]
        C1["prompt -> Claude<br/>(claude_tools.py)"] --> C2["Agent / worker<br/>(worker/agent.py)"] --> C3["Apify<br/>(integrations/apify.py)"] --> C4["output / Run logs"]
        C2 -. "model heal: Kalibr + NEAR (fixer/runstep.py)" .-> C1
        C4 --> C5["detect -> diagnose -> generate -> Daytona -> promote<br/>(fixer/orchestrate.py)"]
        C5 -. "prompt heal" .-> C1
    end

    A1 -->|Window 1| B1
    A2 -->|Window 2| B1
    A3 -->|"Window 3 + silent-failure flag"| B1
    B3 -->|"writes checks / gates  [BUILT: capture/bridge.py]"| SC
    SC -->|grades every run| C4
    C4 -.->|"real performance  [GAP: not yet a quality signal]"| A3
```

## Your sketches → current code

| Whiteboard #1 step | Run-time module | Capture-kit module |
|---|---|---|
| 1. Identify trends (Apify) + `[1][2][3]` pick | `integrations/apify.py`, `/tools/scrape_trends` | `capture/windows.record_tool_use` (Window 1) + `record_decision` (Window 3 — the *why* of the pick) |
| 2. Propose content ideas (doc) | `worker/agent.py` | `capture/windows.record_doc_revision` (Window 2) |
| 3. Track performance (logs / Apify) | `eval/scorecard.py` + `fixer/detect.py` on `Run` logs | `capture/silent_failure.py` (flags bad-data scrape) |
| the big loop arrow | the two self-heal loops below | the capture → blueprint "teach" loop |

| Whiteboard #2 node | Module |
|---|---|
| prompt → Claude | `claude_tools.py` (Claude calls the tools) |
| Agent | `worker/agent.py` (each call wrapped by `fixer/runstep.py`) |
| Apify | `integrations/apify.py` |
| O (output) | `ContentDraft` / `Run` (`core/contracts.py`) |
| Agent → Claude feedback | model heal (Kalibr, `fixer/runstep.py`) + prompt heal (`fixer/orchestrate.py`) |

## Does it work? Build status of each connection

**Built + verified (`demo.py`, `python -m capture.demo`):**
- Loop C agent self-heal: model-level (Kalibr/NEAR) and prompt-level (Daytona promote-if-better).
- Loop B capture → timeline → blueprint.
- Window 3 silent-failure flag → guardrail.

**Still open (to make it a fully closed dual loop):**
1. **Blueprint → scorecard bridge** — **now wired** (`capture/bridge.py`): each blueprint `rule` carrying an `avoid` token compiles into a deterministic check folded in via `score_output(..., extra_checks=...)`. This is the link that makes *"the user improves the system"* automatic.
2. **Real performance → quality signal** — "track performance" in whiteboard #1 implies engagement outcomes loop back, but current "quality" = scorecard constraint-compliance, not actual post performance. Good-but-underperforming content isn't penalized yet.
3. **trace_id join** — job-level (capture) vs per-step (Kalibr) live side by side; `data["child_trace_id"]` exists but nothing populates it during a live run.
