"""Shared CLI helpers — the ledger location and date parsing."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from racing_edge.config import get_config
from racing_edge.study.naplog import NapLog
from racing_edge.study.nuances import NuanceLog
from racing_edge.study.store import StudyStore


def open_nap_log() -> NapLog:
    p = Path(get_config().project_dir) / "data" / "nap.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return NapLog(p)


def open_study_store() -> StudyStore:
    p = Path(get_config().project_dir) / "data" / "study.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return StudyStore(p)


def open_nuance_log() -> NuanceLog:
    p = Path(get_config().project_dir) / "data" / "nuances.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return NuanceLog(p)


def resolve_date(s: str) -> date:
    """'today' means the RACING day — Europe/London — not the box's UTC clock
    (2026-07-25 reliability audit: a UTC box's date and the card's date part ways
    at midnight London time; every ledger row keys on this)."""
    from zoneinfo import ZoneInfo
    _today = datetime.now(ZoneInfo("Europe/London")).date()
    if s == "today":
        return _today
    if s == "yesterday":
        return _today - timedelta(days=1)
    return datetime.strptime(s, "%Y-%m-%d").date()
