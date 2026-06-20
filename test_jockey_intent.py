"""
Tests for jockey_intent_signal.py pure reads (no network/filesystem).

Run:
  RACING_API_USERNAME=x RACING_API_PASSWORD=x DB_HOST=x DB_NAME=x DB_USER=x \
  DB_PASS=x EMAIL_SENDER=x EMAIL_PASSWORD=x EMAIL_RECIPIENT=x \
  python test_jockey_intent.py
"""

import os

for _k in ("RACING_API_USERNAME", "RACING_API_PASSWORD", "DB_HOST", "DB_NAME",
           "DB_USER", "DB_PASS", "EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_k, "x")

from jockey_intent_signal import (
    runner_price, combo_map, main_stable_jockeys, jockey_intent_read,
)

_P = _F = 0


def check(name, fn):
    global _P, _F
    try:
        fn()
        print(f"PASS  {name}")
        _P += 1
    except AssertionError as e:
        print(f"FAIL  {name}: {e}")
        _F += 1


def runner(hid, jid, tid, price, jockey="J", trainer="T"):
    return {"horse_id": hid, "jockey_id": jid, "trainer_id": tid,
            "jockey": jockey, "trainer": trainer,
            "odds": [{"decimal": str(price)}], "horse": hid}


# ---- combo_map / main_stable_jockeys ----
def t_combo_map_share():
    stats = [{"jockey_id": "A", "rides": 80, "1st": 16},
             {"jockey_id": "B", "rides": 20, "1st": 2}]
    cm = combo_map(stats)
    assert cm["A"]["sr"] == 20.0, cm["A"]
    assert cm["A"]["share"] == 0.8, cm["A"]


def t_main_jockey():
    cm = combo_map([{"jockey_id": "A", "rides": 80, "1st": 16},
                    {"jockey_id": "B", "rides": 20, "1st": 2}])
    assert main_stable_jockeys(cm) == {"A"}


def t_no_main_when_thin():
    cm = combo_map([{"jockey_id": "A", "rides": 10, "1st": 2},
                    {"jockey_id": "B", "rides": 9, "1st": 1}])
    assert main_stable_jockeys(cm) == set()       # top rides 10 < MAIN_MIN_RIDES


# ---- runner_price ----
def t_price_median():
    r = {"odds": [{"decimal": "5.0"}, {"decimal": "6.0"}, {"decimal": "7.0"}]}
    assert runner_price(r) == 6.0
    assert runner_price({"sp_dec": "4.5"}) == 4.5
    assert runner_price({}) is None


# ---- jockey_intent_read ----
def _yard_race(*runners):
    return {"course": "Naas", "off_time": "15:00", "runners": list(runners)}


def t_stable_jockey_on_second_string():
    # Trainer T1 runs two. Stable jockey A is on the LONGER one (the message).
    cm = combo_map([{"jockey_id": "A", "rides": 90, "1st": 20},
                    {"jockey_id": "B", "rides": 10, "1st": 1}])
    fav = runner("H_fav", "B", "T1", 2.5)          # market elect, lesser jockey
    second = runner("H_2nd", "A", "T1", 6.0)       # stable jockey, longer price
    race = _yard_race(fav, second)
    rd = jockey_intent_read(second, race, cm)
    assert rd["pts"] >= 4.0, rd                     # +4 intent (combo not >=18% so no combo bonus)
    assert rd["verdict"] == "positive", rd
    assert any("quietly fancied" in r for r in rd["reasons"])


def t_lesser_of_yard_negative():
    # The favourite is ridden by the lesser jockey while stable jockey is elsewhere.
    cm = combo_map([{"jockey_id": "A", "rides": 90, "1st": 20},
                    {"jockey_id": "B", "rides": 10, "1st": 1}])
    fav = runner("H_fav", "B", "T1", 2.5)
    second = runner("H_2nd", "A", "T1", 6.0)
    race = _yard_race(fav, second)
    rd = jockey_intent_read(fav, race, cm)
    assert rd["pts"] <= -2.0, rd
    assert rd["verdict"] in ("negative", "neutral")  # -2 alone is neutral; check sign
    assert rd["pts"] == -2.0, rd


def t_hot_combo_single_runner():
    # Single yard runner; jockey is a hot combo (>=18% over >=15) -> +2 (neutral verdict).
    cm = combo_map([{"jockey_id": "A", "rides": 50, "1st": 12}])   # 24%
    only = runner("H1", "A", "T1", 4.0)
    race = _yard_race(only)
    rd = jockey_intent_read(only, race, cm)
    assert rd["pts"] == 2.0, rd
    assert rd["verdict"] == "neutral", rd


def t_intent_plus_hot_combo_stacks():
    # Stable jockey on the longer one AND a hot combo -> +4 +2 = +6.
    cm = combo_map([{"jockey_id": "A", "rides": 90, "1st": 27},   # 30%
                    {"jockey_id": "B", "rides": 10, "1st": 1}])
    fav = runner("H_fav", "B", "T1", 2.5)
    second = runner("H_2nd", "A", "T1", 6.0)
    race = _yard_race(fav, second)
    rd = jockey_intent_read(second, race, cm)
    assert rd["pts"] == 6.0, rd
    assert rd["verdict"] == "positive", rd


def t_no_data_neutral():
    rd = jockey_intent_read(runner("H1", "A", "T1", 4.0), _yard_race(runner("H1", "A", "T1", 4.0)), {})
    assert rd["verdict"] == "neutral" and rd["data_ok"] is False


def t_single_runner_no_intent():
    # Stable jockey but the yard only has ONE runner -> no intent signal (no elect to defy).
    cm = combo_map([{"jockey_id": "A", "rides": 90, "1st": 9}])   # 10%, not hot
    only = runner("H1", "A", "T1", 4.0)
    rd = jockey_intent_read(only, _yard_race(only), cm)
    assert rd["pts"] == 0.0, rd


def main():
    tests = [
        ("combo_map share/sr", t_combo_map_share),
        ("main stable jockey", t_main_jockey),
        ("no main when thin", t_no_main_when_thin),
        ("runner_price median", t_price_median),
        ("stable jockey on second string (+4)", t_stable_jockey_on_second_string),
        ("lesser of yard (-2)", t_lesser_of_yard_negative),
        ("hot combo single runner (+2)", t_hot_combo_single_runner),
        ("intent + hot combo stacks (+6)", t_intent_plus_hot_combo_stacks),
        ("no data neutral", t_no_data_neutral),
        ("single runner -> no intent", t_single_runner_no_intent),
    ]
    print("=" * 64)
    print("jockey_intent_signal.py test suite")
    print("=" * 64)
    for name, fn in tests:
        check(name, fn)
    print("=" * 64)
    print(f"TOTAL: {_P + _F}   PASS: {_P}   FAIL: {_F}")
    print("=" * 64)
    return 0 if _F == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
