"""Tests for conviction, the nap nominator, and the nap log (the n=1 cure)."""

from __future__ import annotations

import sys
from datetime import date, datetime

from racing_edge.domain.models import Odds, PastRun, Race, Runner
from racing_edge.pipeline.nap import evaluate_field, nominate_nap
from racing_edge.selection.conviction import conviction
from racing_edge.study.naplog import NapLog

MORNING = datetime(2026, 7, 13, 8, 0)   # fixed clock: fixture races are 'still to run'.


def _race(**kw):
    return Race(race_id="r", course="Cartmel", off_time="15:50", date=date(2026, 6, 27),
                race_type="Handicap Chase", is_handicap=True, distance_f=25.0, going="Good", **kw)


def _won_cdg(d, orr, rtype="Chase"):
    # the live feed always carries the run's type; the sacred mark gate refuses a
    # blank-typed win as its anchor (a fantasy well-in is worse than an OWED one)
    return PastRun(date=d, position=1, course="Cartmel", going="Good", distance_f=25.0,
                   official_rating=orr, race_type=rtype)


def test_conviction_rewards_the_well_in_proven_horse() -> None:
    # well-in, repeat course winner, 2nd fav -> confident
    r = Runner(horse_id="w", horse="Gem", official_rating=120, odds=Odds(consensus=3.0))
    c = conviction(r, _race(), (_won_cdg(date(2026, 5, 1), 120), _won_cdg(date(2026, 4, 1), 116)),
                   market_rank=2, field_size=8)
    assert c.mark_known and c.confident and c.score >= 3
    assert any("well-in" in a for a in c.aligned)


def test_conviction_flags_the_improver_favourite() -> None:
    # lightly raced, market leader, short price -> the Loch Cuan / Who's Lope flag, NOT confident
    r = Runner(horse_id="i", horse="Improver", official_rating=83, odds=Odds(consensus=2.0))
    c = conviction(r, _race(), (PastRun(date=date(2026, 5, 1), position=1),),
                   market_rank=1, field_size=8)
    assert not c.confident
    assert any("improver-favourite" in f for f in c.flags)


def test_conviction_reads_the_manner_from_history_comments() -> None:
    """Rule #1 finally wired to live data: the comments now on PastRun feed nap_verdict.
    A repeated out-battled profile FLAGS (placer, not a nap); a finisher aligns."""
    r = Runner(horse_id="w", horse="Gem", official_rating=120, odds=Odds(consensus=3.0))
    placer_hist = (
        PastRun(date=date(2026, 6, 1), position=2, official_rating=120,
                comment="every chance, found little"),
        PastRun(date=date(2026, 5, 1), position=2, comment="one paced final furlong"),
        PastRun(date=date(2026, 4, 1), position=1, official_rating=120),
    )
    c = conviction(r, _race(), placer_hist, market_rank=2, field_size=8)
    assert any("placer, not a nap" in f for f in c.flags)
    assert not c.confident                                   # flagged -> never confident

    finisher_hist = (
        PastRun(date=date(2026, 6, 1), position=1, official_rating=120,
                comment="stayed on strongly to lead near the line"),
        PastRun(date=date(2026, 5, 1), position=1, official_rating=116,
                comment="quickened clear, readily"),
    )
    c2 = conviction(r, _race(), finisher_hist, market_rank=2, field_size=8)
    assert any("finisher" in a for a in c2.aligned)


def test_the_im_next_lesson_fair_fav_with_intent_outranks_bare_sweet_spot() -> None:
    """2026-07-03: the engine napped a filly (well-in + 2nd fav) while I'm Next
    (well-in + course depth + in-form yard + stable's #1 up, fair-priced FAV) and
    Giant Haystacks (well-in -9) won elsewhere on the card — favourites earned no
    market lens (#19 missing), -9lb scored like 0lb, intent couldn't score at all."""
    race = _race()
    im_next = Runner(horse_id="IN", horse="ImNext", official_rating=86,
                     jockey_id="J1", odds=Odds(consensus=3.1))
    hist = (_won_cdg(date(2026, 6, 1), 86), _won_cdg(date(2026, 4, 1), 82),
            PastRun(date=date(2026, 3, 1), position=3, official_rating=84))
    c = conviction(im_next, race, hist, market_rank=1, field_size=8,
                   stable_strike=0.17, yard_no1=True)
    assert any("#19" in a for a in c.aligned)            # fair-priced fav now credited
    assert any("in-form yard" in a for a in c.aligned)
    assert any("#1 rider" in a for a in c.aligned)
    # the bare filly profile: well-in + sweet spot only
    filly = Runner(horse_id="F", horse="Filly", official_rating=58,
                   odds=Odds(consensus=3.6))
    cf = conviction(filly, race, (PastRun(date=date(2026, 6, 1), position=1,
                                          official_rating=58),),
                    market_rank=2, field_size=5)
    assert c.score > cf.score                            # the jigsaw now outranks it

    # the magnitude shows inside the verdict but mints NO second label (the master,
    # 2026-07-26: 'the well-in claim is skewing all your picks — ONE piece of the
    # jigsaw'; the old 'heavily treated' label was the bigger-gap-better magnet)
    gh = Runner(horse_id="GH", horse="GiantHaystacks", official_rating=95,
                odds=Odds(consensus=4.4))
    cg = conviction(gh, race, (_won_cdg(date(2026, 5, 1), 104),),
                    market_rank=1, field_size=8)
    assert any("-9lb" in a for a in cg.aligned)           # the delta stays visible
    assert not any("heavily treated" in a for a in cg.aligned)
    assert any("#19" in a for a in cg.aligned)
    # a CRAMPED fav still earns nothing — #19 is about fair prices, not all favs
    cramped = conviction(im_next, race, hist, market_rank=1, field_size=8)
    short = Runner(horse_id="S", horse="Shorty", official_rating=86,
                   odds=Odds(consensus=1.8))
    cs = conviction(short, race, hist, market_rank=1, field_size=8)
    assert not any("#19" in a for a in cs.aligned)
    assert any("#19" in a for a in cramped.aligned)      # 3.1 is fair


class _RaceClient:
    """One configurable race for gate tests."""

    def __init__(self, race_class="4", prices=("3.0", "4.0"), field_pad=0):
        self._cls, self._prices, self._pad = race_class, prices, field_pad

    def racecards(self, day="today"):
        runners = [{"horse_id": f"H{i}", "horse": f"Horse{i}", "age": "7", "ofr": "70",
                    "odds": [{"decimal": p}]} for i, p in enumerate(self._prices)]
        runners += [{"horse_id": f"P{i}", "horse": f"Pad{i}", "age": "7", "ofr": "60"}
                    for i in range(self._pad)]
        return {"racecards": [{"race_id": "R1", "course": "Thirsk", "off_time": "3:00",
                               "date": "2026-07-05", "race_name": "Handicap",
                               "type": "Flat", "class": self._cls, "runners": runners}]}

    def horse_results(self, hid, limit=12):
        return [{"date": f"2026-0{m}-01", "runners": [
            {"horse_id": hid, "position": str(pos), "or": "70"}]}
            for m, pos in ((6, 2), (5, 1), (4, 3), (3, 5), (2, 4), (1, 6))]

    def trainer_jockeys(self, tid):
        return []


def test_race_selection_gates_bottom_grade_and_open_market() -> None:
    """2026-07-05, the master after two poor naps: 'really bad race selections —
    unexposed horses, poor classes, anything could win.' Cl6 flat is flagged; a race
    whose own market can't find an anchor (fav 5.0+) is flagged as a lottery."""
    cl6 = evaluate_field(_RaceClient(race_class="6"), day="today", codes=("flat",), now=MORNING)
    assert cl6 and all(any("bottom-grade" in f for f in p.conviction.flags) for p in cl6)

    open_mkt = evaluate_field(_RaceClient(race_class="4", prices=("5.5", "6.0", "7.0")),
                              day="today", codes=("flat",), now=MORNING)
    assert open_mkt
    assert all(any("anything-could-win" in f for f in p.conviction.flags)
               for p in open_mkt)

    clean = evaluate_field(_RaceClient(race_class="3", prices=("3.0", "4.0")),
                           day="today", codes=("flat",), now=MORNING)
    assert clean and all(not p.conviction.flags for p in clean)   # readable race passes


def test_equal_reads_prefer_the_better_class_race() -> None:
    """The ranking was blind to race quality — a Cl6 scramble outranked a Cl3 on
    price alone. Between equal convictions, the better-class race wins the nap."""
    from racing_edge.pipeline.nap import _rank_key
    r3 = Race(race_id="a", course="X", off_time="2:00", date=date(2026, 7, 5),
              race_type="Flat", is_handicap=True, race_class=3)
    r6 = Race(race_id="b", course="Y", off_time="3:00", date=date(2026, 7, 5),
              race_type="Flat", is_handicap=True, race_class=6)
    from racing_edge.selection.conviction import Conviction
    c = Conviction(aligned=("well-in x", "course winner", "sweet"), flags=(),
                   mark_known=True)
    from racing_edge.pipeline.nap import NapPick
    p3 = NapPick(race=r3, runner=Runner(horse_id="a", horse="A"), price=4.0, conviction=c)
    p6 = NapPick(race=r6, runner=Runner(horse_id="b", horse="B"), price=3.0, conviction=c)
    assert _rank_key(p3) > _rank_key(p6)      # Cl3 beats Cl6 despite the shorter price


def test_every_paid_lens_scores_local_master_trip_and_course_jockey() -> None:
    """The every-endpoint audit (2026-07-09): trainer-course (#10), distance-times
    (the trip lens), jockey-course (#30) — paid for, never called. Pins that all
    three now score, because the first attempt silently landed nowhere."""
    r = Runner(horse_id="w", horse="Gem", official_rating=120, odds=Odds(consensus=3.0))
    hist = (_won_cdg(date(2026, 5, 1), 120),)
    c = conviction(r, _race(), hist, market_rank=2, field_size=8,
                   local_strike=0.22, local_runs=14,
                   trip_strike=0.30, trip_runs=6,
                   jockey_course_strike=0.17, jockey_course_rides=20)
    assert any("local master yard" in a for a in c.aligned)
    assert any("trip proven" in a for a in c.aligned)
    assert any("course jockey" in a for a in c.aligned)
    # the quiet inverse: a rider 0-from-many here is a flag, not a cross-off
    c2 = conviction(r, _race(), hist, market_rank=2, field_size=8,
                    jockey_course_strike=0.0, jockey_course_rides=30)
    assert any("0/30 at this course" in f for f in c2.flags)
    # thin samples stay silent — no lens fires off 3 runs
    c3 = conviction(r, _race(), hist, market_rank=2, field_size=8,
                    local_strike=0.5, local_runs=3, trip_strike=0.5, trip_runs=2)
    assert not any("local master" in a or "trip proven" in a for a in c3.aligned)


def test_field_of_young_unexposed_horses_is_flagged_a_novice_in_disguise() -> None:
    """Chepstow 17:10 (2026-07-03): the race TITLE passed the #13 gate but the field
    was young unexposed fillies — the form book didn't apply and the nap lost. When
    half+ of the live contenders are <=4yo with <=4 runs, every pick gets flagged."""
    class _YoungClient:
        def racecards(self, day="today"):
            return {"racecards": [{
                "race_id": "R1", "course": "Chepstow", "off_time": "17:10",
                "date": "2026-07-03", "race_name": "Fillies Handicap", "type": "Flat",
                "class": "5", "runners": [
                    {"horse_id": "A", "horse": "Baby One", "age": "4", "ofr": "74",
                     "odds": [{"decimal": "2.25"}]},
                    {"horse_id": "B", "horse": "Baby Two", "age": "4", "ofr": "58",
                     "odds": [{"decimal": "3.5"}]},
                ]}]}

        def horse_results(self, hid, limit=12):
            return [{"date": "2026-06-01", "runners": [
                {"horse_id": hid, "position": "1", "or": "70"}]}]   # one run each

        def trainer_jockeys(self, tid):
            return []

    field = evaluate_field(_YoungClient(), day="today", codes=("flat",), now=MORNING)
    assert field
    assert all(any("novice in disguise" in f for f in p.conviction.flags) for p in field)
    assert nominate_nap(_YoungClient(), day="today", codes=("flat",), now=MORNING) is None  # no bet


def test_marks_never_cross_codes() -> None:
    """Caught BY THE DEEP READ mid-pass (2026-07-21): a flat 61 compared against a
    hurdles win off 107 produced a fantasy 'WELL-IN -46lb'. Flat and jumps marks are
    different currencies — with the code given, only same-code wins count."""
    from racing_edge.domain.mark import mark_read
    hist = (
        PastRun(date=date(2026, 6, 1), position=1, official_rating=107,
                race_type="Hurdle"),
        PastRun(date=date(2026, 4, 1), position=2, official_rating=63,
                race_type="Flat"),
    )
    assert mark_read(61, hist).delta == -46            # codeless: the old fantasy
    assert mark_read(61, hist, code="flat").delta is None   # honest: no FLAT win
    flat_hist = (PastRun(date=date(2026, 5, 1), position=1, official_rating=59,
                         race_type="Flat"),) + hist
    assert mark_read(61, flat_hist, code="flat").delta == 2  # real flat comparison


def test_conviction_needs_the_mark_to_be_confident() -> None:
    # everything aligns but the OR isn't on the card -> mark unknown -> never confident
    r = Runner(horse_id="w", horse="Gem", odds=Odds(consensus=3.0))   # no official_rating
    hist = (_won_cdg(date(2026, 5, 1), 120), _won_cdg(date(2026, 4, 1), 116))
    c = conviction(r, _race(), hist, market_rank=2, field_size=8)
    assert not c.mark_known and not c.confident


class _Client:
    def racecards(self, day: str = "today") -> dict:
        return {"racecards": [{
            "race_id": "R1", "course": "Cartmel", "off_time": "15:50", "date": "2026-06-27",
            "race_name": "Handicap Chase", "type": "Chase", "class": "4",
            "distance_f": "25.0", "going": "Good", "runners": [
                {"horse_id": "GEM", "horse": "Gem", "ofr": "120", "odds": [{"decimal": "3.0"}]},
                {"horse_id": "FAV", "horse": "Shorty", "ofr": "118", "odds": [{"decimal": "2.0"}]},
            ]}]}

    def horse_results(self, hid: str, limit: int = 12) -> list[dict]:
        if hid == "GEM":   # well-in repeat course winner
            return [
                {"date": "2026-05-01", "race_id": "p1", "course": "Cartmel", "going": "Good",
                 "dist_f": "25.0", "type": "Chase",
                 "runners": [{"horse_id": "GEM", "position": "1", "or": "120"}]},
                {"date": "2026-04-01", "race_id": "p2", "course": "Cartmel", "going": "Good",
                 "dist_f": "25.0", "type": "Chase",
                 "runners": [{"horse_id": "GEM", "position": "1", "or": "116"}]},
            ]
        return []

    def trainer_jockeys(self, tid: str) -> list[dict]:
        return []


def test_nominate_nap_picks_the_conviction_horse_not_the_short_fav() -> None:
    nap = nominate_nap(_Client(), day="today", codes=("jump",), now=MORNING)
    assert nap is not None
    assert nap.runner.horse == "Gem"          # the well-in proven horse, not the 2.0 fav
    assert nap.conviction.confident


def test_evaluate_field_returns_every_contender_strongest_first() -> None:
    # rule #24: no horse skipped — both runners evaluated, the conviction horse on top
    field = evaluate_field(_Client(), day="today", codes=("jump",), now=MORNING)
    assert {p.runner.horse for p in field} == {"Gem", "Shorty"}   # the WHOLE field, not just pick
    assert field[0].runner.horse == "Gem"                         # strongest first
    nap = nominate_nap(_Client(), day="today", codes=("jump",), now=MORNING)
    assert nap.runner.horse == field[0].runner.horse             # the nap is the top of the field


def test_nap_log_accumulates_a_strike_rate() -> None:
    log = NapLog(":memory:")
    log.record(day=date(2026, 6, 27), race_id="R1", course="York", horse="Hallo Spaceboy",
               horse_id="h", price=3.0, score=3, confident=True)
    log.settle(date(2026, 6, 27), won=True, sp_dec=3.0)
    log.record(day=date(2026, 6, 28), race_id="R2", course="Cartmel", horse="Other",
               horse_id="o", price=2.5, score=2, confident=False)
    log.settle(date(2026, 6, 28), won=False, sp_dec=2.5)
    assert log.strike_rate() == (1, 2)               # 1 of 2 naps won
    assert log.strike_rate(confident_only=True) == (1, 1)   # the confident one won
    log.close()


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())


def test_settle_can_see_every_name_it_calls() -> None:
    """2026-07-22..24: open_nuance_log was imported inside main() only, so _settle
    raised NameError at 22:00 three nights straight — naps settled, then the crash
    killed the night before the self-study, starving the nuance ledger (and the
    flight recorder's broken trap logged EXIT 0 over it). Every name _settle's code
    references must resolve at module scope."""
    import racing_edge.cli.nap as napcli
    for name in ("open_nap_log", "open_nuance_log", "resolve_date",
                 "results_from_raw", "get_client"):
        assert hasattr(napcli, name), f"cli.nap missing module-level name: {name}"


def test_the_woodstock_lesson_stale_anchor_and_serial_placer_flag() -> None:
    """2026-07-25 adversarial audit: Woodstock read 'WELL-IN -7lb' against a win
    older than its entire visible history — an exposed loser's mark erodes BECAUSE
    it keeps losing, and 0 wins in 10 visible runs is a placer profile at win odds.
    Both now flag; a flagged horse is never confident and never a clean survivor."""
    r = Runner(horse_id="w", horse="Woodstock", official_rating=68,
               odds=Odds(consensus=4.9))
    losses = tuple(PastRun(date=date(2026, 7, 1 + i), position=2 + (i % 4),
                           race_type="Flat") for i in range(10))
    old_win = (PastRun(date=date(2025, 6, 1), position=1, official_rating=75,
                       race_type="Flat"),)
    race = Race(race_id="r", course="Cartmel", off_time="15:50",
                date=date(2026, 6, 27), race_type="Flat", is_handicap=True)
    c = conviction(r, race, losses + old_win, market_rank=2, field_size=8)
    assert any("STALE" in f for f in c.flags)            # anchor from a dead era
    assert any("placer risk" in f for f in c.flags)
    assert not c.confident
    # a fresh winner is untouched: won 2 runs back, no stale/placer noise
    fresh = (PastRun(date=date(2026, 7, 10), position=3, race_type="Flat"),
             PastRun(date=date(2026, 7, 1), position=1, official_rating=68,
                     race_type="Flat"))
    c2 = conviction(r, race, fresh, market_rank=2, field_size=8)
    assert not any("STALE" in f or "placer risk" in f for f in c2.flags)


def test_led_and_caught_reads_as_the_nearly_type() -> None:
    from racing_edge.domain.manner import read_manner
    m, _ = read_manner("driven to the front with a furlong out - overtaken "
                       "inside the final 110 yards by the winner")
    assert m == "non_finisher"                            # the Woodstock comment
    m2, _ = read_manner("made headway over 2f out and stayed on well")
    assert m2 == "finisher"                               # 'headway' is not 'headed'


def test_rank_key_weights_the_decisive_lens() -> None:
    """2026-07-25 audit: a mark-OWED conv-4 outranked well-in conv-3 horses,
    wasting candidate slots on picks the sacred floor can never bank."""
    from racing_edge.pipeline.nap import _rank_key
    race = Race(race_id="r", course="Cartmel", off_time="15:50",
                date=date(2026, 6, 27), race_type="Flat", is_handicap=True,
                race_class=4)
    well_in = Runner(horse_id="a", horse="WellIn", official_rating=70,
                     odds=Odds(consensus=4.0))
    wh = (PastRun(date=date(2026, 7, 10), position=4, race_type="Flat"),
          PastRun(date=date(2026, 7, 1), position=1, official_rating=72,
                  course="Thirsk", race_type="Flat"))
    cw = conviction(well_in, race, wh, market_rank=2, field_size=8)
    owed = Runner(horse_id="b", horse="MarkOwed", odds=Odds(consensus=3.0))
    hist = (PastRun(date=date(2026, 7, 10), position=1, race_type="Flat"),)
    co = conviction(owed, race, hist, market_rank=2, field_size=8,
                    stable_strike=0.2, yard_no1=True,
                    jockey_course_strike=0.2, jockey_course_rides=30)
    assert not co.mark_known and co.score > cw.score      # the audited shape
    from racing_edge.pipeline.nap import NapPick
    pw = NapPick(race=race, runner=well_in, price=4.0, conviction=cw)
    po = NapPick(race=race, runner=owed, price=3.0, conviction=co)
    assert _rank_key(pw) > _rank_key(po)                  # well-in outranks anyway


def test_stale_anchor_counts_same_code_runs_only() -> None:
    """2026-07-25 adversarial review: `since` was the raw index over the mixed-code
    history, so a summer-flat/winter-jumps horse that WON its last flat start read
    'STALE — 10 runs back' off its intervening hurdles runs and was crossed off."""
    race = Race(race_id="r", course="Cartmel", off_time="15:50",
                date=date(2026, 6, 27), race_type="Flat", is_handicap=True)
    r = Runner(horse_id="d", horse="DualCode", official_rating=70,
               odds=Odds(consensus=4.0))
    jumps = tuple(PastRun(date=date(2026, 6, 1 + i), position=3,
                          race_type="Hurdle") for i in range(10))
    flat_win = (PastRun(date=date(2026, 5, 1), position=1, official_rating=72,
                        race_type="Flat"),)
    c = conviction(r, race, jumps + flat_win, market_rank=2, field_size=8)
    assert any("well-in" in a for a in c.aligned)
    assert not c.stale_anchor            # its LAST FLAT START was the win — fresh


def test_the_dial_in_gauges_pnl_and_lens_attribution() -> None:
    """2026-07-25, the master: 'first consistency, now picking winners.' You can't
    tune what you don't measure: the ledger now carries level-stakes P/L at SP and
    per-lens win/loss attribution, so knobs turn on evidence, not on last week's mood."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        log = NapLog(Path(d) / "nap.db")
        log.record(day=date(2026, 7, 1), race_id="r1", course="York", horse="A",
                   horse_id="a", price=4.0, score=4, confident=True,
                   aligned="well-in (WELL-IN -5lb) | market sweet spot (2nd/3rd fav)")
        log.settle(date(2026, 7, 1), won=True, sp_dec=4.0)
        log.record(day=date(2026, 7, 2), race_id="r2", course="Ayr", horse="B",
                   horse_id="b", price=3.0, score=3, confident=False,
                   aligned="well-in (WELL-IN -2lb) | fair-priced favourite (#19)")
        log.settle(date(2026, 7, 2), won=False, sp_dec=3.1)
        log.record_pass(day=date(2026, 7, 3), reason="discipline")   # never counted
        pnl, n = log.profit_loss()
        assert n == 2 and abs(pnl - 2.0) < 1e-9        # +3.0 win, -1.0 loss
        attr = {a["lens"]: (a["wins"], a["losses"]) for a in log.lens_attribution()}
        assert attr["well-in"] == (1, 1)               # rides both — no signal yet
        assert attr["market sweet spot"] == (1, 0)
        assert attr["fair-priced favourite"] == (0, 1)
        log.close()


def test_favline_banks_and_settles_beside_the_nap(tmp_path):
    # the master, 2026-08-16: "ok lets do favourite and value bet, what have
    # we got to lose the information is there" — the market's pick banks
    # beside ours and settles into its own record line.
    from datetime import date as _date

    from racing_edge.study.naplog import NapLog

    log = NapLog(tmp_path / "nap.db")
    d = _date(2026, 8, 17)
    log.record_favline(day=d, race_id="r1", course="Ripon",
                       horse="Steady Eddie", horse_id="h9", price=2.5)
    assert log.pending_favline()[0]["horse"] == "Steady Eddie"
    log.settle_favline(d, won=True, sp_dec=2.5)
    wins, settled, pnl = log.favline_record()
    assert (wins, settled) == (1, 1)
    assert abs(pnl - 1.5) < 1e-9          # 2.5 SP winner = +1.5pt level stakes
    log.settle_favline(d, won=True, sp_dec=2.5)  # idempotent on the day
    assert log.favline_record()[1] == 1
    log.close()


def test_well_in_is_a_rough_guide_without_current_form_behind_it() -> None:
    # the master, 2026-08-17: "we base everything on well in? why... the
    # well in has proven only a rough guide and has not been reliable"
    # (his 2026-07-26 law: it counts only with current form and manner).
    # A fresh well-in with NO corroborating form/manner lens must not score.
    r = Runner(horse_id="u", horse="MarkOnly", official_rating=110,
               odds=Odds(consensus=5.0))
    hist = (
        PastRun(date=date(2026, 6, 1), position=4, official_rating=112,
                race_type="Chase"),
        PastRun(date=date(2026, 5, 1), position=5, official_rating=114,
                race_type="Chase"),
        _won_cdg(date(2026, 4, 1), 114),   # won 3 back off a HIGHER mark
    )
    c = conviction(r, _race(), hist, market_rank=4, field_size=8)
    assert not any("well-in" in a for a in c.aligned)
    assert any("rough guide only" in f for f in c.flags)

    # the same mark WITH a last-time-out win behind it still counts
    hist_form = (_won_cdg(date(2026, 6, 1), 110),
                 PastRun(date=date(2026, 5, 1), position=3,
                         official_rating=112, race_type="Chase"),
                 _won_cdg(date(2026, 4, 1), 114))
    c2 = conviction(r, _race(), hist_form, market_rank=4, field_size=8)
    assert any("well-in" in a for a in c2.aligned)


def test_race_first_ranking_readable_handicap_beats_seductive_horse() -> None:
    # the master, 2026-08-17: "one of the big problems is picking the right
    # race i think this is a weak point in the system" — the race outranks
    # the horse: a solid pick in a clean handicap beats a stronger-scored
    # horse standing in a flagged or non-handicap race.
    from racing_edge.pipeline.nap import NapPick, _rank_key
    from racing_edge.selection.conviction import Conviction

    STRONG = ("won last time out", "course winner", "in-form yard (20%)",
              "market sweet spot (2nd/3rd fav)", "trip proven (30%)")
    MODEST = ("won last time out", "in-form yard (18%)")

    def pick(rq, aligned):
        c = Conviction(aligned=aligned, flags=(), mark_known=True)
        r = Runner(horse_id=f"h{rq}{len(aligned)}", horse="X", official_rating=80,
                   odds=Odds(consensus=4.0))
        return NapPick(race=_race(), runner=r, price=4.0, conviction=c,
                       race_quality=rq)

    clean_handicap_modest = pick(rq=1, aligned=MODEST)
    flagged_race_star = pick(rq=-1, aligned=STRONG)
    nonhandicap_star = pick(rq=0, aligned=STRONG)
    ranked = sorted([flagged_race_star, clean_handicap_modest, nonhandicap_star],
                    key=_rank_key, reverse=True)
    assert ranked[0] is clean_handicap_modest
    # within the SAME race quality, the better horse still wins
    clean_handicap_star = pick(rq=1, aligned=STRONG)
    ranked2 = sorted([clean_handicap_modest, clean_handicap_star],
                     key=_rank_key, reverse=True)
    assert ranked2[0] is clean_handicap_star


def test_race_quality_score_carries_the_fingerprint_study() -> None:
    # the master, 2026-08-17: "we need to give ourself the best chance of
    # winning consistently and if you think the above is the right way and
    # type of race lets go" — every term receipted by the 1,978-race study.
    from racing_edge.pipeline.nap import race_quality_score

    # the dream betting race: concentrated Cl4 handicap chase, 8 runners
    best = race_quality_score(is_handicap=True, concentration=0.8,
                              race_class=4, race_type="Handicap Chase",
                              field_size=8, n_race_flags=0)
    assert best == 3
    # the walk-past: unclassed open-market hurdle, 14 runners, flagged
    worst = race_quality_score(is_handicap=False, concentration=0.4,
                               race_class=None, race_type="Maiden Hurdle",
                               field_size=14, n_race_flags=1)
    assert worst == -4
    # concentration is the strongest single signal — it alone separates
    mid_locked = race_quality_score(is_handicap=True, concentration=0.8,
                                    race_class=5, race_type="Handicap",
                                    field_size=9, n_race_flags=0)
    mid_open = race_quality_score(is_handicap=True, concentration=0.5,
                                  race_class=5, race_type="Handicap",
                                  field_size=9, n_race_flags=0)
    assert mid_locked > mid_open


def test_terrible_race_lesson_aw_penalty_and_hollow_concentration() -> None:
    # the master, 2026-08-19, after Percy's Lad ran 5th: "for the record
    # that was a terrible race to pick in wolverhampton." Two teeth: AW
    # costs a point (taught #14, receipted: concentrated AW top-3 71.9% vs
    # 79.9% turf), and concentration earned by dead wood counts for nothing.
    from racing_edge.pipeline.nap import race_quality_score

    base = dict(is_handicap=True, concentration=0.8, race_class=4,
                race_type="Handicap", field_size=9, n_race_flags=0)
    turf_quality = race_quality_score(**base)
    aw_same = race_quality_score(**base, is_aw=True)
    aw_hollow = race_quality_score(**base, is_aw=True, hollow=True)
    assert turf_quality == 3
    assert aw_same == 2          # the surface taxes a point
    assert aw_hollow == 1        # hollow field forfeits the conc bonus too
    # yesterday's Wolves 6:30 under the corrected score: AW + hollow = +1,
    # no longer the automatic race of the day


def test_raised_lb_is_a_caution_not_a_cross_off() -> None:
    """THE OPPOSITE (the master, 2026-08-22: 'just do the opposite and see how
    it goes... dont go all nuclear on the system'). 'Raised N lb since last
    win' had no master quote and no receipts (RULE_AUDIT row); it crossed Too
    Much Trevor, who won at 10/1, and on 2026-08-22 it was the sole cross-off
    on dozens of horses — erasing the day's best race. Demoted: it now WARNS
    (a caution the case must answer) and never ERASES — flags stay clean so
    the horse survives, but confidence stays blocked. REVERT-IF: a week of
    marked mornings reads worse than the week before this shipped."""
    r = Runner(horse_id="t", horse="Too Much Trevor", official_rating=80,
               odds=Odds(consensus=6.0))
    hist = (PastRun(date=date(2026, 8, 1), position=1, official_rating=75,
                    race_type="Flat"),
            PastRun(date=date(2026, 7, 10), position=3, race_type="Flat"))
    race = Race(race_id="r", course="Ripon", off_time="14:10",
                date=date(2026, 8, 22), race_type="Flat", is_handicap=True)
    c = conviction(r, race, hist, market_rank=3, field_size=8)
    assert any("raised" in x for x in c.cautions)      # the warning rides along
    assert not any("raised" in f for f in c.flags)     # but it no longer erases
    assert not c.confident                             # a raised horse is never a nap
