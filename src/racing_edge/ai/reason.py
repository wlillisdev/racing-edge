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


def _log_usage(task: str, model: str, data: dict) -> None:
    """Append the call's REAL token counts (from the API response) to a local CSV —
    the machine counts its own bill instead of anyone estimating it. Never raises."""
    try:
        import csv
        import datetime
        from pathlib import Path
        _data_dir = Path(__file__).resolve().parents[3] / "data"
        u = data.get("usage") or {}
        # cache-aware (2026-07-25): cache writes bill ~like input; cache READS bill
        # at ~0.1x, so they count at a tenth — the ledger stays in cost-proportional
        # token units and the budget breaker keeps meaning what it meant.
        eff_in = (int(u.get("input_tokens") or 0)
                  + int(u.get("cache_creation_input_tokens") or 0)
                  + int(u.get("cache_read_input_tokens") or 0) // 10)
        row = [datetime.date.today().isoformat(), task, model,
               eff_in, int(u.get("output_tokens") or 0)]
        # anchored to the repo, not the CWD (2026-07-25 audit: a manual
        # run from elsewhere wrote spend into a stray data/ — the budget
        # breaker could be bypassed without anyone deciding to)
        path = _data_dir / "model_usage.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not path.exists()
        with path.open("a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["date", "task", "model", "input_tokens", "output_tokens"])
            w.writerow(row)
    except Exception:
        pass
_VERSION = "2023-06-01"
_TIMEOUT = 120

# The best model for each task — not one dial for everything.
_TASK_MODELS = {
    "study": "claude-sonnet-5",       # per-race read: strong + affordable
    "sceptic": "claude-sonnet-5",     # cost cut 2026-07-08: sonnet vs sonnet is a fair fight
    "synthesis": "claude-sonnet-5",   # weekly; sonnet suffices for the summary
    "nap": "claude-fable-5",          # THE pick: once a day, the only flagship call
}
_FALLBACK = "claude-sonnet-5"


def resolve_model(task: str) -> str:
    """Which model this task thinks with: per-task env > the TABLE > global env.
    THE TABLE NOW BEATS the global ANTHROPIC_MODEL (2026-07-08, the burn: a global
    =claude-fable-5 left in .env silently forced EVERY nightly call onto the most
    expensive model, overriding all the per-task savings). The global is now only a
    fallback for tasks the table doesn't know."""
    per_task = os.environ.get(f"ANTHROPIC_MODEL_{task.upper()}")
    if per_task:
        return per_task
    if task in _TASK_MODELS:
        return _TASK_MODELS[task]
    return os.environ.get("ANTHROPIC_MODEL") or _FALLBACK


# PER-TASK DAILY CEILINGS (the master, 2026-07-27: 'we need to be lean, stop
# wasting tokens, build a fail-safe in' — the global cap let one runaway path
# drain the whole pool; now each task has its own hard ceiling, env-overridable
# via NAP_TOKEN_BUDGET_<TASK>). Numbers sized ~2x normal daily use: headroom for
# a heavy card, a hard stop on a runaway.
_TASK_BUDGETS = {"nap": 80_000, "study": 60_000, "sceptic": 30_000,
                 "synthesis": 40_000}


def _budget_spent_today(task: str | None = None) -> int:
    """Tokens (in+out) logged today — for one task, or all. 0 if no ledger yet."""
    try:
        import csv
        import datetime
        from pathlib import Path
        today = datetime.date.today().isoformat()
        total = 0
        _data_dir = Path(__file__).resolve().parents[3] / "data"
        with (_data_dir / "model_usage.csv").open() as f:
            for row in csv.DictReader(f):
                if row["date"] == today and (task is None or row["task"] == task):
                    total += int(row["input_tokens"]) + int(row["output_tokens"])
        return total
    except Exception:
        return 0


def budget_blown(task: str | None = None) -> int | None:
    """The HARD token fail-safe, two layers (2026-07-08 global; 2026-07-27 per-task):
    the global day cap (env NAP_TOKEN_BUDGET, default 300k) AND each task's own
    ceiling — so a runaway morning can never eat the night school's budget or vice
    versa. Returns the offending spend if any cap is hit, else None."""
    try:
        cap = int(os.environ.get("NAP_TOKEN_BUDGET", "300000"))
    except ValueError:
        cap = 300000
    if cap <= 0:
        return _budget_spent_today() or 1          # 0 = model OFF entirely
    spent = _budget_spent_today()
    if spent >= cap:
        return spent
    if task and task in _TASK_BUDGETS:
        try:
            tcap = int(os.environ.get(f"NAP_TOKEN_BUDGET_{task.upper()}",
                                      str(_TASK_BUDGETS[task])))
        except ValueError:
            tcap = _TASK_BUDGETS[task]
        tspent = _budget_spent_today(task)
        if tcap > 0 and tspent >= tcap:
            return tspent
    return None


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
                     executor: Callable[[str, dict], str], max_steps: int = 4,
                     max_tokens: int = 3000):
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
        spent = budget_blown(task)
        if spent is not None:
            return "", [f"DAILY TOKEN BUDGET reached ({spent} used) — no more model "
                        f"calls today (raise NAP_TOKEN_BUDGET to override)"]
        # the big first prompt gets its own cache breakpoint; a ROLLING marker on
        # the newest tool-result extends the cached prefix every round (2026-07-25
        # review: system-only caching still re-billed the growing history in full)
        messages: list[dict] = [{"role": "user", "content": [
            {"type": "text", "text": prompt,
             "cache_control": {"type": "ephemeral"}}]}]
        trail: list[str] = []
        prev_marked: dict | None = None
        steps = 0
        budget = max_tokens
        bumped = False
        for _round in range(max_steps + 5):            # hard cap on conversation rounds
            # PROMPT CACHING (2026-07-25 audit): the loop re-billed the identical
            # system+tools+prompt prefix every tool round at full price. Cache
            # markers make each round after the first read the prefix at ~0.1x —
            # what made max_steps=6 affordable.
            body = {"model": model, "max_tokens": budget,
                    "system": [{"type": "text", "text": system,
                                "cache_control": {"type": "ephemeral"}}],
                    "messages": messages, "tools": tools}
            data, status = _post_with_retry(headers, body)
            if data is None:
                trail.append(f"API error {status or 'network'} — gave up after retries")
                return "", trail
            _log_usage(task, model, data)
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
                                        "content": out[:4000]})
                if results:
                    if prev_marked is not None:
                        prev_marked.pop("cache_control", None)
                    results[-1]["cache_control"] = {"type": "ephemeral"}
                    prev_marked = results[-1]
                messages.append({"role": "user", "content": results})
                continue
            text = "".join(b.get("text", "") for b in content if isinstance(b, dict))
            stop = data.get("stop_reason")
            # a TRUNCATED answer (max_tokens) is unusable even when text came back —
            # the JSON gets cut mid-string. Retry the same request once, budget doubled.
            if stop == "max_tokens" and not bumped:
                bumped = True
                budget *= 2
                trail.append(f"answer truncated at {budget // 2} tokens — "
                             f"retrying with max_tokens={budget}")
                continue
            if not text:                               # NEVER fail silently
                trail.append(f"empty final (stop={stop}, blocks="
                             f"{[b.get('type') for b in content if isinstance(b, dict)]})")
            return text, trail
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
        if budget_blown(task) is not None:
            return ""                              # daily budget reached — hard stop
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        data, _status = _post_with_retry(headers, body)
        if data is None:
            return ""
        _log_usage(task, model, data)
        parts = data.get("content") or []
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    return complete
