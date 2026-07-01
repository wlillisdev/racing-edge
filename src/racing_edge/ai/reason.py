"""A robust model caller for the SELF-TEACHING loop — direct HTTP, NOT the SDK.

The narrative completer (ai/llm.py) uses the `anthropic` SDK, which clashes with the
box's httpx (the removed `proxies` arg) and crashes — which is why the box runs with
ANTHROPIC_API_KEY blanked and the model switched OFF. A self-teaching loop needs the
model ON, so this talks to the Messages API directly over `requests` (already a
dependency, already used for the Racing API) and never imports the SDK.

Contract: degrades to None without a key; never raises on a network/API error — the
caller reports "no reasoning available" rather than crashing the study. It reasons ONLY
over the facts it is handed (see study.selfcritique); it is never a source of facts.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import requests

_URL = "https://api.anthropic.com/v1/messages"
_VERSION = "2023-06-01"
_TIMEOUT = 60


def get_reasoner(max_tokens: int = 1500) -> Callable[[str, str], str] | None:
    """Return complete(system, prompt) -> text, or None if no key is configured.

    Model comes from ANTHROPIC_MODEL (so the box can dial the depth up without a code
    change); falls back to the same Haiku the rest of the app defaults to."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

    def complete(system: str, prompt: str) -> str:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": key,
            "anthropic-version": _VERSION,
            "content-type": "application/json",
        }
        try:
            resp = requests.post(_URL, headers=headers, json=body, timeout=_TIMEOUT)
            if resp.status_code != 200:
                return ""
            data = resp.json()
            parts = data.get("content") or []
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        except (requests.RequestException, ValueError):
            return ""

    return complete
