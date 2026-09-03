"""THE LIVE DOOR CHECK's own tests — against FAKE clients, deliberately.

THE SCAR this module exists to answer (2026-09-02 22:00, the box): settle
FAILED and learn CRASHED on a live HTTP 422 while 282 tests, every one
against a fake client, stayed green. These tests do NOT re-open that hole —
they pin the CHECK's own logic (which door feeds which, what a skip looks
like, what render prints), the same as every other test in this repo. The
check earns its keep by being run for REAL on the box
(PYTHONPATH=src python -m racing_edge.data.doors) and in the 09:30 health
task — that is the live door a mock can never stand in for.
"""

from __future__ import annotations


from racing_edge.data.client import RacingAPIError
from racing_edge.data.doors import DOORS, all_open, check_doors, render


class FakeClient:
    """One client, every door scripted by name. A behavior that IS an
    Exception instance is raised; anything else is returned as-is. An
    unscripted call is a test bug, not a silent pass."""

    def __init__(self, **behaviors):
        self._behaviors = behaviors
        self.calls: list[str] = []

    def _resolve(self, name):
        self.calls.append(name)
        if name not in self._behaviors:
            raise AssertionError(f"unscripted call: {name}")
        b = self._behaviors[name]
        if isinstance(b, Exception):
            raise b
        return b

    def racecards(self, day="today"):
        return self._resolve("racecards")

    def results_by_date(self, date_str):
        return self._resolve("results_by_date")

    def result_by_id(self, race_id):
        return self._resolve("result_by_id")

    def horse_results(self, horse_id, limit=12):
        return self._resolve("horse_results")

    def horse_distance_times(self, horse_id):
        return self._resolve("horse_distance_times")

    def trainer_jockeys(self, trainer_id):
        return self._resolve("trainer_jockeys")

    def trainer_course(self, trainer_id, course_id=""):
        return self._resolve("trainer_course")

    def jockey_course(self, jockey_id):
        return self._resolve("jockey_course")

    def trainer_ages(self, trainer_id):
        return self._resolve("trainer_ages")


_RUNNER = {"horse_id": "hrs_1", "trainer_id": "trn_1", "jockey_id": "jky_1",
           "horse": "Test Horse", "trainer": "Test Trainer", "jockey": "Test Jockey"}

_CARD = {"racecards": [
    {"race_id": "rac_1", "course": "Ascot", "off_time": "14:00",
     "date": "2026-09-03", "type": "Hurdle", "runners": [_RUNNER]},
]}

_RESULTS = {"results": [
    {"race_id": "res_1", "date": "2026-09-02", "runners": []},
], "total": 1}

_ALL_OPEN = dict(
    racecards=_CARD,
    results_by_date=_RESULTS,
    result_by_id={"race_id": "res_1", "runners": []},
    horse_results=[{"race_id": "old_1"}],
    horse_distance_times=[{"dist_f": 20, "wins": 1}],
    trainer_jockeys=[{"jockey": "Test Jockey"}],
    trainer_course=[{"course": "Ascot"}],
    jockey_course=[{"course": "Ascot"}],
    trainer_ages=[{"age": 4}],
)


def _row(rows, name):
    return next(r for r in rows if r[0] == name)


def test_every_door_open_reports_sensible_details():
    client = FakeClient(**_ALL_OPEN)
    rows = check_doors(client, today=__import__("datetime").date(2026, 9, 3))
    assert [r[0] for r in rows] == DOORS
    assert all_open(rows)
    assert _row(rows, "racecards")[2] == "1 races"
    assert _row(rows, "results_by_date")[2] == "1 rows"
    assert _row(rows, "result_by_id")[2] == "doc"
    assert _row(rows, "horse_results")[2] == "1 rows"
    assert _row(rows, "trainer_ages")[2] == "1 rows"
    # the known input was actually drawn from the card and handed on
    assert client.calls == list(DOORS)


def test_results_by_date_422_fails_alone_others_still_open():
    """THE EXACT SHAPE of the scar: a wrong param on the results door reads
    HTTP 422 — that door FAILS, result_by_id (which needs ITS document)
    is skipped, but the card-fed doors never even notice."""
    behaviors = dict(_ALL_OPEN)
    behaviors["results_by_date"] = RacingAPIError(
        422, "https://api.theracingapi.com/v1/results", "unrecognised query parameter")
    client = FakeClient(**behaviors)
    rows = check_doors(client, today=__import__("datetime").date(2026, 9, 3))

    name, ok, detail = _row(rows, "results_by_date")
    assert not ok
    assert "422" in detail
    assert "RacingAPIError" in detail

    name, ok, detail = _row(rows, "result_by_id")
    assert not ok
    assert detail == "skipped — no results to try"

    # racecards and everything it feeds is untouched by the results failure
    assert _row(rows, "racecards")[1] is True
    for door in ("horse_results", "horse_distance_times", "trainer_jockeys",
                 "trainer_course", "jockey_course", "trainer_ages"):
        assert _row(rows, door)[1] is True, door
    assert not all_open(rows)


def test_racecards_failure_skips_dependents_without_crashing():
    behaviors = dict(_ALL_OPEN)
    behaviors["racecards"] = RacingAPIError(500, "https://x/racecards/pro", "boom")
    client = FakeClient(**behaviors)
    rows = check_doors(client, today=__import__("datetime").date(2026, 9, 3))

    assert _row(rows, "racecards")[1] is False
    for door in ("horse_results", "horse_distance_times", "trainer_jockeys",
                 "trainer_course", "jockey_course", "trainer_ages"):
        _, ok, detail = _row(rows, door)
        assert ok is False
        assert detail == "skipped — no card to try"
    # results_by_date needs nothing from the card — still genuinely tried
    assert _row(rows, "results_by_date")[1] is True
    assert _row(rows, "result_by_id")[1] is True
    assert not all_open(rows)
    # the six dependents were never called at all — a dead root door must
    # not even ATTEMPT the doors it cannot feed
    for door in ("horse_results", "horse_distance_times", "trainer_jockeys",
                 "trainer_course", "jockey_course", "trainer_ages"):
        assert door not in client.calls


def test_empty_card_is_ok_but_still_starves_the_dependents():
    """An empty racecards answer is an honest 'no racing', not a refused
    door — but with no runner to draw ids from, the dependents still can't
    be tried for real, so they are skipped rather than called with ''.
    """
    behaviors = dict(_ALL_OPEN)
    behaviors["racecards"] = {"racecards": []}
    client = FakeClient(**behaviors)
    rows = check_doors(client, today=__import__("datetime").date(2026, 9, 3))

    assert _row(rows, "racecards") == ("racecards", True, "empty")
    for door in ("horse_results", "horse_distance_times", "trainer_jockeys",
                 "trainer_course", "jockey_course", "trainer_ages"):
        assert _row(rows, door) == (door, False, "skipped — no card to try")


def test_no_race_id_is_a_happy_skip_not_a_failure():
    behaviors = dict(_ALL_OPEN)
    behaviors["results_by_date"] = {"results": [], "total": 0}
    client = FakeClient(**behaviors)
    rows = check_doors(client, today=__import__("datetime").date(2026, 9, 3))

    assert _row(rows, "results_by_date") == ("results_by_date", True, "empty")
    assert _row(rows, "result_by_id") == ("result_by_id", True, "no race id to try")
    assert "result_by_id" not in client.calls


def test_any_exception_is_caught_never_raised():
    behaviors = dict(_ALL_OPEN)
    behaviors["trainer_ages"] = ValueError("something the client never should have done")
    client = FakeClient(**behaviors)
    rows = check_doors(client, today=__import__("datetime").date(2026, 9, 3))  # must not raise
    name, ok, detail = _row(rows, "trainer_ages")
    assert not ok
    assert detail.startswith("ValueError: ")


def test_render_lines_and_tally():
    rows = [
        ("racecards", True, "12 races"),
        ("results_by_date", False, "RacingAPIError: HTTP 422 for .../results: bad param"),
    ]
    lines = render(rows)
    assert lines[0] == "  ✓ door racecards — 12 races"
    assert lines[1] == ("  ✗ door results_by_date — RacingAPIError: HTTP 422 for "
                         ".../results: bad param")
    assert lines[-1] == "  doors: 1/2 open"


def test_all_open_true_and_false():
    assert all_open([("a", True, "x"), ("b", True, "y")])
    assert not all_open([("a", True, "x"), ("b", False, "y")])


def test_doors_list_matches_the_contract_order():
    assert DOORS == [
        "racecards", "results_by_date", "result_by_id", "horse_results",
        "horse_distance_times", "trainer_jockeys", "trainer_course",
        "jockey_course", "trainer_ages",
    ]
