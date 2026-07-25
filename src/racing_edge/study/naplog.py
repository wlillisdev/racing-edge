"""The nap log — one nap a day, recorded and settled, so a STRIKE RATE accumulates.

The cure for n=1: every nap the system nominates is banked here the morning it's made,
then settled against the result. Over weeks it answers the only question that matters —
how often does the nap win, and how often only when it was a CONFIDENT (mark-read) nap
versus a reasoned lean? One small SQLite table, same pattern as the picks/study stores.
"""

from __future__ import annotations

import contextlib
import sqlite3
from datetime import date
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nap (
    date        TEXT NOT NULL,
    race_id     TEXT NOT NULL,
    course      TEXT NOT NULL DEFAULT '',
    horse       TEXT NOT NULL DEFAULT '',
    horse_id    TEXT NOT NULL DEFAULT '',
    price       REAL,
    score       INTEGER NOT NULL DEFAULT 0,
    confident   INTEGER NOT NULL DEFAULT 0,
    won         INTEGER,                       -- NULL until settled; 1 win / 0 not
    sp_dec      REAL,
    PRIMARY KEY (date)
);
CREATE TABLE IF NOT EXISTS shadow (
    date        TEXT NOT NULL,
    race_id     TEXT NOT NULL,
    course      TEXT NOT NULL DEFAULT '',
    horse       TEXT NOT NULL DEFAULT '',
    horse_id    TEXT NOT NULL DEFAULT '',
    price       REAL,
    score       INTEGER NOT NULL DEFAULT 0,
    won         INTEGER,
    sp_dec      REAL,
    PRIMARY KEY (date)
);
"""


class NapLog:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        # migration: the CASE rides with the pick (audit 2026-07-05: the night study
        # was critiquing a pick whose reasoning it could not see — "a self-critique of
        # an invented memory"). Older ledgers gain the columns in place.
        for col in ("case_text", "deep_conf"):
            with contextlib.suppress(sqlite3.OperationalError):   # column may exist
                self._conn.execute(f"ALTER TABLE nap ADD COLUMN {col} TEXT DEFAULT ''")
        self._conn.commit()

    def record(self, *, day: date, race_id: str, course: str, horse: str, horse_id: str,
               price: float | None, score: int, confident: bool,
               case: str = "", deep_conf: str = "") -> None:
        """Bank the morning's nap (unsettled), WITH its reasoning. Idempotent on the day."""
        self._conn.execute(
            "INSERT OR REPLACE INTO nap (date, race_id, course, horse, horse_id, price, "
            "score, confident, won, sp_dec, case_text, deep_conf) "
            "VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?,?)",
            (day.isoformat(), race_id, course, horse, horse_id, price, score,
             int(confident), case, deep_conf),
        )
        self._conn.commit()

    def record_pass(self, *, day: date, reason: str) -> None:
        """Bank a NO-BET day as a first-class row (won=-1: settled as 'no bet').
        2026-07-18: an earned pass and a dead pipeline looked identical — empty inbox,
        empty ledger. Now quiet days carry their reason and the watchman can tell
        discipline from failure."""
        self._conn.execute(
            "INSERT OR REPLACE INTO nap (date, race_id, course, horse, horse_id, price, "
            "score, confident, won, sp_dec, case_text, deep_conf) "
            "VALUES (?,'PASS','','NO BET','',NULL,0,0,-1,NULL,?, '')",
            (day.isoformat(), reason),
        )
        self._conn.commit()

    def settle(self, day: date, won: bool, sp_dec: float | None = None) -> None:
        self._conn.execute("UPDATE nap SET won = ?, sp_dec = ? WHERE date = ?",
                           (int(won), sp_dec, day.isoformat()))
        self._conn.commit()

    def strike_rate(self, confident_only: bool = False) -> tuple[int, int]:
        """(naps won, naps settled). Pass confident_only to judge the real naps alone."""
        q = "SELECT COUNT(*) FROM nap WHERE won IN (0, 1)"      # -1 = pass day, not a bet
        if confident_only:
            q += " AND confident = 1"
        settled = int(self._conn.execute(q).fetchone()[0])
        wins = int(self._conn.execute(q + " AND won = 1").fetchone()[0])
        return wins, settled

    def pending(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM nap WHERE won IS NULL ORDER BY date").fetchall()
        return [dict(r) for r in rows]

    def history(self) -> list[dict]:
        """Every nap ever banked, oldest first — the readable record (settled + pending)."""
        rows = self._conn.execute("SELECT * FROM nap ORDER BY date").fetchall()
        return [dict(r) for r in rows]

    # ---- the SHADOW ledger: the mechanical engine's pick, banked for A/B ---------
    # (the master, 2026-07-08: the trial method is best AND the older method's shadow
    # picks are good — so both get a record, one machine, two ledgers, zero extra cost)
    def record_shadow(self, *, day: date, race_id: str, course: str, horse: str,
                      horse_id: str, price: float | None, score: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO shadow (date, race_id, course, horse, horse_id, "
            "price, score, won, sp_dec) VALUES (?,?,?,?,?,?,?,NULL,NULL)",
            (day.isoformat(), race_id, course, horse, horse_id, price, score),
        )
        self._conn.commit()

    def pending_shadow(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM shadow WHERE won IS NULL ORDER BY date").fetchall()
        return [dict(r) for r in rows]

    def settle_shadow(self, day: date, won: bool, sp_dec: float | None = None) -> None:
        self._conn.execute("UPDATE shadow SET won = ?, sp_dec = ? WHERE date = ?",
                           (int(won), sp_dec, day.isoformat()))
        self._conn.commit()

    def shadow_strike(self) -> tuple[int, int]:
        settled = int(self._conn.execute(
            "SELECT COUNT(*) FROM shadow WHERE won IS NOT NULL").fetchone()[0])
        wins = int(self._conn.execute(
            "SELECT COUNT(*) FROM shadow WHERE won = 1").fetchone()[0])
        return wins, settled

    def close(self) -> None:
        self._conn.close()
