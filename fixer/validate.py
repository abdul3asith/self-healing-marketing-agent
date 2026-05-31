"""
VALIDATE  —  the credibility step. Run a CANDIDATE prompt against the FROZEN eval set
inside an isolated Daytona sandbox, score it, tear down, return the average score.

A fix is never promoted on faith. This must run candidate prompts in ISOLATION —
never against the live worker.

Daytona (verified):
  pip install daytona
  from daytona import Daytona
  api key from the Daytona Dashboard -> DAYTONA_API_KEY
  sandboxes spin up in <90ms and run Python.

Owner: Person C (Sandbox & orchestration).

Strategy: ship the worker + scorecard + frozen trends into the sandbox, run the
candidate prompt against all 8 eval trends there, and return the mean scorecard score.
Because the eval set is frozen and the scorecard is deterministic, the same candidate
always yields the same score -> a trustworthy proof-of-fix.

If Daytona access fails (auth/quota), set DAYTONA_STUB=1 to score the candidate in a
LOCAL subprocess instead, so the loop never stalls (handoff: "stub behind its interface
and keep moving"). The stub is clearly flagged in the returned metadata.
"""

from __future__ import annotations

import os

DAYTONA_STUB = os.getenv("DAYTONA_STUB", "0") == "1"


# This is the script that runs INSIDE the sandbox. It imports nothing exotic; the
# orchestrator uploads the worker/eval/llm_client code alongside it.
_SANDBOX_RUNNER = r'''
import json, sys
from eval.trends import EVAL_TRENDS, BRAND_PROFILE
from worker.agent import run_worker

candidate_prompt = json.loads(sys.stdin.read())["candidate_prompt"]
scores = []
for trend in EVAL_TRENDS:
    run = run_worker(trend, BRAND_PROFILE, candidate_prompt)  # raw template == prompt_version
    scores.append(run.score)
print(json.dumps({"avg": sum(scores)/len(scores), "scores": scores}))
'''


def validate_in_daytona(candidate_prompt: str) -> dict:
    """Returns {"avg": float, "scores": [...], "sandboxed": bool}."""
    if DAYTONA_STUB:
        return _validate_local(candidate_prompt)

    # pip install daytona
    from daytona import Daytona, CreateSandboxFromSnapshotParams  # noqa
    import json

    daytona = Daytona()  # reads DAYTONA_API_KEY / DAYTONA_TARGET from env
    sandbox = daytona.create()  # default python runtime, <90ms
    try:
        # TODO(Person C): upload the project (worker/, eval/, llm_client.py, core/)
        # into the sandbox filesystem, plus the candidate's OPENAI_API_KEY env.
        # e.g. sandbox.fs.upload_files(...) then run the runner below.
        sandbox.fs.create_folder("/home/daytona/app")  # placeholder path
        sandbox.fs.upload_file(_SANDBOX_RUNNER.encode(), "/home/daytona/app/_runner.py")
        resp = sandbox.process.exec(
            'cd /home/daytona/app && echo $PAYLOAD | python _runner.py',
            env={"PAYLOAD": json.dumps({"candidate_prompt": candidate_prompt}),
                 "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "")},
        )
        result = json.loads(resp.result)
        result["sandboxed"] = True
        return result
    finally:
        sandbox.delete()  # tear down


def _validate_local(candidate_prompt: str) -> dict:
    """STUB fallback: score the candidate in-process. Same determinism, no isolation.
    Flagged with sandboxed=False so the dashboard/audit trail never misrepresents it."""
    from eval.trends import EVAL_TRENDS, BRAND_PROFILE
    from worker.agent import run_worker
    scores = [run_worker(t, BRAND_PROFILE, candidate_prompt).score for t in EVAL_TRENDS]
    return {"avg": sum(scores) / len(scores), "scores": scores, "sandboxed": False}
