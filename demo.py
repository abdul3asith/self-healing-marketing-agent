"""
DEMO DRIVER  —  the section-9 sequence, end to end, deterministically.

  1. worker on GOOD prompt -> score steady ~1.0 (green)
  2. operator "deploys" DEGRADED prompt -> score craters ~0.4 (red)
  3. fixer auto-detects the drop (Detection)
  4. FIRST candidate fails the sandbox eval -> discarded   <-- the money moment
  5. SECOND candidate passes the sandbox -> promoted live
  6. worker score recovers to ~1.0 (green), no human touched it
  7. show the audit trail + NEAR AI attestation on the promoted fix

Owner: lead / Person D.

Run: python demo.py   (uses MemoryStore + needs NEAR_AI_API_KEY or LLM_FALLBACK_API_KEY,
or DAYTONA_STUB=1 to keep validation local). Trigger from the dashboard button too.
"""

from __future__ import annotations

import itertools

from backend.store import get_store
from worker.agent import run_worker
from fixer.detect import rolling_avg
from fixer.orchestrate import attempt_self_heal
from eval.trends import EVAL_TRENDS, BRAND_PROFILE


def _batch(store, n=10):
    """Run n worker generations using the current live prompt; cycle through trends."""
    trend_cycle = itertools.cycle(EVAL_TRENDS)
    for _ in range(n):
        trend = next(trend_cycle)
        run = run_worker(trend, BRAND_PROFILE, store.get_live_prompt())
        store.save_run(run)
    return rolling_avg(store.recent_runs(limit=n))


def main():
    store = get_store()  # starts on the "good" prompt

    print("1) Healthy worker (GOOD prompt)")
    print(f"   rolling avg = {_batch(store):.2f}  (expect ~1.0, green)\n")

    print("2) Operator deploys the DEGRADED prompt")
    store.set_live_prompt("degraded")
    print(f"   rolling avg = {_batch(store):.2f}  (expect ~0.4, red)\n")

    print("3-5) Fixer self-heals (first candidate fails, second promotes)")
    result = attempt_self_heal(store, force_first_fail=True)
    for a in result.get("attempts", []):
        verdict = "PROMOTED" if a["sandbox_score"] >= 0.8 and a is result["attempts"][-1] and result["promoted"] else "discarded"
        print(f"   attempt {a['attempt']}: sandbox_score={a['sandbox_score']:.2f} -> {verdict}")
    print(f"   promoted={result.get('promoted')} attestation={result.get('attestation')}\n")

    print("6) Worker after promotion")
    print(f"   rolling avg = {_batch(store):.2f}  (expect ~1.0, recovered)\n")

    print("7) Audit trail")
    print(f"   runs={len(store.all_runs())} detections={len(store.detections())} "
          f"fix_attempts={len(store.fix_attempts())}")


if __name__ == "__main__":
    main()
