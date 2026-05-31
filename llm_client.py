"""
THE ONE MODEL CLIENT  —  every LLM call in the project goes through here.

Point it at NEAR AI Cloud (OpenAI-compatible) or a fallback provider without
touching any logic elsewhere. This is the seam the handoff requires: "Keep all
model calls behind ONE swappable client."

NEAR AI Cloud (verified):
  base_url = https://cloud-api.near.ai/v1   (gateway; routes to any model)
  api_key  = generated in the NEAR AI Cloud Dashboard
  uses the standard `openai` python SDK with base_url overridden.

Owner: lead / Person C (NEAR AI integration).
"""

from __future__ import annotations

import json
import os
import re

NEAR_AI_BASE_URL = os.getenv("NEAR_AI_BASE_URL", "https://cloud-api.near.ai/v1")
NEAR_AI_API_KEY = os.getenv("NEAR_AI_API_KEY")
NEAR_AI_MODEL = os.getenv("NEAR_AI_MODEL", "deepseek-ai/DeepSeek-V3.1")

# Multi-model NEAR: a Kalibr path model_id maps to a NEAR model slug. A "heal" is
# simply switching between these private NEAR models — exactly the reliability story
# given the cloud's flakiness. GLM-5 slug is unverified; set it once confirmed at
# completions.near.ai/endpoints (empty -> treated as a down model so the loop heals).
NEAR_AI_MODEL_QWEN = os.getenv("NEAR_AI_MODEL_QWEN", "Qwen/Qwen3.5-122B-A10B")
NEAR_AI_MODEL_DEEPSEEK = os.getenv("NEAR_AI_MODEL_DEEPSEEK", "deepseek-ai/DeepSeek-V3.1")
NEAR_AI_MODEL_GLM = os.getenv("NEAR_AI_MODEL_GLM", "")

PATH_TO_NEAR_MODEL = {
    "near-qwen3.5": NEAR_AI_MODEL_QWEN,
    "near-deepseek-v3.1": NEAR_AI_MODEL_DEEPSEEK,
    "near-glm5": NEAR_AI_MODEL_GLM,
}

# Fallback so we're never blocked by one provider (open decision: keep a backup key).
FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "https://api.openai.com/v1")
FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY")
FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "gpt-4o-mini")

# Demo/testing knob: comma-separated Kalibr path ids to force-fail (e.g. "near-qwen3.5"),
# so you can SHOW the model-level heal even offline. See NEAR_AI_CHAOS in .env.example.
_DOWN_MODELS = {m.strip() for m in os.getenv("NEAR_AI_CHAOS", "").split(",") if m.strip()}


class NearAIError(RuntimeError):
    """Raised when a SPECIFIC NEAR model call fails, so the orchestrator can HEAL
    (reroute to another model via Kalibr) instead of silently masking the failure."""


def is_mock() -> bool:
    """True when no model credentials are set -> deterministic offline mock so the
    whole demo runs with zero keys / zero network (the hackathon-network hedge)."""
    return not (NEAR_AI_API_KEY or FALLBACK_API_KEY)


def map_path_to_near_model(model_id: str | None) -> str:
    """Map a Kalibr path model_id (e.g. 'near-qwen3.5') to a NEAR slug. An unknown id
    is treated as a literal NEAR slug; None falls back to the default model."""
    if not model_id:
        return NEAR_AI_MODEL
    return PATH_TO_NEAR_MODEL.get(model_id, model_id)


def _openai_client(base_url: str, api_key: str):
    from openai import OpenAI  # lazy import: mock mode (no keys) needs zero deps
    return OpenAI(base_url=base_url, api_key=api_key)


def _fallback_chat(messages, temperature, max_tokens) -> str:
    client = _openai_client(FALLBACK_BASE_URL, FALLBACK_API_KEY)
    resp = client.chat.completions.create(
        model=FALLBACK_MODEL, messages=messages, temperature=temperature, max_tokens=max_tokens)
    return resp.choices[0].message.content or ""


def _execute(messages: list[dict], *, near_model: str, temperature: float,
             max_tokens: int, allow_fallback: bool) -> str:
    """Low-level executor for a SPECIFIC NEAR model. Raises NearAIError on failure
    (optionally trying the cross-provider fallback first when allow_fallback=True)."""
    if is_mock():
        return _mock_chat(messages, near_model)

    if NEAR_AI_API_KEY:
        if not near_model:
            # e.g. GLM slug unset: treat as a down model so the loop heals elsewhere.
            if allow_fallback and FALLBACK_API_KEY:
                return _fallback_chat(messages, temperature, max_tokens)
            raise NearAIError("NEAR model slug is empty (unconfigured).")
        try:
            client = _openai_client(NEAR_AI_BASE_URL, NEAR_AI_API_KEY)
            resp = client.chat.completions.create(
                model=near_model, messages=messages, temperature=temperature, max_tokens=max_tokens)
            return resp.choices[0].message.content or ""
        except Exception as e:
            if allow_fallback and FALLBACK_API_KEY:
                return _fallback_chat(messages, temperature, max_tokens)
            raise NearAIError(f"NEAR call failed for model '{near_model}': {e}") from e

    # No NEAR key but a fallback exists.
    return _fallback_chat(messages, temperature, max_tokens)


def chat(messages: list[dict], *, model_id: str | None = None, near_model: str | None = None,
         temperature: float = 0.7, max_tokens: int = 600, allow_fallback: bool = False) -> str:
    """Execute a chat completion on a SPECIFIC NEAR model.

    Used by the self-healing orchestrator: Kalibr picks `model_id` (a registered path
    like 'near-qwen3.5'); we map it to a NEAR slug and run it here. allow_fallback is
    False by default so a model failure surfaces as NearAIError and Kalibr can HEAL by
    rerouting to another NEAR model rather than masking it with a different provider.
    """
    if model_id and model_id in _DOWN_MODELS:
        raise NearAIError(f"chaos: '{model_id}' marked down via NEAR_AI_CHAOS")
    resolved = near_model or map_path_to_near_model(model_id)
    return _execute(messages, near_model=resolved, temperature=temperature,
                    max_tokens=max_tokens, allow_fallback=allow_fallback)


def complete(prompt: str, *, system: str = "", temperature: float = 0.7,
             provider: str = "near") -> str:
    """Single text completion (legacy convenience used by the fixer/worker). Routes
    NEAR -> fallback on error. New code should prefer chat()/runStep so that failures
    can HEAL via Kalibr instead of being masked by a cross-provider fallback."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    if provider == "fallback":
        if is_mock():
            return _mock_chat(messages, FALLBACK_MODEL)
        return _fallback_chat(messages, temperature, 600)
    return _execute(messages, near_model=NEAR_AI_MODEL, temperature=temperature,
                    max_tokens=600, allow_fallback=True)


# ---------------------------------------------------------------------------
# OFFLINE MOCK  —  deterministic, demo-coherent output when no keys are set.
# It is prompt-aware enough that a GOOD prompt (which enumerates the rules)
# yields a compliant draft (~1.0) while a vague DEGRADED prompt yields a sloppy
# one (~0.4) — so detection + heal + recovery all run offline. The fail-then-
# recover *drama* still needs a real model (the mock recovers on attempt 0).
# ---------------------------------------------------------------------------
_MOCK_FIX_TEMPLATE = '''You are a social content writer for a {niche} brand.
Write ONE Instagram post about the trend "{trend_label}". Follow every rule:
1. Hook at most 60 characters.
2. Caption at most 150 characters.
3. Include this call-to-action VERBATIM in the hook or caption: "{required_cta}"
4. Include the trend keyword "{trend_keyword}" in the hook or caption.
5. Provide 3 to 5 hashtags starting with '#'. One MUST be "{required_hashtag}".
6. Do NOT use any of these banned words: {banned_words}.
7. Return ONLY valid JSON: {{"hook": "...", "caption": "...", "hashtags": ["#a", "#b", "#c"]}}
Voice: {voice_note}'''


def _extract(pattern: str, text: str, default: str) -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1) if m else default


def _mock_content(text: str) -> str:
    """Return a JSON content draft. If the prompt enumerates the rules (contains
    'verbatim'), build a compliant draft by reading the embedded rule values;
    otherwise return a rule-breaking 'right shape, wrong content' draft."""
    if "verbatim" in text.lower():
        keyword = _extract(r'keyword "([^"]+)"', text, "trend")
        cta = _extract(r'VERBATIM[^"]*"([^"]+)"', text, "Follow for more")
        req_tag = _extract(r'MUST be "([^"]+)"', text, "#glowroutine")
        hook = f"{keyword}: my daily glow"[:60]
        caption = f"{cta}. Simple steps for happy skin."[:150]
        tags = list(dict.fromkeys([req_tag, "#skincare", "#glowup"]))[:5]
        return json.dumps({"hook": hook, "caption": caption, "hashtags": tags})
    # Vague prompt -> valid JSON shape but breaks the content rules.
    return json.dumps({
        "hook": "This amazing trend will totally change your whole routine forever and ever today",
        "caption": "We love this trend so much! You have to try it today, it is the best thing ever.",
        "hashtags": ["#fun", "#love"],
    })


def _mock_chat(messages: list[dict], near_model: str) -> str:
    text = "\n".join(m.get("content", "") for m in messages)
    low = text.lower()
    if "return only the new prompt template" in low:        # fixer.generate
        return _MOCK_FIX_TEMPLATE
    if "diagnose the root cause" in low:                    # fixer.diagnose
        return ("The current prompt is too vague: it omits the hard constraints "
                "(60-char hook, 150-char caption, the verbatim CTA, the trend keyword, "
                "the 3-5 hashtag rule with the required tag, and the banned-word list), "
                "so the model ignores them.")
    if "hashtags" in low and "hook" in low:                 # worker content generation
        return _mock_content(text)
    return f"[mock:{near_model}] deterministic offline response."


def get_attestation(run_id: str) -> str | None:
    """STRETCH (open decision #2): NEAR AI runs models in TEEs and can return a
    verifiable attestation. For MVP this is stubbed; wire the real receipt only if
    items 1–6 finish early. Returns a placeholder ref or None."""
    if os.getenv("NEAR_AI_ATTESTATION", "stub") == "stub":
        return f"near-att-stub::{run_id}"
    # TODO(Person C): fetch real attestation from NEAR AI direct-completions TEE.
    return None
