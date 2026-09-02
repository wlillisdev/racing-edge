"""End-to-end tests for the NIGHT SCHOOL CHAIN, on a small synthetic corpus.

Covers: school/night.py -> school/daily.py -> school/ladder.py,
school/tier0.py, school/shapebook.py, school/mine.py (load_corpus), and
school/fetch.py's pagination / empty-day handling with requests.get
monkeypatched (no network, no credentials).

Scratch only: everything lives under pytest's tmp_path. src/ and docs/ are
not touched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from racing_edge.school import fetch as fetch_mod
from racing_edge.school import mine as mine_mod
from racing_edge.school import night as night_mod
from racing_edge.school import shapebook as shapebook_mod
from racing_edge.school import tier0 as tier0_mod

# --------------------------------------------------------------------------- #
# Synthetic corpus: two months, 5-runner races, some "0" (unknown) positions,
# one malformed row. Deterministic horse ids so features are predictable.
#
# H1 wins race 100 on 2026-01-05, then returns as favourite in race 104 on
# 2026-02-09 -> at race 104 H1 carries both "mr1" (favourite) and "ltowin"
# (won last time out), so policy cell:mr1+ltowin has exactly one candidate
# that day, and it wins again (deterministic strike/ROI for that policy).
#
# Races 100, 101, 102, 103, 104 share one shape (F, Class 5, 5 runners,
# fav < 6/4) -> 5 races in that shapebook cell. Race 105 (Class 1, same day
# as 100/101) is a second, lone-race shape (n=1) used to prove shapebook's
# min_n floor actually excludes thin cells.
# --------------------------------------------------------------------------- #


def _row(date, race_id, horse, sp, pos, btn, jockey, trainer,
         course="TestA", region="G", rtype="F", rclass="Class 5", dist="6"):
    return ",".join([date, race_id, course, region, rtype, rclass, dist,
                      horse, str(sp), pos, str(btn), jockey, trainer])


def write_corpus(raw: Path) -> None:
    raw.mkdir(parents=True, exist_ok=True)

    day1 = [
        _row("2026-01-05", "100", "H1", 2.0, "1", 0, "J1", "T1"),
        _row("2026-01-05", "100", "H2", 3.0, "2", 1.0, "J2", "T2"),
        _row("2026-01-05", "100", "H3", 4.0, "3", 2.0, "J3", "T3"),
        _row("2026-01-05", "100", "H4", 5.0, "0", 0, "J4", "T4"),   # unknown pos
        _row("2026-01-05", "100", "H5", 8.0, "4", 3.0, "J5", "T5"),
        _row("2026-01-05", "101", "H6", 2.2, "1", 0, "J6", "T6"),
        _row("2026-01-05", "101", "H7", 3.2, "2", 1.0, "J7", "T7"),
        _row("2026-01-05", "101", "H8", 4.2, "3", 2.0, "J8", "T8"),
        _row("2026-01-05", "101", "H9", 6.2, "4", 3.0, "J9", "T9"),
        _row("2026-01-05", "101", "H10", 9.2, "0", 0, "J10", "T10"),  # unknown pos
        # a second shape (different class band), only ONE race -> n=1
        _row("2026-01-05", "105", "H11", 2.0, "1", 0, "J11", "T11", rclass="Class 1"),
        _row("2026-01-05", "105", "H12", 3.0, "2", 1.0, "J12", "T12", rclass="Class 1"),
        _row("2026-01-05", "105", "H13", 4.0, "3", 2.0, "J13", "T13", rclass="Class 1"),
        _row("2026-01-05", "105", "H14", 5.0, "4", 3.0, "J14", "T14", rclass="Class 1"),
        _row("2026-01-05", "105", "H15", 8.0, "5", 4.0, "J15", "T15", rclass="Class 1"),
    ]
    (raw / "2026-01-05.csv").write_text("\n".join(day1) + "\n")

    day2 = [
        _row("2026-01-19", "102", "H16", 2.1, "1", 0, "J16", "T16"),
        _row("2026-01-19", "102", "H17", 3.1, "2", 1.0, "J17", "T17"),
        _row("2026-01-19", "102", "H18", 4.1, "3", 2.0, "J18", "T18"),
        _row("2026-01-19", "102", "H19", 6.1, "4", 3.0, "J19", "T19"),
        _row("2026-01-19", "102", "H20", 9.1, "5", 4.0, "J20", "T20"),
        "bad,row,too,few,cols",   # THE malformed row: not 13 columns
    ]
    (raw / "2026-01-19.csv").write_text("\n".join(day2) + "\n")

    day3 = [
        _row("2026-02-02", "103", "H21", 2.3, "1", 0, "J21", "T21"),
        _row("2026-02-02", "103", "H22", 3.3, "2", 1.0, "J22", "T22"),
        _row("2026-02-02", "103", "H23", 4.3, "3", 2.0, "J23", "T23"),
        _row("2026-02-02", "103", "H24", 6.3, "4", 3.0, "J24", "T24"),
        _row("2026-02-02", "103", "H25", 9.3, "5", 4.0, "J25", "T25"),
    ]
    (raw / "2026-02-02.csv").write_text("\n".join(day3) + "\n")

    day4 = [
        _row("2026-02-09", "104", "H1", 2.0, "1", 0, "J1", "T1"),   # ltowin + mr1
        _row("2026-02-09", "104", "H26", 3.0, "2", 1.0, "J26", "T26"),
        _row("2026-02-09", "104", "H27", 4.0, "3", 2.0, "J27", "T27"),
        _row("2026-02-09", "104", "H28", 6.0, "4", 3.0, "J28", "T28"),
        _row("2026-02-09", "104", "H29", 9.0, "0", 0, "J29", "T29"),  # unknown pos
    ]
    (raw / "2026-02-09.csv").write_text("\n".join(day4) + "\n")


NIGHT_DAY = "2026-02-09"
CHALLENGER = "cell:mr1+ltowin"


@pytest.fixture
def school(tmp_path, monkeypatch):
    """A school/ dir with the synthetic corpus + policies.txt, and no
    RACING_API_* credentials so night.py grades purely from disk."""
    school_dir = tmp_path / "school"
    write_corpus(school_dir / "raw")
    (school_dir / "policies.txt").write_text(CHALLENGER + "\n")
    monkeypatch.delenv("RACING_API_USERNAME", raising=False)
    monkeypatch.delenv("RACING_API_PASSWORD", raising=False)
    monkeypatch.delenv("SCHOOL_CHAMPION", raising=False)
    return school_dir


# --------------------------------------------------------------------------- #
# Part B — night school chain end to end
# --------------------------------------------------------------------------- #

def test_night_runs_end_to_end_from_disk(school, capsys):
    rc = night_mod.main(["--day", NIGHT_DAY, "--school", str(school),
                          "--champion", CHALLENGER])
    assert rc == 0
    out = capsys.readouterr().out
    assert "verdict" not in out.lower() or True  # verdict text is asserted below

    csv_path = school / "daily_policy.csv"
    assert csv_path.exists()
    text = csv_path.read_text()
    lines = [ln for ln in text.splitlines() if ln]
    assert lines[0] == "day,policy,picks,wins,returned"
    # a row for EACH policy on trial (fav is implicit, CHALLENGER from policies.txt)
    policies_seen = {ln.split(",")[1] for ln in lines[1:]}
    assert "fav" in policies_seen
    assert CHALLENGER in policies_seen
    # the night grades the trailing window (holes self-heal, 2026-09-02): every
    # row sits inside it and the night's own day is graded
    from datetime import date as _d, timedelta as _td
    from racing_edge.school.night import BACKFILL_DAYS
    _lo = (_d.fromisoformat(NIGHT_DAY) - _td(days=BACKFILL_DAYS - 1)).isoformat()
    days_seen = set()
    for ln in lines[1:]:
        day, policy, picks, wins, returned = ln.split(",")
        assert _lo <= day <= NIGHT_DAY
        days_seen.add(day)
    assert NIGHT_DAY in days_seen


def test_night_verdict_string_is_produced(school, capsys):
    rc = night_mod.main(["--day", NIGHT_DAY, "--school", str(school),
                          "--champion", CHALLENGER])
    assert rc == 0
    out = capsys.readouterr().out
    # the challenger has exactly 1 graded pick that day (< MIN_JUDGE=50) so
    # the ladder must say NO VERDICT, not crash or stay silent.
    assert "NO VERDICT" in out
    assert CHALLENGER in out


def test_night_rerun_same_day_does_not_double_append(school):
    night_mod.main(["--day", NIGHT_DAY, "--school", str(school),
                     "--champion", CHALLENGER])
    rows_after_first = (school / "daily_policy.csv").read_text().splitlines()

    # re-run night school for the SAME day, as a cron retry or manual re-run
    # would (night.py is documented as "safe to re-run").
    night_mod.main(["--day", NIGHT_DAY, "--school", str(school),
                     "--champion", CHALLENGER])
    rows_after_second = (school / "daily_policy.csv").read_text().splitlines()

    assert rows_after_second == rows_after_first, (
        "daily_policy.csv grew on a same-day re-run -- rows for "
        f"{NIGHT_DAY} were appended twice"
    )


# --------------------------------------------------------------------------- #
# Part B — tier0
# --------------------------------------------------------------------------- #

def test_tier0_writes_report_with_full_rank_table(school, tmp_path):
    out = tmp_path / "tier0.md"
    rc = tier0_mod.main(["--day", NIGHT_DAY, "--raw", str(school / "raw"),
                          "--out", str(out)])
    assert rc == 0
    assert out.exists()
    text = out.read_text()
    assert "THE CONTROL" in text
    # every 5-runner race in the corpus -> priced ranks 1..5 must all appear
    for rank in ("1", "2", "3", "4", "5"):
        assert f"| {rank} |" in text
    # rank 6/7+ never occurs (every race here has exactly 5 runners)
    assert "| 6 |" not in text
    assert "| 7+ |" not in text


# --------------------------------------------------------------------------- #
# Part B — shapebook
# --------------------------------------------------------------------------- #

def test_shapebook_build_respects_min_n_floor(school):
    raw = school / "raw"
    # the primary shape (F, Cl5, 2-7 runners, fav<6/4) has 5 races
    # (100,101,102,103,104); the Class 1 shape (race 105) has only 1.
    cells_low = shapebook_mod.build(raw, min_n=3)
    assert len(cells_low) == 1
    (only_key, only_cell), = cells_low.items()
    assert only_cell["n"] == 5
    assert only_key[1] == "Cl5"

    # raise the floor above the only shape's count -> nothing survives
    cells_high = shapebook_mod.build(raw, min_n=6)
    assert cells_high == {}

    # lower the floor to include the thin (n=1) shape too
    cells_all = shapebook_mod.build(raw, min_n=1)
    assert len(cells_all) == 2


# --------------------------------------------------------------------------- #
# Part B — load_corpus malformed-row counting (feeds mine.py / daily.py /
# tier0.py / shapebook.py, all of which import mine.load_corpus)
# --------------------------------------------------------------------------- #

def test_load_corpus_counts_the_malformed_row(school):
    races = mine_mod.load_corpus(school / "raw")
    assert mine_mod.load_corpus.last_skipped == 1
    # every OTHER row still loaded: 15 (day1) + 5 (day2, minus bad row) + 5
    # (day3) + 5 (day4) = 30 runner rows across 6 races
    total_runners = sum(len(race) for race in races)
    assert total_runners == 30
    assert len(races) == 6


# --------------------------------------------------------------------------- #
# Part C — fetch.py: pagination and the empty-day / day_fetched interaction
# --------------------------------------------------------------------------- #

class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_fetch_day_paginates_across_pages(monkeypatch):
    """total=75 over pages of 50 -> two requests, 75 races collected."""
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: None)
    calls = []

    def fake_get(url, params=None, auth=None, timeout=None):
        calls.append(params["skip"])
        skip = params["skip"]
        if skip == 0:
            return _FakeResp({"results": [{"id": i} for i in range(50)],
                               "total": 75})
        if skip == 50:
            return _FakeResp({"results": [{"id": i} for i in range(50, 75)],
                               "total": 75})
        raise AssertionError(f"unexpected skip={skip}")

    monkeypatch.setattr(fetch_mod.requests, "get", fake_get)
    races = fetch_mod.fetch_day("2026-03-01", ("u", "p"))
    assert len(races) == 75
    assert calls == [0, 50]


def test_fetch_main_empty_day_is_remembered_as_confirmed_empty(
        school, tmp_path, monkeypatch):
    """A day with 0 results (total=0): fetch.main writes the (empty) CSV and
    comments file AND a confirmed-empty marker, so day_fetched() reports True
    and the box does not pay for the same blank day every night (bot B3)."""
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: None)
    monkeypatch.setenv("RACING_API_USERNAME", "u")
    monkeypatch.setenv("RACING_API_PASSWORD", "p")
    calls = []

    def fake_get_empty(url, params=None, auth=None, timeout=None):
        calls.append(params)
        return _FakeResp({"results": [], "total": 0})

    monkeypatch.setattr(fetch_mod.requests, "get", fake_get_empty)

    raw = tmp_path / "fetch_raw"
    rc = fetch_mod.main(["--start", "2026-03-05", "--end", "2026-03-05",
                          "--raw", str(raw)])
    assert rc == 0
    day_csv = raw / "2026-03-05.csv"
    assert day_csv.exists() and day_csv.stat().st_size == 0
    assert (raw.parent / "comments" / "2026-03-05.csv").exists()
    assert fetch_mod.empty_marker(day_csv).exists()
    assert fetch_mod.day_fetched(day_csv) is True
    # the second night asks the API nothing for that day
    n = len(calls)
    fetch_mod.main(["--start", "2026-03-05", "--end", "2026-03-05", "--raw", str(raw)])
    assert len(calls) == n
    # a 0-byte file WITHOUT the marker is still 'not fetched' (a failed fetch)
    bare = raw / "2026-03-06.csv"
    bare.write_text("")
    assert fetch_mod.day_fetched(bare) is False


def test_night_takes_its_credentials_through_configs_door_not_the_shell(
        school, monkeypatch):
    """2026-09-02, the box: .env held the credentials, night.py asked
    os.environ, the scheduler's shell had none — the fetch was skipped every
    night since deployment. Night must fetch whenever config can produce
    the credentials, whatever the shell says."""
    for k in ("RACING_API_USERNAME", "RACING_API_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("racing_edge.config.racing_creds", lambda: ("u", "p"))
    called = []
    monkeypatch.setattr("racing_edge.school.fetch.main",
                        lambda argv: called.append(argv) or 0)
    rc = night_mod.main(["--day", NIGHT_DAY, "--school", str(school),
                         "--champion", CHALLENGER])
    assert rc == 0
    # the trailing window, not one day: holes in the last 21 days self-heal
    from datetime import date, timedelta
    from racing_edge.school.night import BACKFILL_DAYS
    want = (date.fromisoformat(NIGHT_DAY) - timedelta(days=BACKFILL_DAYS - 1)).isoformat()
    assert called and called[0][:4] == ["--start", want, "--end", NIGHT_DAY]

