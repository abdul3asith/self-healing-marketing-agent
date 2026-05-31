"""
TRACE  —  the job-level trace_id. The one label that makes the whole kit work.

The repo already has a trace_id, but it's PER LLM STEP: Kalibr's decide()/get_alternative()
mint `mock-trace::<uuid>` for a single model call (see integrations/kalibr.py and
fixer/runstep.py). That's the wrong granularity for capturing a human job, which spans
many tool calls, doc edits, and decisions over hours.

So we mint a JOB-level trace_id here (`job::<uuid>`). Everything the three windows
record during that job is stamped with it. Any per-step Kalibr trace_ids that occur
inside the job are kept as children inside a tool observation's `data` — they reference
up to the job trace, never replace it.
"""

from __future__ import annotations

import uuid

from capture.contracts import JobTrace


def new_job_trace(title: str, *, trace_id: str | None = None) -> JobTrace:
    """Open a new job. `title` is the human-readable job name (e.g. the client + cycle);
    `trace_id` may be supplied to resume/attach to an existing job, else one is minted."""
    return JobTrace(trace_id=trace_id or f"job::{uuid.uuid4()}", title=title)


def new_observation_id() -> str:
    return f"obs::{uuid.uuid4()}"
