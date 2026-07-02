"""The nuance ledger — where the AI banks what it TEACHES ITSELF from results.

Every self-interrogation (study.selfcritique) that produces a lesson lands here, dated
and tagged the race that taught it, with the facts it rests on and what's OWED to
confirm it. Status starts 'proposed': a nuance is a candidate the TRIAL RECORD or the
MASTER promotes to a tell/rule — the model never writes the notebook on its own word.
One small SQLite table, the same shape as the nap log and study store.
"""

from __future__ import annotations

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
"""


class NuanceLog:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, *, day: date, race_id: str, course: str, winner: str,
               blind_pick: str, nuance: str, what_missed: str, cite: str,
               owed: str, confidence: str) -> None:
        """Bank a proposed nuance. Idempotent on (date, race, nuance text)."""
        self._conn.execute(
            "INSERT OR IGNORE INTO nuance (date, race_id, course, winner, blind_pick, "
            "nuance, what_missed, cite, owed, confidence, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?, 'proposed')",
            (day.isoformat(), race_id, course, winner, blind_pick, nuance,
             what_missed, cite, owed, confidence),
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
