"""
Tests for loser_patterns.py pure logic (no network/filesystem).

Run:
  RACING_API_USERNAME=x RACING_API_PASSWORD=x DB_HOST=x DB_NAME=x DB_USER=x \
  DB_PASS=x EMAIL_SENDER=x EMAIL_PASSWORD=x EMAIL_RECIPIENT=x \
  python test_loser_patterns.py
"""

import os

for _k in ("RACING_API_USERNAME", "RACING_API_PASSWORD", "DB_HOST", "DB_NAME",
           "DB_USER", "DB_PASS", "EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_k, "x")

from loser_patterns import band_price, band_field, band_dist, seg_stats

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


def t_band_price():
    assert band_price(1.8) == "<=2.0 (odds-on)"
    assert band_price(2.0) == "<=2.0 (odds-on)"
    assert band_price(3.0) == "2.0-3.0"
    assert band_price(4.0) == "3.0-4.0"
    assert band_price(5.5) == "4.0-6.0"
    assert band_price(12.0) == "6.0+"
    assert band_price(None) == "?"


def t_band_field():
    assert band_field(5) == "small (<=7)"
    assert band_field(10) == "medium (8-12)"
    assert band_field(18) == "big (13+)"
    assert band_field(0) == "?"


def t_band_dist():
    assert band_dist(5.0) == "sprint (<=6f)"
    assert band_dist(8.0) == "mile (6-9.5f)"
    assert band_dist(10.0) == "middle (9.5-12f)"
    assert band_dist(16.0) == "staying (12f+)"
    assert band_dist(None) == "?"


def t_seg_stats_groups_and_roi():
    recs = [
        {"k": "A", "won": True, "sp": 3.0},    # +2
        {"k": "A", "won": False, "sp": 5.0},   # -1
        {"k": "B", "won": False, "sp": 2.0},   # -1
    ]
    rows = dict((b, (n, w, r)) for b, n, w, r in seg_stats(recs, "k"))
    # A: 2 picks, 50% win, P/L (2 -1)=+1 over 2 = +50%
    an, aw, ar = rows["A"]
    assert an == 2 and aw == 50.0 and abs(ar - 50.0) < 1e-6, rows["A"]
    # B: 1 pick, 0% win, -100%
    bn, bw, br = rows["B"]
    assert bn == 1 and bw == 0.0 and br == -100.0


def t_seg_stats_sorted_by_volume():
    recs = [{"k": "rare", "won": True, "sp": 2.0}] + \
           [{"k": "common", "won": False, "sp": 2.0} for _ in range(5)]
    rows = seg_stats(recs, "k")
    assert rows[0][0] == "common" and rows[0][1] == 5   # most-bet bucket first


def main():
    tests = [
        ("band_price", t_band_price),
        ("band_field", t_band_field),
        ("band_dist", t_band_dist),
        ("seg_stats groups + ROI", t_seg_stats_groups_and_roi),
        ("seg_stats sorted by volume", t_seg_stats_sorted_by_volume),
    ]
    print("=" * 56)
    print("loser_patterns.py test suite")
    print("=" * 56)
    for name, fn in tests:
        check(name, fn)
    print("=" * 56)
    print(f"TOTAL: {_P + _F}   PASS: {_P}   FAIL: {_F}")
    print("=" * 56)
    return 0 if _F == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
