"""THE RECORD, MADE READABLE — the export that lets the repo check the numbers.

The audit of 2026-09-20 found that `data/*.db` is gitignored, so the record
that judges the work (law 1: picks settle at SP in nap.db) could not be read
from the session doing the work. Every strike rate this project has quoted
came from a summary or from memory. With a one-month deadline running, the
export IS the instrument that measures the month.

These tests pin the arithmetic, because an instrument that reads wrong is
worse than no instrument.
"""
import csv
import sqlite3

from racing_edge.school import record_export as R


def _db(tmp_path, naps, favs=()):
    p = tmp_path / "nap.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE nap (date TEXT PRIMARY KEY, race_id TEXT, course TEXT, "
              "horse TEXT, horse_id TEXT, price REAL, score INTEGER, "
              "confident INTEGER, won INTEGER, sp_dec REAL)")
    c.execute("CREATE TABLE favline (date TEXT PRIMARY KEY, race_id TEXT, course TEXT, "
              "horse TEXT, horse_id TEXT, price REAL, won INTEGER, sp_dec REAL)")
    for n in naps:
        c.execute("INSERT INTO nap (date,race_id,course,horse,horse_id,price,score,"
                  "confident,won,sp_dec) VALUES (?,?,?,?,?,?,?,?,?,?)", n)
    for f in favs:
        c.execute("INSERT INTO favline (date,race_id,course,horse,horse_id,price,"
                  "won,sp_dec) VALUES (?,?,?,?,?,?,?,?)", f)
    c.commit()
    c.close()
    return p


def test_a_missing_ledger_is_said_plainly_and_never_faked(tmp_path):
    """On this machine nap.db does not exist — the box writes it. That must
    produce an honest empty record, not a crash and not an invented number."""
    csv_p, md_p = tmp_path / "record.csv", tmp_path / "THE_RECORD.md"
    assert R.export(tmp_path / "absent.db", csv_p, md_p) == 0
    assert "No record yet" in md_p.read_text()
    assert list(csv.DictReader(open(csv_p))) == []


def test_the_strike_and_level_stakes_arithmetic(tmp_path):
    """Three settled bets: a 3.0 winner, a loser, a 2.5 winner.
    P/L = +2.00 -1.00 +1.50 = +2.50 over 3 = +83.3% ROI, strike 66.7%."""
    db = _db(tmp_path, [
        ("2026-09-05", "r1", "Thirsk", "Proposal", "h1", 3.0, 9, 1, 1, 3.0),
        ("2026-09-12", "r2", "Leopardstown", "Constitution River", "h2", 2.5, 8, 1, 0, 2.38),
        ("2026-09-21", "r3", "Ayr", "Somehorse", "h3", 2.5, 7, 0, 1, 2.5),
    ])
    s = R.summarise(R.rows(db))
    assert s["settled"] == 3 and s["wins"] == 2
    assert round(s["strike"], 1) == 66.7
    assert round(s["pl"], 2) == 2.50
    assert round(s["roi"], 1) == 83.3


def test_a_pass_is_a_position_and_never_counted_as_a_losing_bet(tmp_path):
    """The engine banks a NAMED PASS when it declines ("an earned pass, not a
    failure"). A pass must show in the record as a day taken, and must never
    be scored as a loser — that would slander the discipline we want."""
    db = _db(tmp_path, [
        ("2026-09-20", "", "", "", "", None, 0, 0, None, None),
        ("2026-09-21", "r1", "Ayr", "Somehorse", "h1", 2.0, 7, 1, 1, 2.0),
    ])
    rows = R.rows(db)
    assert [r["status"] for r in rows] == ["PASS", "WON"]
    s = R.summarise(rows)
    assert s["passes"] == 1 and s["settled"] == 1 and s["bets"] == 1
    assert round(s["pl"], 2) == 1.00        # the pass costs nothing and wins nothing


def test_a_pending_day_is_not_yet_a_result(tmp_path):
    """A banked but unsettled day is PENDING. Counting it as a loss would make
    every afternoon look like a defeat until the evening."""
    db = _db(tmp_path, [("2026-09-21", "r1", "Ayr", "Somehorse", "h1", 2.0, 7, 1, None, None)])
    s = R.summarise(R.rows(db))
    assert s["pending"] == 1 and s["settled"] == 0 and s["pl"] == 0.0


def test_the_favourite_benchmark_is_scored_on_the_same_races(tmp_path):
    """The SP-favourite is the bar to beat (his graduation bar, 2026-08-15).
    It is scored only where the ledger actually kept a favourite line, so a
    missing benchmark never flatters or damns us by silence."""
    db = _db(tmp_path,
             [("2026-09-05", "r1", "Thirsk", "Proposal", "h1", 3.0, 9, 1, 1, 3.0),
              ("2026-09-12", "r2", "Leop", "Constitution River", "h2", 2.5, 8, 1, 0, 2.38)],
             [("2026-09-05", "r1", "Thirsk", "TheJolly", "f1", 2.0, 0, 2.0),
              ("2026-09-12", "r2", "Leop", "Constitution River", "h2", 2.38, 0, 2.38)])
    s = R.summarise(R.rows(db))
    assert s["fav_settled"] == 2 and s["fav_wins"] == 0
    assert round(s["fav_pl"], 2) == -2.00        # both favourites beaten
    assert round(s["pl"], 2) == 1.00             # we beat the bar on these two


def test_a_winner_with_no_sp_returns_the_stake_and_is_never_guessed(tmp_path):
    """A win the ledger never priced must not invent a return. Stake back, no
    profit — an honest zero beats a plausible number."""
    db = _db(tmp_path, [("2026-09-21", "r1", "Ayr", "Somehorse", "h1", 5.0, 7, 1, 1, None)])
    s = R.summarise(R.rows(db))
    assert s["wins"] == 1 and s["pl"] == 0.0


def test_the_csv_round_trips_and_carries_the_engine_split(tmp_path):
    """v1 v v2 is the comparison the ladder runs on; the export must carry it
    so the repo can split the month without re-deriving the cutover date."""
    db = _db(tmp_path, [
        ("2026-09-01", "r0", "Bath", "Older", "h0", 4.0, 6, 0, 0, 4.0),
        ("2026-09-05", "r1", "Thirsk", "Proposal", "h1", 3.0, 9, 1, 1, 3.0),
    ])
    csv_p, md_p = tmp_path / "record.csv", tmp_path / "THE_RECORD.md"
    assert R.export(db, csv_p, md_p) == 2
    back = list(csv.DictReader(open(csv_p)))
    assert [r["engine"] for r in back] == ["v1", "v2"]
    assert back[1]["horse"] == "Proposal" and back[1]["status"] == "WON"
    body = md_p.read_text()
    assert "Proposal" in body and "strike" in body
    assert "Never edit this file" in body


def test_a_named_pass_is_not_a_win(tmp_path):
    """2026-09-23, the first night the record could be read. nap.db encodes
    `won` as 1 won / 0 lost / -1 named pass / -2 void. The first version of
    _status did `"WON" if row["won"] else "LOST"` — and -1 and -2 are TRUTHY,
    so all thirteen passes and all three voids were reported as WINS, turning
    a 29.0% strike rate into 43.6%. The instrument built to make the record
    honest was the thing lying about it."""
    db = _db(tmp_path, [
        ("2026-09-01", "r1", "Ayr", "Winner", "h1", 3.0, 9, 1, 1, 3.0),
        ("2026-09-02", "r2", "Ayr", "Loser", "h2", 3.0, 9, 1, 0, 3.0),
        ("2026-09-03", "", "", "NO BET", "", None, 0, 0, -1, None),
        ("2026-09-04", "r4", "Ayr", "Voided", "h4", 3.0, 9, 1, -2, None),
    ])
    rows = R.rows(db)
    assert [r["status"] for r in rows] == ["WON", "LOST", "PASS", "VOID"]
    s = R.summarise(rows)
    assert s["settled"] == 2 and s["wins"] == 1, "a pass or void is not a bet"
    assert s["strike"] == 50.0, "the pass must not dilute or inflate the strike"
    assert s["passes"] == 1 and s["voids"] == 1
    assert round(s["pl"], 2) == 1.00, "a pass risks nothing and returns nothing"


def test_the_engine_writes_NO_BET_not_a_blank_horse(tmp_path):
    """Belt and braces: a pass is caught by its won code OR by the horse text
    the engine actually writes, because the first version relied on a blank
    horse field that never occurs in practice."""
    db = _db(tmp_path, [("2026-09-03", "r1", "Ayr", "NO BET", "", None, 0, 0, 1, None)])
    assert R.rows(db)[0]["status"] == "PASS"
