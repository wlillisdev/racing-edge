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
                aligned="", flags="", cautions="", pos=1, sp_dec=3.0, won=1,
                signposts="", best_class="no line", class_level=99, pattern="",
                distance_f=6.0)
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
# THE SHADOW LADDER — variant keys graded off the banked rows (2026-09-05:
# "do all the testing on the shadow"). Measured, never crowned.
# --------------------------------------------------------------------------- #
def _abc(c_flags: str = "big-field lottery") -> list[dict]:
    # A: no class line but the strongest jigsaw and the shortest price
    # B: a Listed line (rung 4), a weak jigsaw, a long price
    # C: a Group 2 line (rung 2), the best score — but carries a flag
    return [
        _row(race_id="r1", horse_id="A", mkt_rank=1, price=2.5, score=4,
             confident=1, class_level=99, won=0),
        _row(race_id="r1", horse_id="B", mkt_rank=3, price=8.0, score=1,
             confident=0, class_level=4, won=1, sp_dec=9.0),
        _row(race_id="r1", horse_id="C", mkt_rank=2, price=3.0, score=5,
             confident=1, class_level=2, flags=c_flags, won=0),
    ]


def test_shadow_pick_mirrors_the_live_key_and_crosses_off_flags() -> None:
    rows = _abc()
    assert ys.shadow_pick(rows, "key-class")["horse_id"] == "B"   # class first
    assert ys.shadow_pick(rows, "key-old")["horse_id"] == "A"     # the jigsaw
    for k in ("key-old", "key-class", "key-class-noflag"):
        assert ys.shadow_pick(rows, k)["horse_id"] != "C"         # flagged
    assert ys.shadow_pick(rows, "fav")["horse_id"] == "A"
    # fails with the crossed_off filter deleted: C's Group 2 line would win
    assert ys.crossed_off(rows[2]) and not ys.crossed_off(rows[1])


def test_shadow_keeps_the_improver_favourite_only_for_the_noflag_variant() -> None:
    rows = _abc(c_flags="improver-favourite")
    assert ys.shadow_pick(rows, "key-class")["horse_id"] == "B"
    assert ys.shadow_pick(rows, "key-class-noflag")["horse_id"] == "C"
    rows = _abc(c_flags="improver-favourite|big-field lottery")
    assert ys.shadow_pick(rows, "key-class")["horse_id"] == "B"
    assert ys.shadow_pick(rows, "key-class-noflag")["horse_id"] == "B"


def test_shadow_grades_only_settled_races_and_voids_a_non_runner_pick() -> None:
    rows = _abc()
    # r2: no settled winner among the rows -> graded by nobody
    rows += [_row(race_id="r2", horse_id="D", mkt_rank=1, won=None),
             _row(race_id="r2", horse_id="E", mkt_rank=2, won=None)]
    # r3: the favourite (key-old's pick) is a non-runner -> key-old and fav
    # void the race; key-class still picks the Listed-line horse G
    rows += [_row(race_id="r3", horse_id="F", mkt_rank=1, price=2.0, score=4,
                  confident=1, class_level=99, won=None, sp_dec=None),
             _row(race_id="r3", horse_id="G", mkt_rank=2, price=4.0, score=1,
                  class_level=4, won=1, sp_dec=4.5)]
    by = {p: (n, w, ret) for _d, p, n, w, ret in ys.shadow_day_rows(rows)}
    assert by["shadow:key-class"] == (2, 2, 9.0 + 4.5)
    assert by["shadow:key-old"] == (1, 0, 0.0)        # r3 voided (F a non-runner)
    assert by["shadow:fav"] == (1, 0, 0.0)
    assert "shadow:key-class-pattern" not in by       # a Cl4 handicap: no row


def test_shadow_pattern_variant_grades_only_pattern_and_heritage_races() -> None:
    rows = _abc()                                                  # Cl4 hcp
    rows += [_row(race_id="rp", horse_id="P", mkt_rank=1, price=2.0, score=2,
                  class_level=3, pattern="Group 3", won=1, sp_dec=3.0),
             _row(race_id="rp", horse_id="Q", mkt_rank=2, price=5.0, score=1,
                  class_level=99, pattern="Group 3", won=0)]
    rows += [_row(race_id="rh", horse_id="H1", mkt_rank=1, price=3.0, score=1,
                  class_level=6, race_class=2, won=0),
             _row(race_id="rh", horse_id="H2", mkt_rank=2, price=6.0, score=3,
                  class_level=5, race_class=2, won=1, sp_dec=7.0)]
    by = {p: (n, w, ret) for _d, p, n, w, ret in ys.shadow_day_rows(rows)}
    assert by["shadow:key-class-pattern"] == (2, 2, 3.0 + 7.0)   # rp + rh only
    assert by["shadow:key-class"][0] == 3                          # all three


def test_shadow_rows_are_namespaced_and_idempotent(tmp_path) -> None:
    rows = _abc()
    csvp = tmp_path / "daily_policy.csv"
    written, skipped = ys.grade_shadow(rows, csvp)
    assert written > 0 and skipped == 0
    first = csvp.read_bytes()
    assert ys.grade_shadow(rows, csvp) == (0, written)
    assert csvp.read_bytes() == first
    policies = [ln.split(",")[1] for ln in csvp.read_text().splitlines()[1:]]
    assert policies and all(p.startswith("shadow:") for p in policies)
    table = ys.shadow_table(rows)
    assert "SHADOW LADDER" in table and "PROVISIONAL until 500" in table
    assert "shadow:key-class: picks=1 strike=100.0% ROI=+800.0%" in table


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
    ys.settle_day(day, [RaceResult(race_id="r1", date=day, runners=(
        RunnerResult(horse_id="A", position=1, sp_dec=3.2),))], root=root)

    rc = ys.main(["--root", str(root)])
    assert rc == 0
    out = root.parent / "yardstick.md"
    assert out.exists()
    text = out.read_text()
    assert "THE YARDSTICK" in text
    assert "doorbell" in text
    # the shadow ladder grades the same night, into the ledger BESIDE the root
    # (never the repo's own daily_policy.csv when --root is a tmp dir)
    pol = root.parent / "daily_policy.csv"
    assert pol.exists()
    assert ",shadow:fav," in pol.read_text()
