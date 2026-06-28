"""The study store — where the detective work accumulates and stays queryable.

study_card() studies every race each night; without a home those records vanish.
This persists them so the notebook's rules can be tested against a growing body of
real results ("how often did the 2nd/3rd fav win over 500 races?", "which manner
preceded our losses?"). One small SQLite table, same pattern as the picks ledger.

The qualitative RULES stay in docs/handicapping_notebook.md — a rulebook to read,
not a query target. This stores the STUDY DATA the rules are tested against.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from racing_edge.study.postmortem import RaceStudy

_SCHEMA = """
CREATE TABLE IF NOT EXISTS race_study (
    date               TEXT NOT NULL,
    race_id            TEXT NOT NULL,
    course             TEXT NOT NULL DEFAULT '',
    winner             TEXT,
    winner_market_rank INTEGER,        -- 1 = fav, 2 = 2nd fav, ...
    winner_manner      TEXT,
    field_size         INTEGER,
    our_pick           TEXT,
    our_pick_pos       INTEGER,
    our_pick_manner    TEXT,
    lessons            TEXT DEFAULT '', -- newline-joined findings
    gaps               TEXT DEFAULT '', -- grunt work still owed (franking, the mark, ...)
    PRIMARY KEY (date, race_id)
);
"""


class StudyStore:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(race_study)")}
        if "gaps" not in cols:                       # migrate older study DBs
            self._conn.execute("ALTER TABLE race_study ADD COLUMN gaps TEXT DEFAULT ''")
        self._conn.commit()

    def record(self, *, day: date, race_id: str, course: str, study: RaceStudy) -> None:
        """Persist one race's study. Idempotent — re-studying replaces the row."""
        self._conn.execute(
            "INSERT OR REPLACE INTO race_study (date, race_id, course, winner, "
            "winner_market_rank, winner_manner, field_size, our_pick, our_pick_pos, "
            "our_pick_manner, lessons, gaps) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (day.isoformat(), race_id, course, study.winner, study.winner_market_rank,
             study.winner_manner, study.field_size, study.our_pick, study.our_pick_pos,
             study.our_pick_manner, "\n".join(study.lessons), "\n".join(study.gaps)),
        )
        self._conn.commit()

    def record_card(self, day: date, race_ids: Sequence[str], courses: Sequence[str],
                    studies: Sequence[RaceStudy]) -> int:
        for rid, course, study in zip(race_ids, courses, studies, strict=True):
            self.record(day=day, race_id=rid, course=course, study=study)
        return len(studies)

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM race_study").fetchone()[0])

    def rule2_rate(self) -> tuple[int, int]:
        """(races the 2nd/3rd fav won, races with a ranked winner) — rule #2, in the wild."""
        hits = self._conn.execute(
            "SELECT COUNT(*) FROM race_study WHERE winner_market_rank IN (2, 3)").fetchone()[0]
        total = self._conn.execute(
            "SELECT COUNT(*) FROM race_study WHERE winner_market_rank IS NOT NULL").fetchone()[0]
        return int(hits), int(total)

    def all_studies(self) -> list[dict]:
        """Every studied race, oldest first — the body the homework miner reads."""
        rows = self._conn.execute(
            "SELECT date, race_id, course, winner, winner_market_rank, winner_manner, "
            "field_size, our_pick, our_pick_pos, our_pick_manner, lessons, gaps "
            "FROM race_study ORDER BY date").fetchall()
        return [dict(r) for r in rows]

    def lessons_log(self, limit: int = 50) -> list[tuple[str, str]]:
        """Recent (date, lesson) lines — the running record of what the card taught."""
        rows = self._conn.execute(
            "SELECT date, lessons FROM race_study WHERE lessons != '' "
            "ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
        return [(r["date"], line) for r in rows for line in r["lessons"].split("\n") if line]

    def close(self) -> None:
        self._conn.close()
