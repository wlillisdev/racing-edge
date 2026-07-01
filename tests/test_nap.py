"""Tests for conviction, the nap nominator, and the nap log (the n=1 cure)."""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.domain.models import Odds, PastRun, Race, Runner
from racing_edge.pipeline.nap import evaluate_field, nominate_nap
from racing_edge.selection.conviction import conviction
from racing_edge.study.naplog import NapLog


def _race(**kw):
    return Race(race_id="r", course="Cartmel", off_time="15:50", date=date(2026, 6, 27),
                race_type="Handicap Chase", is_handicap=True, distance_f=25.0, going="Good", **kw)


def _won_cdg(d, orr):
    return PastRun(date=d, position=1, course="Cartmel", going="Good", distance_f=25.0,
                   official_rating=orr)


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
                 "dist_f": "25.0",
                 "runners": [{"horse_id": "GEM", "position": "1", "or": "120"}]},
                {"date": "2026-04-01", "race_id": "p2", "course": "Cartmel", "going": "Good",
                 "dist_f": "25.0",
                 "runners": [{"horse_id": "GEM", "position": "1", "or": "116"}]},
            ]
        return []

    def trainer_jockeys(self, tid: str) -> list[dict]:
        return []


def test_nominate_nap_picks_the_conviction_horse_not_the_short_fav() -> None:
    nap = nominate_nap(_Client(), day="today", codes=("jump",))
    assert nap is not None
    assert nap.runner.horse == "Gem"          # the well-in proven horse, not the 2.0 fav
    assert nap.conviction.confident


def test_evaluate_field_returns_every_contender_strongest_first() -> None:
    # rule #24: no horse skipped — both runners evaluated, the conviction horse on top
    field = evaluate_field(_Client(), day="today", codes=("jump",))
    assert {p.runner.horse for p in field} == {"Gem", "Shorty"}   # the WHOLE field, not just pick
    assert field[0].runner.horse == "Gem"                         # strongest first
    nap = nominate_nap(_Client(), day="today", codes=("jump",))
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
