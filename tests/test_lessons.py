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
    assert ok and "none open past" in line

    old = [_row("a", "SURFACED", "2026-07-27", "manner beats the bare figure")]
    ok, line = L.health_line(old, TODAY)
    assert not ok
    assert "LESSONS NOT ACTED ON" in line and "42d" in line
    assert "manner beats the bare figure" in line


def test_a_ruled_lesson_stops_shouting_and_a_killed_one_stays_dead():
    """CARVED and KILLED are closed. Only SURFACED, DOORBELL and TESTING are
    open — a lesson he has ruled on is not nagging him about it again."""
    for status in ("CARVED", "KILLED"):
        ok, _ = L.health_line([_row("a", status, "2026-01-01")], TODAY)
        assert ok, f"{status} should be closed"
    for status in L.OPEN:
        ok, _ = L.health_line([_row("a", status, "2026-01-01")], TODAY)
        assert not ok, f"{status} should still be open"


def test_the_oldest_open_lesson_is_the_one_named():
    rows = [_row("recent", "SURFACED", "2026-08-25", "the recent one"),
            _row("ancient", "DOORBELL", "2026-07-01", "the ignored one"),
            _row("middle", "TESTING", "2026-08-01", "the middling one")]
    st = L.stale(rows, TODAY)
    assert [r["id"] for r in st] == ["ancient", "middle", "recent"]
    _, line = L.health_line(rows, TODAY)
    assert "the ignored one" in line and "3 of 3" in line


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
