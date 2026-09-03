"""Tests for the yardstick ledger (the master, 2026-09-03: bank the full read,
throw nothing away, let the record say which lenses lift the win rate above
the market — calculated and surgical, changes no pick, no rule)."""

from __future__ import annotations

from datetime import date

import pytest

from racing_edge.domain.models import Odds, Race, RaceResult, Runner, RunnerResult
from racing_edge.pipeline.nap import NapPick
from racing_edge.school import yardstick as ys
from racing_edge.selection.conviction import Conviction

# --------------------------------------------------------------------------- #
# lens_key
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tag, want", [
    ("finisher (1 strong finish(es) in comments)", "finisher"),
    ("local master yard (28% at this course, 67 runs — #10)", "local master yard"),
    ("raised 9lb since last win", "raised since last win"),
    ("RED-HOT — won its last two", "red-hot"),
    ("stable's #1 rider up (intent)", "stable's rider up"),
    ("jockey 0/25 at this course (#30)", "jockey at this course"),
    ("big-field lottery", "big-field lottery"),
    ("manner: out-battled/found little repeatedly — placer, not a nap (#1)",
     "manner"),
])
def test_lens_key_examples(tag, want) -> None:
    assert ys.lens_key(tag) == want


# --------------------------------------------------------------------------- #
# rows_from_field — two hand-built races, two runners each
# --------------------------------------------------------------------------- #
def _pick(race, runner, price, aligned=(), flags=(), cautions=(),
         mark_known=True, rq=0):
    c = Conviction(aligned=aligned, flags=flags, mark_known=mark_known,
                   cautions=cautions)
    return NapPick(race=race, runner=runner, price=price, conviction=c,
                   race_quality=rq)


def test_rows_from_field_two_races() -> None:
    rA = Runner(horse_id="A", horse="Alpha", odds=Odds(consensus=3.0))
    rB = Runner(horse_id="B", horse="Beta", odds=Odds(consensus=5.0))
    race1 = Race(race_id="r1", course="Cartmel", off_time="14:10",
                 date=date(2026, 9, 3), race_type="Handicap Chase",
                 is_handicap=True, race_class=4, runners=(rA, rB))
    pA = _pick(race1, rA, 3.0,
              aligned=("well-in (mark read: +5)",
                       "finisher (1 strong finish(es) in comments)"),
              rq=3)
    pB = _pick(race1, rB, 5.0, flags=("big-field lottery",),
              cautions=("raised 9lb since last win",), mark_known=False, rq=3)

    rC = Runner(horse_id="C", horse="Gamma", odds=Odds(consensus=2.0))
    rD = Runner(horse_id="D", horse="Delta", odds=Odds(consensus=8.0))
    race2 = Race(race_id="r2", course="Southwell", off_time="15:40",
                 date=date(2026, 9, 3), race_type="Hurdle", is_handicap=True,
                 race_class=5, runners=(rC, rD))
    pC = _pick(race2, rC, 2.0,
              aligned=("fair-priced favourite (#19 — the winner, not the price)",),
              rq=1)
    pD = _pick(race2, rD, 8.0, mark_known=False, rq=1)

    day = date(2026, 9, 3)                       # on/after V2_FROM -> v2
    rows = ys.rows_from_field(day, [pA, pB, pC, pD])
    assert len(rows) == 4
    by = {r["horse_id"]: r for r in rows}

    assert by["A"]["mkt_rank"] == 1 and by["B"]["mkt_rank"] == 2
    assert by["C"]["mkt_rank"] == 1 and by["D"]["mkt_rank"] == 2
    assert by["A"]["aligned"] == "well-in|finisher"
    assert by["B"]["flags"] == "big-field lottery"
    assert by["B"]["cautions"] == "raised since last win"
    assert by["A"]["code"] == "C"                # book_code("Handicap Chase")
    assert by["C"]["code"] == "H"                # book_code("Hurdle")
    assert by["A"]["version"] == "v2"
    assert by["A"]["field_size"] == 2
    assert by["A"]["race_quality"] == 3
    assert by["A"]["score"] == 2                 # mark + manner families
    assert by["A"]["confident"] == 0              # cautions/flags absent but score<3
    for r in rows:
        assert r["pos"] == r["sp_dec"] == r["won"] == ""


# --------------------------------------------------------------------------- #
# bank / load round trip
# --------------------------------------------------------------------------- #
def test_bank_then_load_round_trip(tmp_path) -> None:
    root = tmp_path / "yardstick"
    day = date(2026, 9, 3)
    rA = Runner(horse_id="A", horse="Alpha", odds=Odds(consensus=3.0))
    race = Race(race_id="r1", course="Cartmel", off_time="14:10", date=day,
                race_type="Chase", is_handicap=True, race_class=4,
                runners=(rA,))
    p = _pick(race, rA, 3.0, aligned=("well-in (foo)",), rq=2)

    path = ys.bank(day, [p], root=root)
    assert path == root / "2026-09-03.csv"
    assert path.exists()

    rows = ys.load(root)
    assert len(rows) == 1
    r = rows[0]
    assert r["horse_id"] == "A"
    assert r["price"] == 3.0
    assert r["score"] == 1                       # one family (mark)
    assert r["race_quality"] == 2
    assert r["won"] is None

    # OVERWRITE, not append — one morning, one file
    path2 = ys.bank(day, [p], root=root)
    assert path2 == path
    assert len(ys.load(root)) == 1


# --------------------------------------------------------------------------- #
# settle_day — mirrors cli/nap.py:_settle_tables (~line 379)
# --------------------------------------------------------------------------- #
def test_settle_day_marks_pos_sp_won_and_is_idempotent(tmp_path) -> None:
    root = tmp_path / "yardstick"
    day = date(2026, 9, 3)
    rA = Runner(horse_id="A", horse="Alpha", odds=Odds(consensus=3.0))
    rB = Runner(horse_id="B", horse="Beta", odds=Odds(consensus=5.0))
    rC = Runner(horse_id="C", horse="Gamma", odds=Odds(consensus=8.0))
    race = Race(race_id="r1", course="Cartmel", off_time="14:10", date=day,
                race_type="Chase", is_handicap=True, race_class=4,
                runners=(rA, rB, rC))
    picks = [_pick(race, rA, 3.0, rq=2), _pick(race, rB, 5.0, rq=2),
             _pick(race, rC, 8.0, rq=2)]
    ys.bank(day, picks, root=root)

    # A wins, B pulls up (ran, lost), C is absent from the result -> non-runner
    results = [RaceResult(race_id="r1", date=day, runners=(
        RunnerResult(horse_id="A", position=1, sp_dec=3.2),
        RunnerResult(horse_id="B", position=None, status="PU"),
    ))]
    n = ys.settle_day(day, results, root=root)
    assert n == 2                                # A and B settled; C unmeasured

    rows = {r["horse_id"]: r for r in ys.load(root)}
    assert rows["A"]["won"] == 1 and rows["A"]["sp_dec"] == 3.2 and rows["A"]["pos"] == 1
    assert rows["B"]["won"] == 0 and rows["B"]["pos"] == "PU"
    assert rows["C"]["won"] is None and rows["C"]["pos"] == ""

    # idempotent: re-settling with the same results changes nothing
    n2 = ys.settle_day(day, results, root=root)
    assert n2 == 2
    rows2 = {r["horse_id"]: r for r in ys.load(root)}
    assert rows2 == rows


# --------------------------------------------------------------------------- #
# scoreboard — hand-computed lift
# --------------------------------------------------------------------------- #
def _row(**kw):
    base = dict(date="2026-09-01", version="v2", race_id="r1", course="X",
                off_time="14:00", code="C", race_class=4, is_handicap=1,
                field_size=4, race_quality=2, horse_id="H", horse="Horse",
                mkt_rank=1, price=3.0, score=1, confident=0, mark_known=1,
                aligned="", flags="", cautions="", pos=1, sp_dec=3.0, won=1)
    base.update(kw)
    return base


def test_scoreboard_lift_math_by_hand() -> None:
    # rank 1: 2 runners, 1 win -> control 50%. rank 2: 2 runners, 0 wins -> 0%.
    # 'test-lens' rides the rank-1 winner and one rank-2 loser: n=2, wins=1,
    # expected = 0.5 + 0.0 = 0.5 -> lift = 100*(1-0.5)/2 = +25.0pp exactly.
    rows = [
        _row(horse_id="A", mkt_rank=1, won=1, aligned="test-lens"),
        _row(horse_id="B", mkt_rank=1, won=0, aligned=""),
        _row(horse_id="C", mkt_rank=2, won=0, aligned=""),
        _row(horse_id="D", mkt_rank=2, won=0, aligned="test-lens"),
    ]
    ctrl = ys._control(rows)
    assert ctrl[1] == (2, 1)
    assert ctrl[2] == (2, 0)

    rate = {k: (w / n if n else 0.0) for k, (n, w) in ctrl.items()}
    agg = ys._lens_table(rows, "aligned", rate)
    lens = agg["test-lens"]
    assert lens["n"] == 2
    assert lens["wins"] == 1
    assert lens["exp"] == pytest.approx(0.5)
    assert ys.tier0.lift_pp(lens) == pytest.approx(25.0)

    text = ys.scoreboard(rows)
    assert "test-lens" in text
    assert "+25.0" in text
    assert "50.0%" in text                       # the rank-1 control line


def test_scoreboard_race_bands_and_version() -> None:
    rows = [
        # a betting race (quality 2): fav (rank1) wins
        _row(race_id="rb", race_quality=2, horse_id="A", mkt_rank=1, won=1,
            score=2, version="v2"),
        _row(race_id="rb", race_quality=2, horse_id="B", mkt_rank=2, won=0,
            score=1, version="v2"),
        # below the bar (quality 0): rank-2 upsets the fav, our top score (B) loses
        _row(race_id="rd", race_quality=0, horse_id="C", mkt_rank=1, won=0,
            score=1, version="v1", sp_dec=4.0),
        _row(race_id="rd", race_quality=0, horse_id="D", mkt_rank=2, won=1,
            score=3, version="v1", sp_dec=6.0),
    ]
    bands = ys._race_bands(rows)
    assert bands["betting"]["n"] == 1
    assert bands["betting"]["fav_win"] == 1 and bands["betting"]["fav_n"] == 1
    assert bands["betting"]["top3_hit"] == 1
    assert bands["below"]["n"] == 1
    assert bands["below"]["fav_win"] == 0 and bands["below"]["fav_n"] == 1
    assert bands["below"]["pick_win"] == 1        # D scored highest (3) and won

    vt = ys._version_table(rows)
    assert vt["v2"]["n"] == 2 and vt["v2"]["wins"] == 1
    assert vt["v1"]["n"] == 2 and vt["v1"]["wins"] == 1
    assert vt["v1"]["pnl"] == pytest.approx((6.0 - 1.0) - 1.0)   # D wins @6.0, C loses


# --------------------------------------------------------------------------- #
# main — writes the .md
# --------------------------------------------------------------------------- #
def test_main_writes_markdown(tmp_path) -> None:
    root = tmp_path / "data" / "school" / "yardstick"
    day = date(2026, 9, 3)
    rA = Runner(horse_id="A", horse="Alpha", odds=Odds(consensus=3.0))
    race = Race(race_id="r1", course="Cartmel", off_time="14:10", date=day,
                race_type="Chase", is_handicap=True, race_class=4,
                runners=(rA,))
    p = _pick(race, rA, 3.0, rq=2)
    ys.bank(day, [p], root=root)

    rc = ys.main(["--root", str(root)])
    assert rc == 0
    out = root.parent / "yardstick.md"
    assert out.exists()
    text = out.read_text()
    assert "THE YARDSTICK" in text
    assert "doorbell" in text
