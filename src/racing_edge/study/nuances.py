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

from racing_edge.domain.units import uk_today

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
        self._conn = sqlite3.connect(str(path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        # migration: the sceptic's verdict is evidence too (audit 2026-07-05: refuted
        # nuances vanished, so the model's repeated failure modes were invisible)
        for col in ("sceptic_ground", "sceptic_reason"):
            with contextlib.suppress(sqlite3.OperationalError):   # column may exist
                self._conn.execute(f"ALTER TABLE nuance ADD COLUMN {col} TEXT DEFAULT ''")
        # migration 2026-07-25 (the self-study value audit): lessons carry a THEME
        # (fixed taxonomy), a MECHANISM (why it transfers) and a FAILS_WHEN (the kill
        # test); re-proposals become VOTES (seen_count) instead of new rows — the
        # loop was rediscovering the same lesson nightly with no memory of itself
        for col, typ in (("theme", "TEXT DEFAULT ''"), ("mechanism", "TEXT DEFAULT ''"),
                         ("fails_when", "TEXT DEFAULT ''"),
                         ("seen_count", "INTEGER DEFAULT 1"),
                         ("last_seen", "TEXT DEFAULT ''")):
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.execute(f"ALTER TABLE nuance ADD COLUMN {col} {typ}")
        for col, typ in (("theme", "TEXT DEFAULT ''"), ("held", "INTEGER")):
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.execute(f"ALTER TABLE tracked ADD COLUMN {col} {typ}")
        self._conn.commit()

    @staticmethod
    def _tokens(s: str) -> set:
        import re as _re
        stop = {"when", "that", "with", "this", "from", "have", "their", "there",
                "which", "into", "over", "than", "then", "them", "were", "does"}
        return set(_re.findall(r"[a-z]{4,}", s.lower())) - stop

    def find_duplicate(self, nuance: str, threshold: float = 0.6) -> dict | None:
        """The earlier lesson this nuance re-states, if any — token-Jaccard on
        content words (catches #190 re-proposing the Hoodie Hoo lesson verbatim-ish)."""
        a = self._tokens(nuance)
        if not a:
            return None
        for row in self.all():
            if row["status"] == "refuted":
                continue
            b = self._tokens(row["nuance"])
            if b and len(a & b) / len(a | b) >= threshold:
                return row
        return None

    def record(self, *, day: date, race_id: str, course: str, winner: str,
               blind_pick: str, nuance: str, what_missed: str, cite: str,
               owed: str, confidence: str, status: str = "proposed",
               sceptic_ground: str = "", sceptic_reason: str = "",
               theme: str = "", mechanism: str = "", fails_when: str = "") -> int | None:
        """Bank a nuance — or, if it re-states an earlier non-refuted lesson, count
        it as a VOTE on that lesson (seen_count += 1) instead of minting a row
        (2026-07-25 value audit: the loop proposed the same lesson nightly with no
        memory of itself — repetition is CONVERGENCE evidence, not new insight).
        Returns the id of the earlier lesson when merged, else None."""
        if status != "refuted":
            dup = self.find_duplicate(nuance)
            if dup is not None:
                self._conn.execute(
                    "UPDATE nuance SET seen_count = COALESCE(seen_count, 1) + 1, "
                    "last_seen = ? WHERE id = ?", (day.isoformat(), dup["id"]))
                self._conn.commit()
                return int(dup["id"])
        self._conn.execute(
            "INSERT OR IGNORE INTO nuance (date, race_id, course, winner, blind_pick, "
            "nuance, what_missed, cite, owed, confidence, status, sceptic_ground, "
            "sceptic_reason, theme, mechanism, fails_when) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (day.isoformat(), race_id, course, winner, blind_pick, nuance,
             what_missed, cite, owed, confidence, status, sceptic_ground,
             sceptic_reason, theme, mechanism, fails_when),
        )
        self._conn.commit()
        return None

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
              angle: str, note: str, conditions: str, theme: str = "") -> None:
        """Bank a forward clue mined from a result — a horse to follow or oppose
        NEXT time (#27). Surfaced automatically when the horse reappears on a card."""
        self._conn.execute(
            "INSERT OR IGNORE INTO tracked (date, race_id, horse, horse_id, angle, "
            "note, conditions, status, theme) VALUES (?,?,?,?,?,?,?, 'active', ?)",
            (day.isoformat(), race_id, horse, horse_id, angle, note, conditions, theme),
        )
        self._conn.commit()

    def tracked_active(self) -> list[dict]:
        """Active clues no older than 28 days — a clue is about the horse's NEXT run;
        a month on, that run has happened unseen or the clue is stale either way
        (coroner 2026-07-21: 872 rows, the oldest from week one, none ever settled)."""
        from datetime import timedelta
        cutoff = (uk_today() - timedelta(days=28)).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM tracked WHERE status = 'active' AND date >= ? ORDER BY date",
            (cutoff,)).fetchall()
        return [dict(r) for r in rows]

    def expire_tracked(self, days: int = 28) -> int:
        """The nightly broom (2026-07-25: health nagged '225 clues older than 3 weeks'
        forever — the 28-day filter hid them from the working lists but the rows sat
        'active' in the DB for good). A clue whose horse hasn't reappeared within
        `days` is marked done-expired: the lead went cold, honestly. Returns rows swept."""
        from datetime import timedelta
        cutoff = (uk_today() - timedelta(days=days)).isoformat()
        cur = self._conn.execute(
            "UPDATE tracked SET status = 'done', "
            "note = note || '  [expired unverified — horse never reappeared]' "
            "WHERE status = 'active' AND date < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def tracked_stale(self, days: int = 28) -> int:
        """Rows STILL marked active in the DB beyond the expiry horizon — should be
        ~0 while the nightly broom runs; a growing count means the broom is dead."""
        from datetime import timedelta
        cutoff = (uk_today() - timedelta(days=days)).isoformat()
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM tracked WHERE status = 'active' AND date < ?",
            (cutoff,)).fetchone()
        return int(row["n"])

    def settle_tracked(self, horse_id: str, *, outcome: str,
                       held: bool | None = None) -> int:
        """The clue's horse RAN — the clue is spent. Mark every active row for the
        horse 'done', stamp how it worked out, and store HELD/missed (the clue
        stream's own strike rate — the most direct measure of study value).
        Returns rows settled."""
        cur = self._conn.execute(
            "UPDATE tracked SET status = 'done', held = ?, "
            "note = note || '  [settled: ' || ? || ']' "
            "WHERE horse_id = ? AND status = 'active'",
            (None if held is None else int(held), outcome, horse_id))
        self._conn.commit()
        return cur.rowcount

    def clue_scoreboard(self, since: str = "2026-07-22") -> dict:
        """Follow/oppose hit rates over SETTLED clues (since the fair-court +
        settle-on-run era; older rows are structurally unsettled). Baselines the
        report must print beside them: a random runner wins ~10-11% (follow must
        beat that to mean anything); 'oppose succeeded' is nearly free against
        outsiders, so judge oppose only against fancied runners over time."""
        rows = self._conn.execute(
            "SELECT angle, held FROM tracked WHERE status = 'done' "
            "AND held IS NOT NULL AND date >= ?", (since,)).fetchall()
        out = {"follow": {"n": 0, "hits": 0}, "oppose": {"n": 0, "hits": 0}}
        for r in rows:
            b = out.get(r["angle"])
            if b is None:
                continue
            b["n"] += 1
            b["hits"] += int(r["held"])
        for b in out.values():
            b["rate"] = (b["hits"] / b["n"]) if b["n"] else None
        return out

    def field_test_themes(self, min_n: int = 5, min_rate: float = 0.6) -> list[str]:
        """RECORD-BASED promotion (the design's own law: 'the TRIAL RECORD or the
        MASTER promotes'): when a theme's settled clues prove out (>= min_n settled,
        >= min_rate held), its proposed nuances become 'field-tested' — earned by
        results, never by the model's say-so; 'validated' stays master-only."""
        rows = self._conn.execute(
            "SELECT theme, COUNT(*) AS n, SUM(held) AS h FROM tracked "
            "WHERE status = 'done' AND held IS NOT NULL AND theme != '' "
            "GROUP BY theme").fetchall()
        promoted = []
        for r in rows:
            if r["n"] >= min_n and (r["h"] or 0) / r["n"] >= min_rate:
                cur = self._conn.execute(
                    "UPDATE nuance SET status = 'field-tested' "
                    "WHERE theme = ? AND status = 'proposed'", (r["theme"],))
                if cur.rowcount:
                    promoted.append(f"{r['theme']} ({r['h']}/{r['n']} clues held)")
        self._conn.commit()
        return promoted

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
