"""
model_cost_guard.py — track LLM spend from real token usage and stop runaways.

File-based monthly ledger (data/llm_cost_<YYYY-MM>.json) — deliberately no DB
dependency, so the safety net works even if the warehouse is down. Any component
that makes LLM calls records token usage here:

  - SOFT threshold  -> logs a WARNING and writes data/cost_alert_<month>.flag
                       (surfaced by the pipeline) so you're notified.
  - HARD cap        -> callers check should_halt() and skip further LLM calls
                       for the rest of the month, so spend physically cannot run
                       away beyond the cap.

Thresholds are env-overridable (LLM_BUDGET_SOFT_USD / LLM_BUDGET_HARD_USD).
Prices are $ per 1M tokens (input, output) — keep in sync with the model
catalogue.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.helpers import data_path, log

PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-8":   (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5":  (1.0,  5.0),
}
_DEFAULT_PRICE = PRICES["claude-opus-4-8"]

SOFT_USD = float(os.environ.get("LLM_BUDGET_SOFT_USD", "30"))   # warn at
HARD_USD = float(os.environ.get("LLM_BUDGET_HARD_USD", "50"))   # halt at


def cost_of(model: str, in_tok: int, out_tok: int) -> float:
    p_in, p_out = PRICES.get(model, _DEFAULT_PRICE)
    return in_tok / 1_000_000 * p_in + out_tok / 1_000_000 * p_out


class CostMeter:
    """Accumulates token usage across calls within one run."""

    def __init__(self) -> None:
        self.calls = self.in_tok = self.out_tok = 0
        self.usd = 0.0

    def add(self, model: str, usage) -> None:
        it = int(getattr(usage, "input_tokens", 0) or 0)
        ot = int(getattr(usage, "output_tokens", 0) or 0)
        self.calls += 1
        self.in_tok += it
        self.out_tok += ot
        self.usd += cost_of(model, it, ot)


def _ledger_path(month: str) -> Path:
    return Path(data_path(f"llm_cost_{month}.json"))


def _load(month: str) -> dict:
    p = _ledger_path(month)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    return {"month": month, "total_usd": 0.0, "by_day": {}, "by_component": {}}


def month_to_date(date_str: str) -> float:
    return float(_load(date_str[:7]).get("total_usd", 0.0))


def should_halt(date_str: str, hard: float = HARD_USD) -> bool:
    """True once this month's spend has reached the hard cap — callers skip LLM work."""
    return month_to_date(date_str) >= hard


def commit(meter: CostMeter, date_str: str, component: str) -> float:
    """Add a run's spend to the monthly ledger; return the new month-to-date total."""
    month = date_str[:7]
    led = _load(month)
    led["total_usd"] = round(led.get("total_usd", 0.0) + meter.usd, 4)
    d = led["by_day"].setdefault(date_str, {"usd": 0.0, "calls": 0})
    d["usd"] = round(d["usd"] + meter.usd, 4)
    d["calls"] += meter.calls
    c = led["by_component"].setdefault(component, {"usd": 0.0, "calls": 0})
    c["usd"] = round(c["usd"] + meter.usd, 4)
    c["calls"] += meter.calls
    try:
        _ledger_path(month).write_text(json.dumps(led, indent=2))
    except OSError as exc:
        log(f"model_cost_guard: ledger write failed — {exc}", "WARNING")
    return led["total_usd"]


def check_and_alert(month_total: float, date_str: str,
                    soft: float = SOFT_USD, hard: float = HARD_USD) -> str:
    """Return 'ok' | 'warn' | 'halt' and raise an alert flag on warn/halt."""
    if month_total >= hard:
        _alert(date_str, "HALT", month_total, hard)
        return "halt"
    if month_total >= soft:
        _alert(date_str, "WARN", month_total, soft)
        return "warn"
    return "ok"


def _alert(date_str: str, level: str, total: float, threshold: float) -> None:
    month = date_str[:7]
    msg = (f"[COST] {level}: LLM spend ${total:.2f} for {month} "
           f"(threshold ${threshold:.0f})")
    log(f"model_cost_guard: {msg}", "ERROR" if level == "HALT" else "WARNING")
    try:
        Path(data_path(f"cost_alert_{month}.flag")).write_text(msg + "\n")
    except OSError:
        pass


def status_line(date_str: str) -> str:
    led = _load(date_str[:7])
    return (f"LLM spend {date_str[:7]}: ${led.get('total_usd', 0.0):.2f} "
            f"(soft ${SOFT_USD:.0f} / hard ${HARD_USD:.0f})")
