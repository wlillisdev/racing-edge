"""Shared CLI helpers — the ledger location and date parsing."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from racing_edge.config import get_config
from racing_edge.measurement.store import Ledger


def open_ledger() -> Ledger:
    p = Path(get_config().project_dir) / "data" / "ledger.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return Ledger(p)


def resolve_date(s: str) -> date:
    if s == "today":
        return date.today()
    if s == "yesterday":
        return date.today() - timedelta(days=1)
    return datetime.strptime(s, "%Y-%m-%d").date()
