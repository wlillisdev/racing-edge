"""THE LESSON REGISTER — a lesson may not sit unacted-on and quiet.

The master, 2026-09-07: "nothing changing has to change or else it is
pointless." The why ledger had dissected ten races a night for a week and the
weekly synthesis had surfaced the same shape thirty times in six weeks, and
none of it had become a change, a test, or even a question. The register does
not decide anything — promotion is his word — but it refuses to let an open
lesson go quiet, and the 09:30 page turns red while one has.
"""
from datetime import date

from racing_edge.school import lessons as L

TODAY = date(2026, 9, 7)


def _row(id_, status, first_seen, lesson="a lesson"):
    return {"id": id_, "first_seen": first_seen, "last_seen": first_seen,
            "count": "1", "status": status, "lesson": lesson, "shape": "",
            "source": "", "test": "", "bar": "", "ruling": "", "outcome": ""}


def test_an_open_lesson_past_the_bar_turns_the_page_red():
    fresh = [_row("a", "SURFACED", "2026-09-05")]
    ok, line = L.health_line(fresh, TODAY)
    assert ok and "nothing waiting past" in line

    old = [_row("a", "SURFACED", "2026-07-27", "manner beats the bare figure")]
    ok, line = L.health_line(old, TODAY)
    assert not ok
    assert "LESSONS NOT ACTED ON" in line and "42d" in line
    assert "manner beats the bare figure" in line


def test_red_means_nothing_is_happening_not_merely_unresolved():
    """CARVED and KILLED are closed. TESTING is unresolved but ACTED ON — it
    carries a named test and bar, and making it red merely for being open
    would punish the one behaviour we want (his word, 2026-09-07: "why not
    test them").

    REFINED 2026-09-25 by fault (c) of the audit. That reasoning was right
    about WHY but too generous: with no deadline at all, TESTING became a
    parking space and four lessons sat in it for two months, two of them
    already answered by a test nobody wrote back. A TESTING lesson is now red
    ONLY when its test has not reported; an outcome of any kind, FAILED
    included, clears it."""
    for status in ("CARVED", "KILLED"):
        ok, _ = L.health_line([_row("a", status, "2026-01-01")], TODAY)
        assert ok, f"{status} should not be red"
    answered = dict(_row("a", "TESTING", "2026-01-01"),
                    outcome="FAILED — reversed out of sample")
    ok, _ = L.health_line([answered], TODAY)
    assert ok, "a TESTING lesson whose test REPORTED is not rot"
    ok, _ = L.health_line([_row("a", "TESTING", "2026-01-01")], TODAY)
    assert not ok, "a TESTING lesson whose test never reported IS rot"
    for status in L.NEEDS_ACTION:
        ok, _ = L.health_line([_row("a", status, "2026-01-01")], TODAY)
        assert not ok, f"{status} should be red"
    # and TESTING is still counted as OPEN — unresolved, just not shouting
    assert "TESTING" in L.OPEN and "TESTING" not in L.NEEDS_ACTION


def test_the_oldest_open_lesson_is_the_one_named():
    """A TESTING lesson that has REPORTED is acted on and stays out of the
    red list, however old (refined 2026-09-25, fault (c): it is the silence
    that is rot, not the age)."""
    rows = [_row("recent", "SURFACED", "2026-08-25", "the recent one"),
            _row("ancient", "DOORBELL", "2026-07-01", "the ignored one"),
            dict(_row("under-test", "TESTING", "2026-07-01", "the tested one"),
                 outcome="PASSED on both halves")]
    st = L.stale(rows, TODAY)
    assert [r["id"] for r in st] == ["ancient", "recent"]   # the tested one is acted on
    _, line = L.health_line(rows, TODAY)
    assert "the ignored one" in line


def test_note_counts_a_repeat_and_never_changes_a_status():
    """A lesson the ledger teaches again is counted. A KILLED lesson that
    keeps resurfacing still counts — so a bad ruling shows up in the record
    instead of being silently absorbed."""
    rows = L.note([], "x", lesson="say it once", day="2026-09-01")
    assert rows[0]["count"] == "1" and rows[0]["status"] == "SURFACED"
    rows[0]["status"] = "KILLED"
    rows = L.note(rows, "x", day="2026-09-07")
    assert rows[0]["count"] == "2"
    assert rows[0]["last_seen"] == "2026-09-07"
    assert rows[0]["first_seen"] == "2026-09-01"
    assert rows[0]["status"] == "KILLED"          # only he moves it


def test_the_register_survives_a_round_trip(tmp_path):
    p = tmp_path / "lessons.csv"
    rows = L.note([], "x", lesson="a, comma \"and\" a quote", shape="Cl3-4")
    L.save(rows, p)
    back = L.load(p)
    assert back[0]["lesson"] == 'a, comma "and" a quote'
    assert back[0]["shape"] == "Cl3-4"
    assert L.load(tmp_path / "missing.csv") == []


def test_the_real_register_is_present_and_honest():
    """The seeded register itself: every row carries a known status and a
    lesson, and the lessons the synthesis named are in it."""
    rows = L.load()
    assert rows, "data/lessons.csv is missing — the loop has nowhere to put a lesson"
    ids = {r["id"] for r in rows}
    assert "manner-beats-the-figure" in ids
    for r in rows:
        assert r["status"] in L.STATUSES, f"{r['id']} has status {r['status']!r}"
        assert r["lesson"].strip(), f"{r['id']} has no lesson written"


def test_a_TESTING_lesson_whose_test_never_reports_goes_red():
    """Fault (c) from the 2026-09-20 audit. TESTING was kept out of
    NEEDS_ACTION so that doing the right thing would not show red forever —
    but with no deadline it became a parking space: four lessons sat at
    TESTING from 27 July to 25 September, and two had actually been tested on
    20 September with nobody writing the answer back."""
    silent = _row("a", "TESTING", "2026-07-27")        # 42 days, no outcome
    ok, line = L.health_line([silent], TODAY)
    assert not ok, "a test that never reports is rot"
    assert "no outcome reported" in line

    reported = dict(silent, outcome="FAILED — reversed out of sample")
    ok, _ = L.health_line([reported], TODAY)
    assert ok, "an outcome of ANY kind clears it — FAILED is a result too"

    fresh = _row("b", "TESTING", "2026-09-01")         # 6 days, still in time
    ok, _ = L.health_line([fresh], TODAY)
    assert ok, "a test inside its window must not be nagged"

    assert L.TESTING_DAYS == 28
