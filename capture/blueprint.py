"""
BLUEPRINT  —  the translation step. Read the timeline backwards into agent build specs.

Each piece of the human's real workflow becomes a building instruction for the future
agent, deterministically (no LLM-as-judge — same discipline as eval/scorecard.py):

  tool step          -> CAPABILITY  : "the agent must be able to call APIFY with inputs like these"
  rejection + reason -> RULE        : "don't pick trends that cheapen a premium brand"
  silent failure     -> GUARDRAIL   : "put a human checkpoint right here — it breaks quietly"
  low-confidence call-> HUMAN-IN-LOOP: "keep a human here — this is judgment, not rote"

The one-sentence version: watch a human through three windows, stitch it into one honest
timeline, then read that timeline backwards to figure out what an agent needs — and,
crucially, where it shouldn't be trusted alone.
"""

from __future__ import annotations

from capture.contracts import (
    KIND_DECISION,
    KIND_SILENT_FAILURE,
    KIND_TOOL_USE,
    AgentBlueprint,
    Capability,
    Guardrail,
    HumanCheckpoint,
    Rule,
)
from capture.timeline import assemble, render

# Below this confidence, a decision is treated as judgment (keep a human), not rote.
HITL_CONFIDENCE_THRESHOLD = 0.7


def _rule_from_rejection(question: str, rejection: dict) -> str:
    option = rejection.get("option", "?")
    return f"When deciding {question!r}, reject options like {option!r}."


def translate(store, trace, *, hitl_threshold: float = HITL_CONFIDENCE_THRESHOLD) -> AgentBlueprint:
    """Turn one job's timeline into an AgentBlueprint and persist it."""
    timeline = assemble(store, trace.trace_id)

    capabilities: list[Capability] = []
    rules: list[Rule] = []
    guardrails: list[Guardrail] = []
    human_in_the_loop: list[HumanCheckpoint] = []

    for o in timeline:
        if o.kind == KIND_TOOL_USE:
            capabilities.append(Capability(
                tool=o.data.get("tool", "?"),
                example_inputs=o.data.get("inputs", {}),
                derived_from=o.id,
            ))

        elif o.kind == KIND_DECISION:
            d = o.data
            question = d.get("question", "")
            for rej in d.get("rejected", []):
                rules.append(Rule(
                    rule=_rule_from_rejection(question, rej),
                    rationale=rej.get("reason", ""),
                    derived_from=o.id,
                    avoid=str(rej.get("option", "")),
                ))
            confidence = float(d.get("confidence", 1.0))
            if confidence < hitl_threshold:
                human_in_the_loop.append(HumanCheckpoint(
                    step=question,
                    reason="low-confidence judgment call — judgment, not rote",
                    confidence=confidence,
                    derived_from=o.id,
                ))

        elif o.kind == KIND_SILENT_FAILURE:
            guardrails.append(Guardrail(
                at_step=o.data.get("step", ""),
                check=o.data.get("check", ""),
                action="insert a human verification checkpoint here — this is where bad output slips through silently",
                derived_from=o.id,
            ))

    bp = AgentBlueprint(
        trace_id=trace.trace_id,
        title=trace.title,
        narrative=render(timeline),
        capabilities=capabilities,
        rules=rules,
        guardrails=guardrails,
        human_in_the_loop=human_in_the_loop,
    )
    return store.save_blueprint(bp)
