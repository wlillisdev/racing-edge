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


def run_guarded(task: str, main) -> int:
    """The LAST-RESORT crash net for scheduled entry points (2026-08-01
    architecture pass: the night school crashed identically three nights
    running and the only evidence was a traceback in a log nobody reads —
    a system that fails silently isn't consistent, it's lucky). An unhandled
    crash prints its full traceback, EMAILS the master one line naming the
    error, and exits 1. It never invents success and never swallows the
    traceback — the flight recorder still gets everything."""
    try:
        return main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as exc:
        import traceback
        print(traceback.format_exc(), flush=True)
        head = f"{exc.__class__.__name__}: {str(exc)[:200]}"
        try:
            from racing_edge.report.mail import send
            sent = send(f"⚠ {task} CRASHED — needs a look",
                        f"The '{task}' run died with an unhandled error:\n\n  {head}\n\n"
                        f"Full traceback in data/task_runs.log on the box "
                        f"(grep 'trial.sh' for the run's section).")
            print(f"  crash email {'sent' if sent else 'NOT sent (mail unconfigured)'}",
                  flush=True)
        except Exception:
            print("  crash email could not be sent", flush=True)
        return 1


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
