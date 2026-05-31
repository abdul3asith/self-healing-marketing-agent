"""
DEMO DRIVER  —  the section-9 sequence, end to end, deterministically.

  1. worker on GOOD prompt -> score steady ~1.0 (green)
  2. operator "deploys" DEGRADED prompt -> score craters ~0.4 (red)
  3. fixer auto-detects the drop (Detection)
  4. FIRST candidate fails the sandbox eval -> discarded   <-- the money moment
  5. SECOND candidate passes the sandbox -> promoted live
  6. worker score recovers to ~1.0 (green), no human touched it
  7. show the audit trail on the promoted fix

Owner: lead / Person D.

Run: python demo.py            (summary numbers only)
     VERBOSE=1 python demo.py  (show the actual posts, failed checks, diagnosis,
                                candidate prompts -- i.e. WHAT happened at each step)

Uses MemoryStore + needs OPENAI_API_KEY; set DAYTONA_STUB=1 to keep validation local.
"""

from __future__ import annotations

import itertools
import os

try:
    from dotenv import load_dotenv
    load_dotenv()                  # load .env so OPENAI_API_KEY etc. are available
except ImportError:
    pass                           # dotenv optional; env vars can be exported instead

from backend.store import get_store
from worker.agent import run_worker
from fixer.detect import rolling_avg
from fixer.orchestrate import attempt_self_heal
from eval.trends import EVAL_TRENDS, BRAND_PROFILE

VERBOSE = os.getenv("VERBOSE", "0") == "1"


def _show_run(run, trend):
    """Print one worker post: the actual content + which scorecard checks it failed."""
    o = run.output
    failed = [name for name, ok in run.checks.items() if not ok]
    print(f"   --- trend '{trend.trend_label}'  (score {run.score:.2f}) ---")
    if o is None:
        print("       [unparseable output -> 0.0]")
    else:
        print(f"       hook    ({len(o.hook)} chars): {o.hook}")
        print(f"       caption ({len(o.caption)} chars): {o.caption}")
        print(f"       hashtags: {o.hashtags}")
    print(f"       FAILED checks: {failed or 'none'}\n")


def _batch(store, n=10, show=0):
    """Run n worker generations using the current live prompt; cycle through trends.
    `show`: in verbose mode, print the first `show` posts in full."""
    trend_cycle = itertools.cycle(EVAL_TRENDS)
    shown = 0
    for _ in range(n):
        trend = next(trend_cycle)
        run = run_worker(trend, BRAND_PROFILE, store.get_live_prompt())
        store.save_run(run)
        if VERBOSE and shown < show:
            _show_run(run, trend)
            shown += 1
    return rolling_avg(store.recent_runs(limit=n))


def main():
    store = get_store()  # starts on the "good" prompt

    print("1) Healthy worker (GOOD prompt)")
    avg = _batch(store, show=1)
    print(f"   rolling avg = {avg:.2f}  (expect ~1.0, green)\n")

    print("2) Operator deploys the DEGRADED prompt")
    store.set_live_prompt("degraded")
    avg = _batch(store, show=2)
    print(f"   rolling avg = {avg:.2f}  (expect ~0.4, red)\n")

    print("3-5) Fixer self-heals (first candidate fails, second promotes)")
    result = attempt_self_heal(store, force_first_fail=True)

    if VERBOSE and store.detections():
        d = store.detections()[-1]
        print(f"   DETECTED: window avg {d['window_avg_score']:.2f} < threshold "
              f"{d['threshold']} ({len(d['failing_run_ids'])} failing runs)\n")

    attempts = result.get("attempts", [])
    fixes = store.fix_attempts()
    for a, fix in zip(attempts, fixes):
        promoted = a is attempts[-1] and result.get("promoted")
        verdict = "PROMOTED" if promoted else "discarded"
        print(f"   attempt {a['attempt']}: sandbox_score={a['sandbox_score']:.2f} -> {verdict}")
        if VERBOSE:
            print(f"       hypothesis: {fix['hypothesis']}")
            print(f"       candidate prompt:\n{_indent(fix['candidate_prompt'])}\n")
    print(f"   promoted={result.get('promoted')}\n")

    print("6) Worker after promotion")
    avg = _batch(store, show=1)
    print(f"   rolling avg = {avg:.2f}  (expect ~1.0, recovered)\n")

    print("7) Audit trail")
    print(f"   runs={len(store.all_runs())} detections={len(store.detections())} "
          f"fix_attempts={len(store.fix_attempts())}")


def _indent(text: str, pad: str = "         | ") -> str:
    return "\n".join(pad + line for line in text.splitlines())


if __name__ == "__main__":
    main()
