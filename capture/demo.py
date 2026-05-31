"""
CAPTURE DEMO  —  the human-workflow capture kit, end to end, deterministically.

The scenario from the brief: a strategist runs the April content cycle for Client X.
The whole cycle gets ONE trace_id. The kit watches through three windows, the kit
flags a quiet bad-data failure nobody noticed, then it stitches everything into one
honest timeline and reads that timeline backwards into an agent blueprint.

Run (zero keys, zero network):
    python -m capture.demo        # preferred
    python capture/demo.py        # also works (path bootstrap below)
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

# Allow `python capture/demo.py` (not just `-m capture.demo`) by putting the repo root
# on sys.path, mirroring how the top-level demo.py is run from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capture.blueprint import translate
from capture.bridge import compile_rules_to_checks, evaluate_checks
from capture.silent_failure import flag_silent_failure
from capture.store import get_capture_store
from capture.timeline import assemble, render
from capture.trace import new_job_trace
from capture.windows import record_decision, record_doc_revision, record_tool_use


def main() -> None:
    store = get_capture_store()

    # One job, one label. Everything below is stamped with this trace_id.
    trace = new_job_trace("April content cycle — Client X")
    store.save_trace(trace)
    print(f"JOB  {trace.trace_id}")
    print(f"     {trace.title}\n")

    # --- Window 1: the tool they touch + WHAT they chose to feed it -----------
    record_tool_use(
        store, trace,
        tool="apify.facebook_posts_scraper",
        inputs={"pages": ["@competitorA", "@competitorB"],
                "hashtags": ["#spring", "#sale", "#cleanbeauty"],
                "days": 7},
        output_meta={"posts_returned": 42},
        summary="scraped trends (competitor pages, top hashtags, last 7 days)",
    )

    # --- Window 2: the document evolving between saves ------------------------
    record_doc_revision(
        store, trace,
        doc_id="proposal",
        before={"post_ideas": ["#spring routine", "#sale push", "dance challenge"]},
        after={"post_ideas": ["#spring routine", "glass-skin tips"]},
        summary="wrote proposal (3 ideas -> 2)",
    )

    # --- Window 3: the choice in their head (the gold is the rejection 'why') -
    record_decision(
        store, trace,
        question="which trend to ride for Client X",
        considered=["#spring", "#sale", "dance challenge"],
        picked="#spring",
        rejected=[
            {"option": "#sale", "reason": "Client X is a premium brand — a #sale trend cheapens it"},
            {"option": "dance challenge", "reason": "off-brand for a skincare/clean-beauty client"},
        ],
        confidence=0.6,  # only 60% sure -> a judgment call, not rote
        summary="chose #spring (rejected 2, only 60% sure)",
    )

    # --- Window 1 again: a performance scrape that quietly returns bad data ---
    bad_rows = [
        {"text": "April recap post", "reactions": "", "comments": "", "shares": "",
         "url": "", "time": "", "pageName": ""},
        {"text": "", "reactions": "", "comments": "", "shares": "",
         "url": "", "time": "", "pageName": ""},
        {"text": "spring launch", "reactions": "", "comments": "", "shares": "",
         "url": "", "time": "", "pageName": ""},
    ]
    record_tool_use(
        store, trace,
        tool="apify.facebook_posts_scraper",
        inputs={"pages": ["@clientX"], "metric": "engagement", "days": 30},
        output_meta={"posts_returned": len(bad_rows)},
        summary="tracked April performance",
    )
    ok, sf = flag_silent_failure(store, trace, step="performance tracking scrape", rows=bad_rows)
    print(f"GUARDRAIL  scrape data usable? {ok}")
    if sf:
        print(f"           {sf.summary}\n")

    # --- Assemble the honest timeline ----------------------------------------
    timeline = assemble(store, trace.trace_id)
    print("TIMELINE")
    print(f"  {render(timeline)}\n")

    # --- Translate the timeline backwards into an agent blueprint ------------
    bp = translate(store, trace)

    print("BLUEPRINT — what an agent would need (and where not to trust it)\n")

    print("  CAPABILITIES (tools the agent must have)")
    for c in bp.capabilities:
        print(f"    - {c.tool}  e.g. inputs={c.example_inputs}")

    print("\n  RULES (distilled from rejected options)")
    for r in bp.rules:
        print(f"    - {r.rule}\n        why: {r.rationale}")

    print("\n  GUARDRAILS (where output slips through silently)")
    for g in bp.guardrails:
        print(f"    - at '{g.at_step}': {g.action}\n        check: {g.check}")

    print("\n  HUMAN-IN-THE-LOOP (judgment, not rote)")
    for h in bp.human_in_the_loop:
        print(f"    - '{h.step}' (confidence {h.confidence:.0%}): {h.reason}")

    # --- Gap #1 closed: blueprint rules -> live scorecard checks --------------
    checks = compile_rules_to_checks(bp)
    print("\nBRIDGE — blueprint rules compiled into live scorecard checks (capture/bridge.py)")
    print(f"  generated checks: {[name for name, _ in checks]}")
    compliant = SimpleNamespace(
        hook="POV: your spring glow-up",
        caption="Follow for more. A calm spring routine refresh.",
        hashtags=["#glowroutine", "#spring", "#skincare"])
    violating = SimpleNamespace(
        hook="Huge #sale this weekend only",
        caption="Our sale is live — grab the dance challenge kit!",
        hashtags=["#sale", "#dance"])
    print(f"  compliant draft -> {evaluate_checks(checks, compliant)}")
    print(f"  violating draft -> {evaluate_checks(checks, violating)}")

    print("\nAUDIT")
    print(f"  observations={len(timeline)}  blueprints={len(store.blueprints(trace.trace_id))}")


if __name__ == "__main__":
    main()
