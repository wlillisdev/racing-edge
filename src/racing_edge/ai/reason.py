"""A robust model caller for the SELF-TEACHING loop — direct HTTP, NOT the SDK.

The narrative completer (ai/llm.py) uses the `anthropic` SDK, which clashes with the
box's httpx (the removed `proxies` arg) and crashes — which is why the box runs with
ANTHROPIC_API_KEY blanked and the model switched OFF. A self-teaching loop needs the
model ON, so this talks to the Messages API directly over `requests` (already a
dependency, already used for the Racing API) and never imports the SDK.

THE MODEL IS PICKED PER TASK — the master's ruling after Haiku wrecked the reads
(the WELL-IN/+3lb muddle, the "only recent winner" that wasn't). Each job gets the
brain it needs, in code, so nothing silently degrades to the small model:

  study      — per-race self-interrogation. Runs ~20x/night: strong but affordable.
  sceptic    — the adversarial kill-pass. MUST out-think the proposer: the flagship.
  synthesis  — the weekly join-the-dots over the whole ledger. Once a week: flagship.

Override order (loudest wins): ANTHROPIC_MODEL_<TASK> > ANTHROPIC_MODEL > the table.

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
_TIMEOUT = 120

# The best model for each task — not one dial for everything.
_TASK_MODELS = {
    "study": "claude-sonnet-5",       # per-race read: strong reasoning, runs many times
    "sceptic": "claude-fable-5",      # the kill-pass must be sharper than the proposer
    "synthesis": "claude-fable-5",    # the weekly cross-day read: deepest, runs once
}
_FALLBACK = "claude-sonnet-5"


def resolve_model(task: str) -> str:
    """Which model this task thinks with. Per-task env > global env > the table."""
    per_task = os.environ.get(f"ANTHROPIC_MODEL_{task.upper()}")
    if per_task:
        return per_task
    global_override = os.environ.get("ANTHROPIC_MODEL")
    if global_override:
        return global_override
    return _TASK_MODELS.get(task, _FALLBACK)


def get_reasoner(task: str = "study",
                 max_tokens: int = 1500) -> Callable[[str, str], str] | None:
    """Return complete(system, prompt) -> text for this TASK's model, or None
    if no ANTHROPIC_API_KEY is configured."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = resolve_model(task)

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
