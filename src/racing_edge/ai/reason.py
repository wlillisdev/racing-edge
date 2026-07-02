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


def _post_with_retry(headers: dict, body: dict) -> tuple[dict | None, int]:
    """POST to the Messages API with backoff on transient failures (429 / 5xx /
    network) — the same courtesy the Racing API client already gets. Returns
    (json, 200) on success, (None, last_status) on give-up (0 = network)."""
    import time
    status = 0
    for attempt in range(4):
        try:
            resp = requests.post(_URL, headers=headers, json=body, timeout=_TIMEOUT)
        except requests.RequestException:
            status = 0
            time.sleep(2 ** attempt)
            continue
        status = resp.status_code
        if status == 200:
            try:
                return resp.json(), 200
            except ValueError:
                return None, 200
        if status in (429, 500, 502, 503, 529):        # transient — back off, retry
            time.sleep(min(2.0 * (2 ** attempt), 20.0))
            continue
        return None, status                             # hard error — don't hammer
    return None, status


def get_investigator(task: str, tools: list[dict],
                     executor: Callable[[str, dict], str], max_steps: int = 6,
                     max_tokens: int = 2000):
    """An INVESTIGATING reasoner — the model can call the given tools mid-thought
    (pull a thread, ask for more evidence) instead of answering a questionnaire off a
    static readout. Returns complete(system, prompt) -> (final_text, trail) where trail
    lists every lookup made (auditable — no invisible evidence). Tool calls are capped
    at max_steps; past the cap, further calls get a budget-spent refusal AS the tool
    result (tools stay in the request — dropping them mid-conversation is an API error).
    None if no ANTHROPIC_API_KEY."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = resolve_model(task)
    headers = {"x-api-key": key, "anthropic-version": _VERSION,
               "content-type": "application/json"}

    def complete(system: str, prompt: str) -> tuple[str, list[str]]:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        trail: list[str] = []
        steps = 0
        for _round in range(max_steps + 4):            # hard cap on conversation rounds
            body = {"model": model, "max_tokens": max_tokens, "system": system,
                    "messages": messages, "tools": tools}
            data, status = _post_with_retry(headers, body)
            if data is None:
                trail.append(f"API error {status or 'network'} — gave up after retries")
                return "", trail
            content = data.get("content") or []
            if data.get("stop_reason") == "tool_use":
                messages.append({"role": "assistant", "content": content})
                results = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name, args = block.get("name", ""), block.get("input") or {}
                        if steps < max_steps:
                            steps += 1
                            out = executor(name, args)
                            trail.append(
                                f"{name}({', '.join(str(v) for v in args.values())})")
                        else:
                            out = ("Lookup budget spent — answer NOW with the JSON, "
                                   "using only evidence already gathered.")
                        results.append({"type": "tool_result",
                                        "tool_use_id": block.get("id", ""),
                                        "content": out[:6000]})
                messages.append({"role": "user", "content": results})
                continue
            return ("".join(b.get("text", "") for b in content
                            if isinstance(b, dict)), trail)
        trail.append("round cap hit — no final answer")
        return "", trail

    return complete


def get_reasoner(task: str = "study",
                 max_tokens: int = 1500) -> Callable[[str, str], str] | None:
    """Return complete(system, prompt) -> text for this TASK's model, or None
    if no ANTHROPIC_API_KEY is configured."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = resolve_model(task)

    headers = {
        "x-api-key": key,
        "anthropic-version": _VERSION,
        "content-type": "application/json",
    }

    def complete(system: str, prompt: str) -> str:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        data, _status = _post_with_retry(headers, body)
        if data is None:
            return ""
        parts = data.get("content") or []
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    return complete
