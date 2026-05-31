"""
CLAUDE BRIDGE  —  wire the API tools into a Claude window/agent.

This is the glue between a Claude chat and api.py. It gives you:
  1. ANTHROPIC_TOOLS  — the tool schemas to hand Claude (Anthropic Messages `tools=`).
  2. call_tool(name, input) — a dispatcher that turns a Claude tool_use into an HTTP call
     against the running FastAPI server (api.py).
  3. A runnable example loop (python claude_tools.py "your prompt") that lets Claude
     actually scrape Nat Geo + generate an on-brand post by calling the tools.

Live-site wiring:
  * Start the API:        uvicorn api:app --port 8000     (deploy it, or `ngrok http 8000`)
  * Point this at it:     export AGENT_API_BASE=https://<your-public-url>
  * Give Claude a key:    export ANTHROPIC_API_KEY=sk-ant-...
A browser-based Claude chat widget can also call api.py directly (CORS is open) — this
module is the server-side path when you control the agent loop.
"""

from __future__ import annotations

import json
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx

AGENT_API_BASE = os.getenv("AGENT_API_BASE", "http://127.0.0.1:8000")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


# ---------------------------------------------------------------------------
# 1) Tool schemas Claude reads. These mirror api.py — paste straight into the
#    Anthropic Messages API `tools=[...]` argument.
# ---------------------------------------------------------------------------
ANTHROPIC_TOOLS = [
    {
        "name": "scrape_trends",
        "description": "Scrape the top trending posts from a Facebook page (ranked by engagement). "
                       "Use this first to discover what's trending, then feed a result into generate_post.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_url": {"type": "string", "description": "Facebook page URL, e.g. https://www.facebook.com/natgeo"},
                "limit": {"type": "integer", "description": "Max posts to return (1-50).", "default": 5},
            },
            "required": ["page_url"],
        },
    },
    {
        "name": "generate_post",
        "description": "Write ONE on-brand Instagram post for a given trend. The model call self-heals "
                       "(reroutes across NEAR models via Kalibr) and is scored against deterministic brand rules.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trend_label": {"type": "string", "description": "The trend/topic to write about."},
                "trend_keyword": {"type": "string", "description": "Keyword the post must include (optional)."},
                "prompt_version": {"type": "string", "enum": ["good", "degraded"], "default": "good"},
            },
            "required": ["trend_label"],
        },
    },
    {
        "name": "run_self_heal",
        "description": "Run the prompt-level self-healing loop: seed a quality drop, detect it, diagnose, "
                       "generate a candidate fix, validate it, and promote on success. Returns before/after scores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "n_runs": {"type": "integer", "default": 10},
                "force_first_fail": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "kalibr_intelligence",
        "description": "Get Kalibr routing intelligence per goal (success rate, attempts, status, trend) — "
                       "the model-level self-healing brain.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

# Map each tool to (HTTP method, path).
_ROUTES = {
    "scrape_trends": ("POST", "/tools/scrape_trends"),
    "generate_post": ("POST", "/tools/generate_post"),
    "run_self_heal": ("POST", "/tools/run_self_heal"),
    "kalibr_intelligence": ("GET", "/tools/kalibr_intelligence"),
}


# ---------------------------------------------------------------------------
# 2) Dispatcher: turn a Claude tool_use block into an HTTP call against api.py.
# ---------------------------------------------------------------------------
def call_tool(name: str, tool_input: dict) -> dict:
    """Execute one Claude tool call against the running API. Returns the JSON response."""
    if name not in _ROUTES:
        return {"error": f"unknown tool '{name}'"}
    method, path = _ROUTES[name]
    url = f"{AGENT_API_BASE}{path}"
    with httpx.Client(timeout=180) as client:
        r = client.get(url) if method == "GET" else client.post(url, json=tool_input or {})
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# 3) Example agent loop: Claude plans, calls tools, and answers.
# ---------------------------------------------------------------------------
def chat_with_tools(user_prompt: str) -> None:
    """Minimal Claude tool-use loop. Requires ANTHROPIC_API_KEY + `pip install anthropic`."""
    try:
        from anthropic import Anthropic
    except ImportError:
        print("pip install anthropic to run the live loop. Tool schemas are still importable.")
        return
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY to run the live loop.")
        return

    client = Anthropic()
    messages = [{"role": "user", "content": user_prompt}]

    while True:
        resp = client.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=1024, tools=ANTHROPIC_TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            print("\nClaude:", "".join(b.text for b in resp.content if b.type == "text"))
            return

        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                print(f"  -> Claude calls {block.name}({json.dumps(block.input)})")
                result = call_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
        messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or (
        "Scrape the top trend from National Geographic's Facebook page, then generate an "
        "on-brand Instagram post about it and tell me the brand score."
    )
    print(f"API base: {AGENT_API_BASE}\nPrompt: {prompt}\n")
    chat_with_tools(prompt)
