"""
Tests for edge_tracker.py pure logic (no network/filesystem).

Run:
  RACING_API_USERNAME=x RACING_API_PASSWORD=x DB_HOST=x DB_NAME=x DB_USER=x \
  DB_PASS=x EMAIL_SENDER=x EMAIL_PASSWORD=x EMAIL_RECIPIENT=x \
  python test_edge_tracker.py
"""

import os

for _k in ("RACING_API_USERNAME", "RACING_API_PASSWORD", "DB_HOST", "DB_NAME",
           "DB_USER", "DB_PASS", "EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_k, "x")

from edge_tracker import _race_outcomes, _roi, _to_float

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


def runner(hid, pos, sp, horse=None):
    return {"horse_id": hid, "position": str(pos), "sp_dec": sp, "horse": horse or hid}


def t_favourite_is_min_sp():
    doc = {"results": [{"race_id": "R1", "runners": [
        runner("A", 3, 5.0), runner("B", 1, 2.5), runner("C", 2, 8.0)]}]}
    horse, fav = _race_outcomes(doc)
    assert fav["R1"]["horse_id"] == "B", fav["R1"]   # shortest price
    assert fav["R1"]["pos"] == 1                       # and it won
    assert horse["A"]["race_id"] == "R1"
    assert horse["C"]["sp"] == 8.0


def t_favourite_can_lose():
    doc = {"results": [{"race_id": "R1", "runners": [
        runner("A", 1, 6.0), runner("B", 4, 2.0)]}]}
    _, fav = _race_outcomes(doc)
    assert fav["R1"]["horse_id"] == "B"   # B is favourite (2.0)
    assert fav["R1"]["pos"] == 4           # but it lost


def t_roi_basic():
    # two picks: one won @4.0, one lost @3.0 -> P/L = (3) + (-1) = +2 over 2 = +100%
    rows = [{"sp": "4.0", "won": "1"}, {"sp": "3.0", "won": "0"}]
    n, win, roi = _roi(rows, "sp", "won")
    assert n == 2 and win == 50.0 and abs(roi - 100.0) < 1e-6, (n, win, roi)


def t_roi_all_losers():
    rows = [{"sp": "2.0", "won": "0"}, {"sp": "5.0", "won": "0"}]
    n, win, roi = _roi(rows, "sp", "won")
    assert win == 0.0 and roi == -100.0


def t_roi_skips_unpriced():
    rows = [{"sp": "", "won": "1"}, {"sp": "4.0", "won": "1"}]
    n, win, roi = _roi(rows, "sp", "won")
    assert n == 1 and roi == 300.0   # only the priced winner counts: (4-1)/1


def t_favourite_roi_over_same_rows():
    # method lost both; favourite won one of them -> favourite ROI better
    rows = [{"sp": "6.0", "won": "0", "fav_sp": "2.0", "fav_won": "1"},
            {"sp": "5.0", "won": "0", "fav_sp": "3.0", "fav_won": "0"}]
    _, _, mroi = _roi(rows, "sp", "won")
    _, _, froi = _roi(rows, "fav_sp", "fav_won")
    assert mroi == -100.0
    # fav: (2-1) + (-1) = 0 over 2 = 0%
    assert froi == 0.0
    assert froi > mroi   # favourite beat the method here


def t_to_float_guards():
    assert _to_float("4.5") == 4.5
    assert _to_float("1.0") is None   # <= 1 rejected
    assert _to_float("") is None
    assert _to_float(None) is None


def main():
    tests = [
        ("favourite = min SP", t_favourite_is_min_sp),
        ("favourite can lose", t_favourite_can_lose),
        ("ROI basic", t_roi_basic),
        ("ROI all losers", t_roi_all_losers),
        ("ROI skips unpriced", t_roi_skips_unpriced),
        ("favourite ROI vs method same rows", t_favourite_roi_over_same_rows),
        ("_to_float guards", t_to_float_guards),
    ]
    print("=" * 60)
    print("edge_tracker.py test suite")
    print("=" * 60)
    for name, fn in tests:
        check(name, fn)
    print("=" * 60)
    print(f"TOTAL: {_P + _F}   PASS: {_P}   FAIL: {_F}")
    print("=" * 60)
    return 0 if _F == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
