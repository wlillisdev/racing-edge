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


def test_daily_grader_scores_every_race_not_one_nap(tmp_path):
    # the master, 2026-08-15: "we keep saying wait 50 races to see, there
    # are 50 races every day" — the grader takes one pick per 5+ runner
    # race across the whole card.
    from racing_edge.school.daily import grade, pick_for
    from racing_edge.school.mine import featurise, load_corpus

    rows = []
    for i in range(3):  # three 5-runner races on one day
        rid = f"r{i}"
        rows += [_row("2026-03-02", rid, f"h{i}a", "2.0", "1"),
                 _row("2026-03-02", rid, f"h{i}b", "3.0", "2"),
                 _row("2026-03-02", rid, f"h{i}c", "5.0", "3"),
                 _row("2026-03-02", rid, f"h{i}d", "9.0", "4"),
                 _row("2026-03-02", rid, f"h{i}e", "17.0", "5")]
    scored = featurise(load_corpus(_corpus(tmp_path, rows)), "2026-03-01")
    by_race = {}
    for r in scored:
        by_race.setdefault(r.race_id, []).append(r)
    graded = grade({"2026-03-02": list(by_race.values())}, ["fav"])
    n, wins, ret = graded["fav"]["2026-03-02"]
    assert n == 3 and wins == 3 and ret == 6.0  # fav won all three at 2.0

    # cell policy skips races with no matching runner
    assert pick_for("cell:p11plus+mr1", list(by_race.values())[0]) is None


def test_ladder_change_tack_and_hold_and_silence_under_50():
    # the master, 2026-08-15: "if its failing, we evolve change tack, no
    # point in repeating something that is not working". His own bars rule:
    # under 50 picks no verdict; below the fav benchmark = CHANGE TACK.
    from racing_edge.school.ladder import verdict

    def days(policy, n_days, picks, wins, ret_per_day):
        return [(f"2026-03-{d + 1:02d}", picks, wins, ret_per_day)
                for d in range(n_days)]

    # under 50 picks: arithmetic, not evidence
    rows = {"fav": days("fav", 10, 10, 3, 9.0),
            "champ": days("champ", 2, 10, 3, 9.0)}
    assert verdict(rows, "champ").startswith("NO VERDICT")

    # champion below the benchmark: CHANGE TACK, challenger named
    rows = {"fav": days("fav", 10, 10, 3, 9.0),          # ROI -10%
            "champ": days("champ", 10, 10, 2, 6.0),      # ROI -40%
            "cell:x": days("cell:x", 10, 10, 4, 12.0)}   # ROI +20%
    v = verdict(rows, "champ")
    assert v.startswith("CHANGE TACK") and "cell:x" in v

    # champion beating benchmark, no qualifying challenger: HOLD
    rows = {"fav": days("fav", 10, 10, 3, 9.0),
            "champ": days("champ", 10, 10, 4, 11.0)}
    assert verdict(rows, "champ").startswith("HOLD")


def test_tight2_reads_direction_not_state(tmp_path):
    # the Gower Prince nuance (self-study 2026-08-15, PROPOSED): two
    # runner-up finishes with the margin tightening = progressive finisher.
    # A placer whose margins DRIFT must not get the flag.
    rows = [
        _row("2026-03-02", "r1", "h1", "3.0", "2", btn="4"),
        _row("2026-03-02", "r1", "hx", "2.0", "1"),
        _row("2026-03-12", "r2", "h1", "3.0", "2", btn="0.7"),
        _row("2026-03-12", "r2", "hy", "2.0", "1"),
        _row("2026-03-22", "r3", "h1", "3.0", "3", btn="1"),
        _row("2026-03-22", "r3", "hz", "2.0", "1"),
        # h2: margins drifting (0.5 then 6) — no flag
        _row("2026-03-02", "r4", "h2", "3.0", "2", btn="0.5"),
        _row("2026-03-02", "r4", "hp", "2.0", "1"),
        _row("2026-03-12", "r5", "h2", "3.0", "2", btn="6"),
        _row("2026-03-12", "r5", "hq", "2.0", "1"),
        _row("2026-03-22", "r6", "h2", "3.0", "4", btn="9"),
        _row("2026-03-22", "r6", "hr", "2.0", "1"),
    ]
    scored = featurise(load_corpus(_corpus(tmp_path, rows)), "2026-03-01")
    h1_last = next(r for r in scored if r.horse == "h1" and r.date == "2026-03-22")
    h2_last = next(r for r in scored if r.horse == "h2" and r.date == "2026-03-22")
    assert "tight2" in h1_last.feats
    assert "tight2" not in h2_last.feats


def test_night_school_policies_file_one_line_per_challenger(tmp_path):
    # adding a challenger is one line in policies.txt — no code, no credits
    from racing_edge.school.night import trial_policies

    assert trial_policies(tmp_path) == ["fav"]
    (tmp_path / "policies.txt").write_text(
        "# challengers on trial\ncell:tight2\n\nfav\ncell:mr1+ltowin\n")
    assert trial_policies(tmp_path) == ["fav", "cell:tight2", "cell:mr1+ltowin"]


def test_mark_calibration_shortlist2_and_wrong_twin(tmp_path):
    # the master, 2026-08-16: "you have the winner most of the time on the
    # short list and you just pick the wrong one" — so the mark separates
    # shortlist-2 hits from wrong-twin choices.
    import csv as _csv
    from racing_edge.school.mark import mark

    rows = [
        _row("2026-03-02", "r1", "w1", "3.0", "1"),  # winner
        _row("2026-03-02", "r1", "p1", "2.0", "2"),  # our pick (fav)
        _row("2026-03-02", "r1", "x1", "9.0", "3"),
        _row("2026-03-02", "r2", "p2", "2.0", "1"),  # our pick wins
        _row("2026-03-02", "r2", "d2", "4.0", "2"),
        _row("2026-03-02", "r2", "x2", "9.0", "3"),
    ]
    raw = _corpus(tmp_path, rows)
    keys = tmp_path / "keys.csv"
    with open(keys, "w", newline="") as fh:
        _csv.writer(fh).writerows(
            [["r1", "w1", "3.0", "p1"], ["r2", "p2", "2.0", "p2"]])
    picks = tmp_path / "picks.csv"
    with open(picks, "w", newline="") as fh:
        _csv.writer(fh).writerows([
            ["r1", "p1", "3", "fav respected", "w1"],  # danger won: wrong twin
            ["r2", "p2", "4", "clear form pick", "d2"],
        ])
    out = mark(picks, keys, raw)
    assert "shortlist-2 hit 2/2 (100.0%)" in out
    assert "wrong twin (danger won, we chose the other) = 1" in out
