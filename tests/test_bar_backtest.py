"""Pins for THE BAR BACKTEST: race_terms, bar_score, the leak-safe cumulative
shape vote, bucket/band arithmetic, and the render/main plumbing."""

from racing_edge.pipeline.nap import BETTING_BAR, race_quality_score
from racing_edge.school.bar_backtest import (
    backtest, bar_score, main, race_terms, render,
)
from racing_edge.school.mine import Runner


def _row(date, race_id, horse, sp, pos, course="Ascot", rclass="4",
         dist="8", jky="1", trn="1", region="G", rtype="F", btn="0"):
    return [date, race_id, course, region, rtype, rclass, dist,
            horse, sp, pos, btn, jky, trn]


# --------------------------------------------------------------------------- #
# race_terms
# --------------------------------------------------------------------------- #

def test_race_terms_basic_field():
    rows = [
        Runner(_row("2026-03-02", "r1", "h1", "2.0", "1", rclass="4")),
        Runner(_row("2026-03-02", "r1", "h2", "3.0", "2", rclass="4")),
        Runner(_row("2026-03-02", "r1", "h3", "9.0", "3", rclass="4")),
    ]
    t = race_terms(rows)
    assert t["field_size"] == 3
    assert t["class"] == 4
    assert t["code"] == "F"
    assert t["is_aw"] is False
    assert t["fav_sp"] == 2.0
    assert t["winner_rank"] == 1
    assert t["front3_pos"] == ("1", "2", "3")
    assert abs(t["concentration"] - (1 / 2.0 + 1 / 3.0 + 1 / 9.0)) < 1e-9


def test_race_terms_unclassed_is_none():
    rows = [
        Runner(_row("2026-03-02", "r1", "h1", "2.0", "1", rclass="0")),
        Runner(_row("2026-03-02", "r1", "h2", "3.0", "2", rclass="0")),
    ]
    assert race_terms(rows)["class"] is None


def test_race_terms_aw_course_is_case_insensitive_substring():
    rows = [
        Runner(_row("2026-03-02", "r1", "h1", "2.0", "1", course="Newcastle (AW)")),
        Runner(_row("2026-03-02", "r1", "h2", "3.0", "2", course="Newcastle (AW)")),
    ]
    assert race_terms(rows)["is_aw"] is True
    rows2 = [
        Runner(_row("2026-03-02", "r2", "h1", "2.0", "1", course="Ascot")),
        Runner(_row("2026-03-02", "r2", "h2", "3.0", "2", course="Ascot")),
    ]
    assert race_terms(rows2)["is_aw"] is False


def test_race_terms_unpriced_void_winner_has_no_rank():
    # winner's SP is 0 (void/unpriced) — never guess a market rank for it.
    rows = [
        Runner(_row("2026-03-02", "r1", "h1", "0", "1")),          # winner, unpriced
        Runner(_row("2026-03-02", "r1", "h2", "2.0", "2")),
        Runner(_row("2026-03-02", "r1", "h3", "4.0", "3")),
    ]
    t = race_terms(rows)
    assert t["field_size"] == 2               # only priced (sp>1.0) runners counted
    assert t["winner_rank"] is None
    assert t["front3_pos"] == ("2", "3")       # positions of the priced front runners


# --------------------------------------------------------------------------- #
# bar_score
# --------------------------------------------------------------------------- #

def test_bar_score_matches_race_quality_score_mapping():
    rows = [
        Runner(_row("2026-03-02", "r1", "h1", "2.0", "1", rclass="4")),
        Runner(_row("2026-03-02", "r1", "h2", "2.2", "2", rclass="4")),
        Runner(_row("2026-03-02", "r1", "h3", "2.4", "3", rclass="4")),
        Runner(_row("2026-03-02", "r1", "h4", "9.0", "4", rclass="4")),
    ]
    t = race_terms(rows)
    got = bar_score(t)
    expected = race_quality_score(
        is_handicap=False, concentration=t["concentration"], race_class=4,
        race_type="Flat", field_size=4, n_race_flags=0, is_aw=False,
        hollow=False, shape_verdict=None)
    assert got == expected
    # concentrated (1/2+1/2.2+1/2.4 > 0.75) Class-4 flat race: +1 conc, +1 class
    assert got == 2


def test_bar_score_hurdle_unclassed_big_field_is_penalised_and_code_mapped():
    rows = [Runner(_row("2026-03-02", "r1", f"h{i}", str(3.0 + i), "0",
                        rclass="0", rtype="H"))
            for i in range(14)]
    rows[0] = Runner(_row("2026-03-02", "r1", "h0", "3.0", "1", rclass="0", rtype="H"))
    t = race_terms(rows)
    assert t["code"] == "H"
    got = bar_score(t)
    expected = race_quality_score(
        is_handicap=False, concentration=t["concentration"], race_class=None,
        race_type="Hurdle", field_size=t["field_size"], n_race_flags=0,
        is_aw=False, hollow=False, shape_verdict=None)
    assert got == expected
    # hurdle (-1) + unclassed (-1) + field>=12 (-1) = -3, offset by the top-3
    # concentration bonus (+1: 1/3+1/4+1/5 = 0.783 > 0.75) = -2
    assert got == -2


def test_bar_score_shape_verdict_swings_the_score():
    rows = [
        Runner(_row("2026-03-02", "r1", "h1", "3.0", "1", rclass="3")),
        Runner(_row("2026-03-02", "r1", "h2", "5.0", "2", rclass="3")),
        Runner(_row("2026-03-02", "r1", "h3", "7.0", "3", rclass="3")),
    ]
    t = race_terms(rows)
    base = bar_score(t, None)
    assert bar_score(t, "GET ON THE JOLLY — the fav is a good thing") == base + 1
    assert bar_score(t, "BEST AVOIDED — lottery shape") == base - 2


# --------------------------------------------------------------------------- #
# backtest — hand-computed buckets on a tiny synthetic corpus
# --------------------------------------------------------------------------- #

def test_backtest_buckets_above_and_below_the_bar_by_hand():
    # Race A: concentrated Class-4 5-runner flat race, fav wins — clears the
    # bar (+1 conc, +1 class = score 2) with no shape vote available (first
    # month on record, cell empty).
    race_a = [
        Runner(_row("2026-01-05", "rA", "fav", "2.0", "1", rclass="4")),
        Runner(_row("2026-01-05", "rA", "h2", "2.2", "2", rclass="4")),
        Runner(_row("2026-01-05", "rA", "h3", "2.5", "3", rclass="4")),
        Runner(_row("2026-01-05", "rA", "h4", "9.0", "0", rclass="4")),
        Runner(_row("2026-01-05", "rA", "h5", "12.0", "0", rclass="4")),
    ]
    # Race B: unclassed hurdle, 14 runners, open market, outsider wins —
    # score -1(hurdle)-1(unclassed)-1(field>=12) = -3, well below the bar.
    race_b_rows = [Runner(_row("2026-01-06", "rB", f"h{i}", str(4.0 + i), "0",
                                rclass="0", rtype="H"))
                   for i in range(14)]
    race_b_rows[4] = Runner(_row("2026-01-06", "rB", "h4", str(4.0 + 4), "1",
                                  rclass="0", rtype="H"))  # rank-5 outsider wins
    race_b = race_b_rows

    result = backtest([race_a, race_b])
    assert result["n_races"] == 2

    above_all = result["above"]["ALL"]
    assert above_all["n"] == 1
    assert above_all["fav_strike"] == 100.0
    assert abs(above_all["fav_roi"] - 100.0) < 1e-9   # 2.0 SP fav wins level stake
    assert above_all["top3_cov"] == 100.0
    assert above_all["fav2_strike"] == 0.0
    assert above_all["fav3_strike"] == 0.0
    assert above_all["mean_field"] == 5

    below_all = result["below"]["ALL"]
    assert below_all["n"] == 1
    assert below_all["fav_strike"] == 0.0
    assert abs(below_all["fav_roi"] - (-100.0)) < 1e-9
    assert below_all["top3_cov"] == 0.0                # winner ranked 5th
    assert below_all["mean_field"] == 14

    # per-month rows exist alongside the ALL summary row
    assert "2026-01" in result["above"]
    assert "2026-01" in result["below"]

    # score bands: race A lands in band "2", race B in band "<=0"
    assert result["bands"]["2"]["n"] == 1
    assert result["bands"]["<=0"]["n"] == 1
    assert result["bands"]["1"]["n"] == 0
    assert result["bands"]["3+"]["n"] == 0


def test_backtest_shape_vote_is_leak_safe_across_months_not_within_them():
    # 30 January races of one shape (F, Cl3-4, 10 runners, fav ~3.0), fav
    # wins EVERY one -> once that cell holds n=30 it reads "GET ON THE
    # JOLLY". Each Jan race itself, though, is scored with NO vote (the
    # cell that judges it cannot yet include races from its own month).
    def _shape_race(date, rid, fav_wins, n=10):
        rows = [Runner(_row(date, rid, "hfav", "3.0",
                            "1" if fav_wins else "2", rclass="3"))]
        winner_used = fav_wins
        for i in range(1, n):
            sp = 3.0 + i * 2.0
            pos = "0"
            if not winner_used and i == 1:
                pos, winner_used = "1", True
            rows.append(Runner(_row(date, rid, f"h{i}", str(sp), pos, rclass="3")))
        return rows

    jan_races = [_shape_race(f"2026-01-{d:02d}", f"rJ{d}", fav_wins=True)
                 for d in range(1, 31)]
    # a same-shape February race where the fav does NOT win — isolates the
    # shape bonus from the fav-strike stat.
    feb_race = _shape_race("2026-02-01", "rF1", fav_wins=False)

    result = backtest(jan_races + [feb_race])

    # every January race: class(+1) only, concentration stays modest
    # (1/3 + 1/5 + 1/7 ~= 0.68, below the 0.75 bonus line) -> score 1,
    # and NO shape vote yet (its own cell isn't built until Feb starts).
    assert result["bands"]["1"]["n"] == 30

    # the February race: same terms score 1 on its own, +1 from the now-
    # built "GET ON THE JOLLY" cell (n=30 >= the 30-race gate) = 2, AT the
    # bar. It must be the sole occupant of the "above" bucket.
    above_rows_n = result["above"]["ALL"]["n"]
    below_rows_n = result["below"]["ALL"]["n"]
    assert above_rows_n + below_rows_n == 31
    assert above_rows_n == 1
    assert result["bands"]["2"]["n"] == 1

    # the Feb race's stats land correctly: fav lost (h1, rank2, won instead)
    feb_bucket = result["above"]["ALL"]
    assert feb_bucket["fav_strike"] == 0.0
    assert feb_bucket["top3_cov"] == 100.0     # winner still ranked 2nd
    assert feb_bucket["fav2_strike"] == 100.0  # the 2nd favourite won it


def test_backtest_empty_corpus():
    result = backtest([])
    assert result["n_races"] == 0
    assert result["above"]["ALL"]["n"] == 0
    assert result["below"]["ALL"]["n"] == 0
    for band in ("<=0", "1", "2", "3+"):
        assert result["bands"][band]["n"] == 0


# --------------------------------------------------------------------------- #
# render — the header must carry the stated caveats
# --------------------------------------------------------------------------- #

def test_render_states_the_corpus_limits():
    result = backtest([])
    text = render(result)
    assert "BETTING_BAR" in text or str(BETTING_BAR) in text
    assert "handicap flag" in text.lower()
    assert "07:30" in text
    assert "leak" in text.lower()
    assert "## What this says" in text
    assert "no new rule is proposed" in text


# --------------------------------------------------------------------------- #
# main — writes the report file
# --------------------------------------------------------------------------- #

def test_main_writes_report(tmp_path, capsys):
    raw = tmp_path / "raw"
    raw.mkdir()
    with open(raw / "2026-01-05.csv", "w", newline="") as fh:
        import csv
        csv.writer(fh).writerows([
            _row("2026-01-05", "rA", "fav", "2.0", "1", rclass="4"),
            _row("2026-01-05", "rA", "h2", "5.0", "2", rclass="4"),
        ])
    out = tmp_path / "report.md"
    rc = main(["--raw", str(raw), "--out", str(out)])
    assert rc == 0
    assert out.exists()
    text = out.read_text()
    assert "THE BAR BACKTEST" in text
    printed = capsys.readouterr().out
    assert "THE BAR BACKTEST" in printed
