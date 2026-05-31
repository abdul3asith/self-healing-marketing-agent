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

import os

# pip install openai
from openai import OpenAI

NEAR_AI_BASE_URL = os.getenv("NEAR_AI_BASE_URL", "https://cloud-api.near.ai/v1")
NEAR_AI_API_KEY = os.getenv("NEAR_AI_API_KEY")
NEAR_AI_MODEL = os.getenv("NEAR_AI_MODEL", "deepseek-ai/DeepSeek-V3.1")

# Fallback so we're never blocked by one provider (open decision: keep a backup key).
FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "https://api.openai.com/v1")
FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY")
FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "gpt-4o-mini")


def _client(provider: str = "near") -> tuple[OpenAI, str]:
    if provider == "near" and NEAR_AI_API_KEY:
        return OpenAI(base_url=NEAR_AI_BASE_URL, api_key=NEAR_AI_API_KEY), NEAR_AI_MODEL
    if FALLBACK_API_KEY:
        return OpenAI(base_url=FALLBACK_BASE_URL, api_key=FALLBACK_API_KEY), FALLBACK_MODEL
    raise RuntimeError("No LLM credentials set. Add NEAR_AI_API_KEY or LLM_FALLBACK_API_KEY to .env")


def complete(prompt: str, *, system: str = "", temperature: float = 0.7,
             provider: str = "near") -> str:
    """Single text completion. Returns the model's text (empty string on failure)."""
    client, model = _client(provider)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=600,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        # If NEAR AI fails and a fallback exists, try it once.
        if provider == "near" and FALLBACK_API_KEY:
            return complete(prompt, system=system, temperature=temperature, provider="fallback")
        raise


def get_attestation(run_id: str) -> str | None:
    """STRETCH (open decision #2): NEAR AI runs models in TEEs and can return a
    verifiable attestation. For MVP this is stubbed; wire the real receipt only if
    items 1–6 finish early. Returns a placeholder ref or None."""
    if os.getenv("NEAR_AI_ATTESTATION", "stub") == "stub":
        return f"near-att-stub::{run_id}"
    # TODO(Person C): fetch real attestation from NEAR AI direct-completions TEE.
    return None
