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
    if s == "today":
        return date.today()
    if s == "yesterday":
        return date.today() - timedelta(days=1)
    return datetime.strptime(s, "%Y-%m-%d").date()
