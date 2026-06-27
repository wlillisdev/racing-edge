"""The ledger store — one canonical settled-pick table (the audit's fix for the
three split CSVs + double-logging). SQLite: a real, queryable DB with zero
server setup, atomic, file-based. Picks are written pending in the morning and
settled against results in the evening; metrics read only from here.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from racing_edge.measurement.record import SettledPick

_SCHEMA = """
CREATE TABLE IF NOT EXISTS picks (
    date        TEXT NOT NULL,
    race_id     TEXT NOT NULL,
    horse_id    TEXT NOT NULL,
    horse       TEXT NOT NULL,
    system      TEXT NOT NULL,        -- 'method' | 'favourite'
    season      TEXT NOT NULL,
    code        TEXT NOT NULL,        -- 'jump' | 'flat'
    price_taken REAL,                 -- the price available when picked
    score       REAL,                 -- the method's conviction (sum of signal weights)
    signals     TEXT DEFAULT '',      -- the signal names that fired (for ablation analysis)
    sp          REAL,                 -- settled price (filled at settle)
    position    INTEGER,              -- finishing position (filled at settle)
    settled     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, race_id, horse_id, system)
);
"""


class Ledger:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        # migrate older ledgers that pre-date the score/signals columns
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(picks)")}
        for col, decl in (("score", "REAL"), ("signals", "TEXT DEFAULT ''")):
            if col not in cols:
                self._conn.execute(f"ALTER TABLE picks ADD COLUMN {col} {decl}")
        self._conn.commit()

    def record(self, *, day: date, race_id: str, horse_id: str, horse: str, system: str,
               season: str, code: str, price_taken: float | None,
               score: float | None = None, signals: str = "") -> None:
        """Write a pending pick. Idempotent — never double-logs the same key."""
        self._conn.execute(
            "INSERT OR IGNORE INTO picks "
            "(date, race_id, horse_id, horse, system, season, code, price_taken, score, signals) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (day.isoformat(), race_id, horse_id, horse, system, season, code,
             price_taken, score, signals),
        )
        self._conn.commit()

    def settle_runner(self, *, day: date, race_id: str, horse_id: str,
                      position: int | None, sp: float | None) -> None:
        """Fill the result for a pending pick (any system)."""
        self._conn.execute(
            "UPDATE picks SET sp=?, position=?, settled=1 "
            "WHERE date=? AND race_id=? AND horse_id=? AND settled=0",
            (sp, position, day.isoformat(), race_id, horse_id),
        )
        self._conn.commit()

    def settled_picks(self) -> list[SettledPick]:
        rows = self._conn.execute("SELECT * FROM picks WHERE settled=1").fetchall()
        return [
            SettledPick(
                date=datetime.strptime(r["date"], "%Y-%m-%d").date(),
                race_id=r["race_id"], horse_id=r["horse_id"], horse=r["horse"],
                system=r["system"], season=r["season"], code=r["code"],
                price_taken=r["price_taken"], sp=r["sp"], position=r["position"],
                score=r["score"], signals=r["signals"] or "",
            )
            for r in rows
        ]

    def pending_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM picks WHERE settled=0").fetchone()[0])

    def close(self) -> None:
        self._conn.close()
