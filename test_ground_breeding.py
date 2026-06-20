"""
Tests for ground_breeding_signal.py pure reads (no network/filesystem).

Run:
  RACING_API_USERNAME=x RACING_API_PASSWORD=x DB_HOST=x DB_NAME=x DB_USER=x \
  DB_PASS=x EMAIL_SENDER=x EMAIL_PASSWORD=x EMAIL_RECIPIENT=x \
  python test_ground_breeding.py
"""

import os

for _k in ("RACING_API_USERNAME", "RACING_API_PASSWORD", "DB_HOST", "DB_NAME",
           "DB_USER", "DB_PASS", "EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_k, "x")

from ground_breeding_signal import (
    going_band, _to_furlongs, _row_runs_wins,
    horse_ground_read, sire_ground_trip_read, ground_breeding_read,
)

_P = _F = 0
_FAILS = []


def check(name, fn):
    global _P, _F
    try:
        fn()
        print(f"PASS  {name}")
        _P += 1
    except AssertionError as e:
        print(f"FAIL  {name}: {e}")
        _F += 1
        _FAILS.append(name)


def run(d, pos="9"):
    return {"going": d, "position": pos}


# ---- going_band ----
def t_band():
    assert going_band("Heavy") == "heavy"
    assert going_band("Good To Soft") == "soft"
    assert going_band("good to firm") == "firm"
    assert going_band("Good") == "good"
    # 'heavy' is checked before 'soft', so this reads as the more testing band:
    assert going_band("Soft (Heavy in places)") == "heavy"
    assert going_band("Standard") == "aw"
    assert going_band("") == "unknown"


# ---- _to_furlongs ----
def t_furlongs():
    assert _to_furlongs({"dist_f": "6"}) == 6.0
    assert _to_furlongs({"dist_y": 1320}) == 6.0          # 1320/220
    assert _to_furlongs({"dist": "1m2f"}) == 10.0
    assert _to_furlongs({"dist": "5f"}) == 5.0
    assert _to_furlongs({}) is None


def t_row_runs_wins():
    assert _row_runs_wins({"runners": "50", "1st": "7"}) == (50, 7)
    assert _row_runs_wins({"runs": 30, "wins": 3}) == (30, 3)


# ---- horse_ground_read ----
def t_horse_proven_soft():
    runs = [run("Soft", "1"), run("Soft", "1"), run("Good", "4")]
    pts, reasons, data = horse_ground_read(runs, "soft")
    assert pts == 5.0, pts                       # 2 wins on soft
    assert data["on_band_wins"] == 2


def t_horse_one_win():
    runs = [run("Soft", "1"), run("Good", "3")]
    pts, _, _ = horse_ground_read(runs, "soft")
    assert pts == 4.0, pts


def t_horse_winless_wrong_ground():
    runs = [run("Heavy", "8"), run("Heavy", "6"), run("Heavy", "9"), run("Heavy", "7")]
    pts, reasons, _ = horse_ground_read(runs, "heavy")
    assert pts == -4.0, pts                       # 0/4, unplaced on the band
    assert "ground looks wrong" in reasons[0]


def t_horse_unproven_on_testing():
    # all wins on quick ground, today is heavy, no heavy runs
    runs = [run("Good", "1"), run("Firm", "1")]
    pts, _, _ = horse_ground_read(runs, "heavy")
    assert pts == -2.5, pts


def t_horse_unknown_band_neutral():
    pts, reasons, _ = horse_ground_read([run("Good", "1")], "unknown")
    assert pts == 0.0 and reasons == []


# ---- sire_ground_trip_read ----
def t_sire_strong():
    rows = [{"dist_f": "6", "runners": 100, "1st": 18}]   # 18% over 100, at trip
    pts, reasons, data = sire_ground_trip_read(rows, 6.0, "soft")
    assert pts == 3.0, pts
    assert data["sr"] == 18.0


def t_sire_weak():
    rows = [{"dist_f": "6", "runners": 120, "1st": 3}]    # 2.5% over 120
    pts, _, _ = sire_ground_trip_read(rows, 6.0, "soft")
    assert pts == -3.0, pts


def t_sire_small_sample_neutral():
    rows = [{"dist_f": "6", "runners": 8, "1st": 3}]      # tiny sample -> ignore
    pts, _, _ = sire_ground_trip_read(rows, 6.0, "soft")
    assert pts == 0.0, pts


def t_sire_trip_filter():
    # only the off-trip row is strong; at-trip row is weak -> should read the at-trip
    rows = [{"dist_f": "5", "runners": 100, "1st": 20},   # sprint, not today's trip
            {"dist_f": "12", "runners": 80, "1st": 2}]    # today ~12f, weak
    pts, _, _ = sire_ground_trip_read(rows, 12.0, "soft")
    assert pts == -3.0, pts


# ---- ground_breeding_read (combination) ----
def t_combo_exposed_leads_with_own_record():
    runner = {"horse_id": "H1", "horse": "Proven", "sire_id": "S1"}
    race = {"going_detailed": "Soft", "distance_f": 6.0, "course": "Ascot"}
    horse_runs = [run("Soft", "1"), run("Soft", "1"), run("Good", "5")]
    sire_rows = [{"dist_f": "6", "runners": 100, "1st": 2}]    # weak sire
    rd = ground_breeding_read(runner, race, horse_runs, sire_rows)
    # exposed (3 runs) with own band runs -> own record leads (+5), sire adds -3
    assert rd["ground_pts"] == 5.0, rd
    assert rd["verdict"] == "positive", rd


def t_combo_unexposed_leans_on_breeding():
    runner = {"horse_id": "H2", "horse": "Unexposed", "sire_id": "S2"}
    race = {"going_detailed": "Heavy", "distance_f": 16.0, "course": "Exeter"}
    horse_runs = [run("Good", "8")]                           # one run, none on today's heavy
    sire_rows = [{"dist_f": "16", "runners": 100, "1st": 18}]  # strong soft/heavy sire
    rd = ground_breeding_read(runner, race, horse_runs, sire_rows)
    # unexposed -> breeding weighted up (1.5x on 1 run): 3.0 * 1.5 = 4.5
    assert rd["breeding_pts"] == 4.5, rd
    assert rd["verdict"] == "positive", rd
    assert any("reading the breeding" in r for r in rd["reasons"])


def t_combo_no_data_neutral():
    runner = {"horse_id": "H3", "horse": "Nada", "sire_id": ""}
    race = {"going_detailed": "Good", "distance_f": 8.0}
    rd = ground_breeding_read(runner, race, [], [])
    assert rd["verdict"] == "neutral" and rd["data_ok"] is False


def main():
    tests = [
        ("going_band", t_band),
        ("_to_furlongs", t_furlongs),
        ("_row_runs_wins", t_row_runs_wins),
        ("horse proven on soft (+5)", t_horse_proven_soft),
        ("horse one win on band (+4)", t_horse_one_win),
        ("horse winless wrong ground (-4)", t_horse_winless_wrong_ground),
        ("horse unproven on testing (-2.5)", t_horse_unproven_on_testing),
        ("horse unknown band neutral", t_horse_unknown_band_neutral),
        ("sire strong (+3)", t_sire_strong),
        ("sire weak (-3)", t_sire_weak),
        ("sire small sample neutral", t_sire_small_sample_neutral),
        ("sire trip filter picks at-trip", t_sire_trip_filter),
        ("combo exposed -> own record leads", t_combo_exposed_leads_with_own_record),
        ("combo unexposed -> breeding leads", t_combo_unexposed_leans_on_breeding),
        ("combo no data -> neutral", t_combo_no_data_neutral),
    ]
    print("=" * 64)
    print("ground_breeding_signal.py test suite")
    print("=" * 64)
    for name, fn in tests:
        check(name, fn)
    print("=" * 64)
    print(f"TOTAL: {_P + _F}   PASS: {_P}   FAIL: {_F}")
    print("=" * 64)
    return 0 if _F == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
