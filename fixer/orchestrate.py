"""
ORCHESTRATE  —  the loop. detect -> diagnose -> generate -> validate -> promote / retry.

This is the product. It's the self-healing cycle, with the visible "fail then recover"
that proves the loop is real (section 9, step 4).

Kalibr (verified: kalibr.systems, kalibr-ai/kalibr-sdk-python) is "self-healing
infrastructure for AI agents" — a strong conceptual fit for this orchestration +
retry/recovery layer. Open decision #3: if their hackathon SDK access works out of the
box, wire it here; otherwise we run this loop ourselves and present Kalibr as the
orchestration layer we plug into. Either way the loop logic below is the contract.

Owner: Person C (Sandbox & orchestration).
"""

from __future__ import annotations

import uuid

from fixer.detect import detect_drop, THRESHOLD, rolling_avg
from fixer.diagnose import diagnose
from fixer.generate import generate
from fixer.validate import validate_in_daytona
from llm_client import get_attestation

MAX_RETRIES = 3


def attempt_self_heal(store, *, force_first_fail: bool = True) -> dict:
    """Run one full heal cycle against current logs. Returns a summary dict.

    `force_first_fail`: engineer the demo's money moment — the FIRST candidate uses a
    deliberately weak hypothesis so it fails the sandbox eval and is discarded; the
    second uses the full hypothesis and passes. Set False for pure autonomous behavior.
    """
    recent = store.recent_runs(limit=10)
    detection_data = detect_drop(recent, threshold=THRESHOLD)
    if detection_data is None:
        return {"detected": False, "current_avg": rolling_avg(recent)}

    detection = store.save_detection(detection_data)
    failing = store.runs_by_ids(detection_data["failing_run_ids"])
    current_prompt = store.get_live_prompt()
    current_score = rolling_avg(recent)

    timeline = []
    for attempt in range(MAX_RETRIES):
        weak = force_first_fail and attempt == 0
        hypothesis = diagnose(failing, current_prompt, weak=weak)
        candidate = generate(hypothesis, current_prompt)
        result = validate_in_daytona(candidate)
        sandbox_score = result["avg"]

        fix = store.save_fix_attempt({
            "id": str(uuid.uuid4()),
            "detection_id": detection["id"],
            "hypothesis": hypothesis,
            "candidate_prompt": candidate,
            "sandbox_score": sandbox_score,
            "promoted": False,
            "attestation": None,
        })
        timeline.append({"attempt": attempt, "sandbox_score": sandbox_score,
                         "sandboxed": result.get("sandboxed"), "weak": weak})

        if sandbox_score > current_score and sandbox_score >= THRESHOLD:
            store.promote(candidate)                      # update live prompt_version
            attestation = get_attestation(fix["id"])      # NEAR AI attestation (stretch)
            store.mark_promoted(fix["id"], attestation=attestation)
            return {"detected": True, "promoted": True, "attempts": timeline,
                    "promoted_score": sandbox_score, "attestation": attestation}
        # else: discard, try a different hypothesis (the visible fail-then-recover)

    return {"detected": True, "promoted": False, "attempts": timeline}
