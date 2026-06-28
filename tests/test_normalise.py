"""Tests for the raw-JSON -> contract normalisers, against fixture API shapes.

The point the audit hammered: results need a real normaliser, and jumps
non-finisher codes (F/PU/UR) must not crash int(position). Run: pytest or
`python tests/test_normalise.py`.
"""

from __future__ import annotations

import sys
from datetime import date

from racing_edge.data.normalise import (
    past_runs_from_raw,
    race_from_raw,
    racecards_from_raw,
    results_from_raw,
    runner_from_raw,
)

_RAW_RUNNER = {
    "horse_id": "hrs_1", "horse": "Bishopton", "trainer": "N Richards",
    "trainer_id": "trn_1", "jockey": "S Mulqueen", "jockey_id": "jck_1",
    "claim": "5", "age": "8", "sex": "g", "lbs": "152", "ofr": "138", "rpr": "150",
    "form": "21F31", "last_run": "28", "headgear": "b", "headgear_run": "1",
    "wind_surgery": "", "draw": "", "sire": "Kayf Tara", "sire_id": "sir_1",
    "odds": [{"decimal": "4.0"}, {"decimal": "4.5"}, {"decimal": "3.5"}],
}

_RAW_RACE = {
    "race_id": "rac_1", "course": "Kelso", "off_time": "14:40",
    "race_name": "Handicap Chase", "type": "Chase", "class": "3",
    "distance_f": "20.0", "going": "Soft", "region": "GB",
    "runners": [_RAW_RUNNER],
}


def test_runner_normalise() -> None:
    r = runner_from_raw(_RAW_RUNNER)
    assert r.horse_id == "hrs_1" and r.horse == "Bishopton"
    assert r.weight_lbs == 152 and r.official_rating == 138 and r.rpr == 150
    assert r.claim_lbs == 5
    assert r.headgear == "b" and r.headgear_first_time is True
    assert r.odds.consensus == 4.5     # best (max) of 3.5/4.0/4.5 — the price taken


def test_race_normalise() -> None:
    race = race_from_raw(_RAW_RACE, date(2026, 1, 15))
    assert race.code == "jump"          # Chase
    assert race.is_handicap is True
    assert race.race_class == 3
    assert race.going_band == "soft"
    assert race.season == "nh_winter"
    assert race.field_size == 1


def test_racecards_doc_key_tolerance() -> None:
    # tolerate both "racecards" and "races" (the audit's mismatched-key bug)
    assert len(racecards_from_raw({"racecards": [{**_RAW_RACE, "date": "2026-01-15"}]})) == 1
    assert len(racecards_from_raw({"races": [{**_RAW_RACE, "date": "2026-01-15"}]})) == 1


def test_results_normalise_with_nonfinishers() -> None:
    doc = {"results": [{"race_id": "rac_1", "date": "2026-01-15", "runners": [
        {"horse_id": "A", "position": "1", "sp_dec": "2.5"},
        {"horse_id": "B", "position": "F", "sp_dec": "6.0"},      # faller — must not crash
        {"horse_id": "C", "position": "PU", "sp": "11.0"},        # pulled up
        {"horse_id": "D", "position": "3", "sp_dec": "4.0", "btn": "2.5"},
    ]}]}
    results = results_from_raw(doc)
    assert len(results) == 1
    res = results[0]
    a, b, c, d = (res.of(x) for x in ("A", "B", "C", "D"))
    assert a is not None and a.won is True
    assert b is not None and b.position is None and b.status == "F" and b.won is False
    assert c is not None and c.status == "PU"
    assert d is not None and d.placed(3) is True and d.beaten_lengths == 2.5
    assert res.favourite is not None and res.favourite.horse_id == "A"   # shortest SP


def test_results_normalise_captures_name_and_comment() -> None:
    doc = {"results": [{"race_id": "rac_1", "date": "2026-01-15", "runners": [
        {"horse_id": "A", "horse": "Front Runner", "position": "2", "sp_dec": "3.0",
         "comment": "led, headed final 100yds, no extra"},
    ]}]}
    a = results_from_raw(doc)[0].of("A")
    assert a is not None and a.horse == "Front Runner"
    assert a.comment == "led, headed final 100yds, no extra"   # for the study to read the finish


def test_past_runs_normalise() -> None:
    rows = [
        {"date": "2025-12-01", "position": "1", "class": "2", "going": "Heavy",
         "dist_f": "24.0", "lbs": "158", "course": "Ayr", "type": "Chase", "ran": "10"},
        {"date": "2025-11-01", "position": "U", "class": "3", "going": "Soft"},  # unseated
    ]
    runs = past_runs_from_raw(rows)
    assert len(runs) == 2
    assert runs[0].won is True and runs[0].race_class == 2 and runs[0].field_size == 10
    assert runs[1].position is None and runs[1].won is False


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
