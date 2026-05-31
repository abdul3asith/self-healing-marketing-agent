"""
THE ONE MODEL CLIENT  —  every LLM call in the project goes through here.

Single OpenAI-compatible provider. This is the seam the handoff requires: "Keep all
model calls behind ONE swappable client." To point at a different OpenAI-compatible
endpoint (Together, Groq, OpenRouter, a local server, ...), just override
OPENAI_BASE_URL / OPENAI_MODEL in .env — no logic elsewhere changes.

  base_url = https://api.openai.com/v1   (override with OPENAI_BASE_URL)
  api_key  = OPENAI_API_KEY
  uses the standard `openai` python SDK.

Owner: lead / Person C.
"""

from __future__ import annotations

import os

# pip install openai
from openai import OpenAI

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _client() -> tuple[OpenAI, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("No LLM credentials set. Add OPENAI_API_KEY to .env")
    return OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY), OPENAI_MODEL


def complete(prompt: str, *, system: str = "", temperature: float = 0.7) -> str:
    """Single text completion. Returns the model's text (empty string on failure)."""
    client, model = _client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=600,
    )
    return resp.choices[0].message.content or ""
