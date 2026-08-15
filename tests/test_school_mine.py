"""Pins for the school miner: leakage guard, rank ties, ROI, stability."""
import csv
from pathlib import Path

from racing_edge.school.mine import (
    Cell, Runner, featurise, load_corpus, scan,
)


def _row(date, race_id, horse, sp, pos, course="Ripon", rclass="4",
         dist="8", jky="1", trn="1", region="G", rtype="F", btn="0"):
    return [date, race_id, course, region, rtype, rclass, dist,
            horse, sp, pos, btn, jky, trn]


def _corpus(tmp_path, rows):
    d = tmp_path / "raw"
    d.mkdir()
    by_date = {}
    for r in rows:
        by_date.setdefault(r[0], []).append(r)
    for date, rs in by_date.items():
        with open(d / f"{date}.csv", "w", newline="") as fh:
            csv.writer(fh).writerows(rs)
    return d


def test_market_rank_and_fav_benchmark(tmp_path):
    rows = [
        _row("2026-03-02", "r1", "h1", "2.0", "1"),
        _row("2026-03-02", "r1", "h2", "3.0", "2"),
        _row("2026-03-02", "r1", "h3", "9.0", "3"),
    ]
    races = load_corpus(_corpus(tmp_path, rows))
    scored = featurise(races, "2026-03-01")
    feats = {r.horse: r.feats for r in scored}
    assert "mr1" in feats["h1"] and "mr2" in feats["h2"] and "mr3" in feats["h3"]
    _, _, fav = scan(scored)
    assert fav.n == 1 and fav.wins == 1
    assert abs(fav.roi - 100.0) < 1e-9  # 2.0 SP winner = +100% at level stakes


def test_joint_favourites_only_one_gets_rank1(tmp_path):
    rows = [
        _row("2026-03-02", "r1", "hA", "2.5", "1"),
        _row("2026-03-02", "r1", "hB", "2.5", "2"),
    ]
    scored = featurise(load_corpus(_corpus(tmp_path, rows)), "2026-03-01")
    mr1s = [r.horse for r in scored if "mr1" in r.feats]
    assert len(mr1s) == 1


def test_leakage_guard_same_day_never_feeds_features(tmp_path):
    # h1 wins twice on the same day: the second win must NOT see the first
    # as "won last time out" (same-day results were not knowable at the off).
    rows = [
        _row("2026-03-02", "r1", "h1", "2.0", "1"),
        _row("2026-03-02", "r1", "h2", "3.0", "2"),
        _row("2026-03-02", "r2", "h1", "2.0", "1"),
        _row("2026-03-02", "r2", "h3", "3.0", "2"),
    ]
    scored = featurise(load_corpus(_corpus(tmp_path, rows)), "2026-03-01")
    assert all("ltowin" not in r.feats for r in scored)


def test_lto_and_class_move_use_prior_day(tmp_path):
    rows = [
        _row("2026-03-02", "r1", "h1", "2.0", "1", rclass="3"),
        _row("2026-03-02", "r1", "h2", "3.0", "2", rclass="3"),
        _row("2026-03-10", "r2", "h1", "2.0", "2", rclass="5"),
        _row("2026-03-10", "r2", "h3", "3.0", "1", rclass="5"),
    ]
    scored = featurise(load_corpus(_corpus(tmp_path, rows)), "2026-03-01")
    h1 = next(r for r in scored if r.horse == "h1" and r.date == "2026-03-10")
    assert "ltowin" in h1.feats          # won on the 2nd
    assert "dsl14" in h1.feats           # 8 days
    assert "clsdrop" in h1.feats         # class 3 -> class 5 is a drop
    h3 = next(r for r in scored if r.horse == "h3")
    assert "ltowin" not in h3.feats      # no history at all


def test_month_stability_flags_sign_flip():
    c = Cell()
    r_win = Runner(_row("2026-03-05", "r1", "h1", "3.0", "1"))
    r_lose = Runner(_row("2026-04-05", "r2", "h1", "3.0", "2"))
    c.add(r_win)   # March ROI +200%
    c.add(r_lose)  # April ROI -100%
    assert not c.stable()
    assert c.min_month_roi() == -100.0
