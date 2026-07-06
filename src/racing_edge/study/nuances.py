"""The nuance ledger — where the AI banks what it TEACHES ITSELF from results.

Every self-interrogation (study.selfcritique) that produces a lesson lands here, dated
and tagged the race that taught it, with the facts it rests on and what's OWED to
confirm it. Status starts 'proposed': a nuance is a candidate the TRIAL RECORD or the
MASTER promotes to a tell/rule — the model never writes the notebook on its own word.
One small SQLite table, the same shape as the nap log and study store.
"""

from __future__ import annotations

import contextlib
import sqlite3
from datetime import date
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nuance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    race_id     TEXT NOT NULL DEFAULT '',
    course      TEXT NOT NULL DEFAULT '',
    winner      TEXT NOT NULL DEFAULT '',
    blind_pick  TEXT NOT NULL DEFAULT '',
    nuance      TEXT NOT NULL DEFAULT '',
    what_missed TEXT NOT NULL DEFAULT '',
    cite        TEXT NOT NULL DEFAULT '',
    owed        TEXT NOT NULL DEFAULT '',
    confidence  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'proposed',   -- proposed | validated | rejected
    UNIQUE (date, race_id, nuance)
);
CREATE TABLE IF NOT EXISTS rule_evidence (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    race_id     TEXT NOT NULL DEFAULT '',
    rule        TEXT NOT NULL,                      -- e.g. '#22'
    verdict     TEXT NOT NULL,                      -- supports | contradicts
    note        TEXT NOT NULL DEFAULT '',
    UNIQUE (date, race_id, rule, verdict)
);
CREATE TABLE IF NOT EXISTS tracked (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,                      -- the race that taught the clue
    race_id     TEXT NOT NULL DEFAULT '',
    horse       TEXT NOT NULL,
    horse_id    TEXT NOT NULL DEFAULT '',
    angle       TEXT NOT NULL,                      -- follow | oppose
    note        TEXT NOT NULL DEFAULT '',
    conditions  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',     -- active | done
    UNIQUE (date, horse, angle)
);
"""


class NuanceLog:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        # migration: the sceptic's verdict is evidence too (audit 2026-07-05: refuted
        # nuances vanished, so the model's repeated failure modes were invisible)
        for col in ("sceptic_ground", "sceptic_reason"):
            with contextlib.suppress(sqlite3.OperationalError):   # column may exist
                self._conn.execute(f"ALTER TABLE nuance ADD COLUMN {col} TEXT DEFAULT ''")
        self._conn.commit()

    def record(self, *, day: date, race_id: str, course: str, winner: str,
               blind_pick: str, nuance: str, what_missed: str, cite: str,
               owed: str, confidence: str, status: str = "proposed",
               sceptic_ground: str = "", sceptic_reason: str = "") -> None:
        """Bank a nuance (proposed, or refuted-with-the-kill-reason). Idempotent on
        (date, race, nuance text)."""
        self._conn.execute(
            "INSERT OR IGNORE INTO nuance (date, race_id, course, winner, blind_pick, "
            "nuance, what_missed, cite, owed, confidence, status, sceptic_ground, "
            "sceptic_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (day.isoformat(), race_id, course, winner, blind_pick, nuance,
             what_missed, cite, owed, confidence, status, sceptic_ground,
             sceptic_reason),
        )
        self._conn.commit()

    def proposed(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM nuance WHERE status = 'proposed' ORDER BY date, id").fetchall()
        return [dict(r) for r in rows]

    def all(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM nuance ORDER BY date, id").fetchall()
        return [dict(r) for r in rows]

    def set_status(self, nuance_id: int, status: str) -> None:
        self._conn.execute("UPDATE nuance SET status = ? WHERE id = ?", (status, nuance_id))
        self._conn.commit()

    def record_evidence(self, *, day: date, race_id: str, rule: str, verdict: str,
                        note: str) -> None:
        """One race's verdict on one notebook rule — the notebook being TESTED."""
        self._conn.execute(
            "INSERT OR IGNORE INTO rule_evidence (date, race_id, rule, verdict, note) "
            "VALUES (?,?,?,?,?)",
            (day.isoformat(), race_id, rule, verdict, note),
        )
        self._conn.commit()

    def track(self, *, day: date, race_id: str, horse: str, horse_id: str,
              angle: str, note: str, conditions: str) -> None:
        """Bank a forward clue mined from a result — a horse to follow or oppose
        NEXT time (#27). Surfaced automatically when the horse reappears on a card."""
        self._conn.execute(
            "INSERT OR IGNORE INTO tracked (date, race_id, horse, horse_id, angle, "
            "note, conditions, status) VALUES (?,?,?,?,?,?,?, 'active')",
            (day.isoformat(), race_id, horse, horse_id, angle, note, conditions),
        )
        self._conn.commit()

    def tracked_active(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM tracked WHERE status = 'active' ORDER BY date").fetchall()
        return [dict(r) for r in rows]

    def rule_tally(self) -> list[dict]:
        """Per-rule evidence counts: how often results supported vs contradicted each
        notebook rule. The running scoreboard of the method itself."""
        rows = self._conn.execute(
            "SELECT rule, "
            "SUM(CASE WHEN verdict = 'supports' THEN 1 ELSE 0 END) AS supports, "
            "SUM(CASE WHEN verdict = 'contradicts' THEN 1 ELSE 0 END) AS contradicts "
            "FROM rule_evidence GROUP BY rule ORDER BY rule").fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
