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
CREATE TABLE IF NOT EXISTS favline (
    date        TEXT NOT NULL,
    race_id     TEXT NOT NULL,
    course      TEXT NOT NULL DEFAULT '',
    horse       TEXT NOT NULL DEFAULT '',
    horse_id    TEXT NOT NULL DEFAULT '',
    price       REAL,
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
        # 'aligned' (2026-07-25, the dial-in gauges): the lenses that fired at
        # banking, stored so wins/losses can be ATTRIBUTED per lens family
        for col in ("case_text", "deep_conf", "aligned"):
            with contextlib.suppress(sqlite3.OperationalError):   # column may exist
                self._conn.execute(f"ALTER TABLE nap ADD COLUMN {col} TEXT DEFAULT ''")
        # 'race_quality' (2026-08-22, the two-column record — the master: 'go for
        # it'): the fingerprint score banks WITH the pick so the ledger can judge
        # betting-race picks apart from forced dreck-day picks.
        with contextlib.suppress(sqlite3.OperationalError):
            self._conn.execute(
                "ALTER TABLE nap ADD COLUMN race_quality INTEGER DEFAULT 0")
        self._conn.commit()

    def record(self, *, day: date, race_id: str, course: str, horse: str, horse_id: str,
               price: float | None, score: int, confident: bool,
               case: str = "", deep_conf: str = "", aligned: str = "",
               race_quality: int = 0) -> None:
        """Bank the morning's nap (unsettled), WITH its reasoning. Idempotent on the day."""
        self._conn.execute(
            "INSERT OR REPLACE INTO nap (date, race_id, course, horse, horse_id, price, "
            "score, confident, won, sp_dec, case_text, deep_conf, aligned, race_quality) "
            "VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?,?,?,?)",
            (day.isoformat(), race_id, course, horse, horse_id, price, score,
             int(confident), case, deep_conf, aligned, int(race_quality)),
        )
        self._conn.commit()

    def record_split(self, bar: int = 2) -> tuple[tuple[int, int], tuple[int, int]]:
        """((wins, settled) in BETTING races, (wins, settled) in the rest).
        The two-column record (the master, 2026-08-22: opinion on everything,
        money-shape on few): a betting race carries fingerprint score >= bar
        (concentrated quality handicap territory); the system is JUDGED on
        that column — the forced dreck-day column is duty, not evidence."""
        out = []
        for cond in ("race_quality >= ?", "race_quality < ?"):
            q = f"SELECT COUNT(*) FROM nap WHERE won IN (0, 1) AND {cond}"
            settled = int(self._conn.execute(q, (bar,)).fetchone()[0])
            wins = int(self._conn.execute(q + " AND won = 1", (bar,)).fetchone()[0])
            out.append((wins, settled))
        return out[0], out[1]

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

    def profit_loss(self) -> tuple[float, int]:
        """(level-stakes P/L at SP, bets counted). THE money gauge (2026-07-25, the
        master: 'now we have the problem of picking winners' — a strike rate without
        prices measures nothing; 44% at 4.5s is an edge, 44% at 2.2s is ruin)."""
        rows = self._conn.execute(
            "SELECT won, sp_dec FROM nap WHERE won IN (0, 1)").fetchall()
        pnl, n = 0.0, 0
        for r in rows:
            if r["won"] == 1 and r["sp_dec"]:
                pnl += float(r["sp_dec"]) - 1.0
                n += 1
            elif r["won"] in (0, 1):
                pnl -= 1.0 if r["won"] == 0 else 0.0
                n += 1 if r["won"] == 0 else 0
        return pnl, n

    def lens_attribution(self) -> list[dict]:
        """Per lens-label: how many settled WINNERS vs LOSERS carried it at banking.
        The dial-in gauge: a lens that keeps appearing on losers and never winners is
        a knob to turn DOWN — by evidence, not by last week's mood."""
        rows = self._conn.execute(
            "SELECT won, aligned FROM nap WHERE won IN (0, 1) "
            "AND aligned IS NOT NULL AND aligned != ''").fetchall()
        tally: dict[str, list[int]] = {}
        for r in rows:
            for label in (x.strip() for x in r["aligned"].split("|") if x.strip()):
                key = label.split(" (")[0]          # collapse detail: 'well-in (…)'
                t = tally.setdefault(key, [0, 0])
                t[0 if r["won"] == 1 else 1] += 1
        return [{"lens": k, "wins": v[0], "losses": v[1]}
                for k, v in sorted(tally.items(), key=lambda kv: -sum(kv[1]))]

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

    def veto_watch(self, days: int = 7) -> tuple[int, int]:
        """THE VETO TRIPWIRE (2026-08-08, the flip — the master: 'how do we
        build a fail safe to stop you departing from it'). The reader's one
        remaining power is the veto; over-use is departure by the back door,
        and a veto that killed a WINNER must surface by name. Returns
        (vetoes banked in the window, vetoed picks that then won — joined
        against the shadow column where every vetoed pick banks)."""
        from datetime import timedelta
        cut = (date.today() - timedelta(days=days)).isoformat()
        v = int(self._conn.execute(
            "SELECT COUNT(*) FROM nap WHERE won = -1 AND date >= ? "
            "AND case_text LIKE 'reader veto%'", (cut,)).fetchone()[0])
        k = int(self._conn.execute(
            "SELECT COUNT(*) FROM nap n JOIN shadow s ON s.date = n.date "
            "WHERE n.won = -1 AND n.date >= ? "
            "AND n.case_text LIKE 'reader veto%' AND s.won = 1",
            (cut,)).fetchone()[0])
        return v, k

    # THE FAV LINE (the master, 2026-08-16: 'ok lets do favourite and value
    # bet, what have we got to lose the information is there'): the market's
    # own pick in the nap's race, banked beside ours every day — two bets,
    # one record, and the ledger says which one earns real stakes.
    def record_favline(self, *, day: date, race_id: str, course: str, horse: str,
                       horse_id: str, price: float | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO favline (date, race_id, course, horse, "
            "horse_id, price) VALUES (?, ?, ?, ?, ?, ?)",
            (day.isoformat(), race_id, course, horse, horse_id, price))
        self._conn.commit()

    def pending_favline(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM favline WHERE won IS NULL ORDER BY date").fetchall()]

    def settle_favline(self, day: date, won: bool, sp_dec: float | None = None) -> None:
        self._conn.execute("UPDATE favline SET won = ?, sp_dec = ? WHERE date = ?",
                           (1 if won else 0, sp_dec, day.isoformat()))
        self._conn.commit()

    def favline_record(self) -> tuple[int, int, float]:
        """(wins, settled, level-stakes P/L at SP) for the favourite line."""
        rows = self._conn.execute(
            "SELECT won, sp_dec FROM favline WHERE won IS NOT NULL").fetchall()
        wins = sum(1 for r in rows if r["won"] == 1)
        pnl = sum((r["sp_dec"] - 1.0) if r["won"] == 1 and r["sp_dec"] else -1.0
                  for r in rows)
        return wins, len(rows), pnl

    def shadow_strike(self) -> tuple[int, int]:
        settled = int(self._conn.execute(
            "SELECT COUNT(*) FROM shadow WHERE won IS NOT NULL").fetchone()[0])
        wins = int(self._conn.execute(
            "SELECT COUNT(*) FROM shadow WHERE won = 1").fetchone()[0])
        return wins, settled

    def close(self) -> None:
        self._conn.close()
