"""
CAPTURE  —  the human-workflow capture kit (design-time front half).

The rest of this repo is the RUN-TIME back half: it watches an *agent* and self-heals
it (no human in the loop). This package is the inverse: it watches a *human* do a real
job through three windows, stitches what it sees into one honest timeline (grouped by a
job-level trace_id), and reads that timeline backwards into an agent blueprint — tools
the agent must have, rules distilled from rejected options, guardrails where output
slips through silently, and explicit "keep a human here" markers on low-confidence
judgment calls.

Everything here is deterministic and zero-dependency (stdlib + eval.gate1 only), so
`python -m capture.demo` runs fully offline, matching the repo's mock-first ethos.
"""
