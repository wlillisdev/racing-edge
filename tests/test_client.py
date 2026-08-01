"""The two-door horse_results contract (2026-08-01, the blind Saturday).

/horses/{id}/results is Pro-tier; on the Standard plan it answers 401 and a
whole morning's histories die. These tests pin the recovery: the client
demotes itself to the Basic-tier /racecards/{horse_id}/results door and stays
there for the rest of the process.
"""

from __future__ import annotations

import pytest

from racing_edge.data.client import RacingAPIClient, RacingAPIError

_ROWS = [{"race_id": "rac_1", "date": "2026-07-20", "runners": []}]


def _client(responses: dict[str, object]) -> RacingAPIClient:
    """A client whose _get is scripted: path-prefix -> rows-doc, int (raise as
    that HTTP status), or Exception. Records every path hit in client.calls."""
    c = RacingAPIClient.__new__(RacingAPIClient)
    c._hr_demoted = False
    c.calls = []

    def _get(path, params=None, allow_404=True):
        c.calls.append(path)
        for prefix, resp in responses.items():
            if path.startswith(prefix):
                if isinstance(resp, int):
                    raise RacingAPIError(resp, path, "scripted")
                return resp
        raise AssertionError(f"unscripted path {path}")

    c._get = _get
    return c


def test_pro_door_first_and_sufficient():
    c = _client({"/horses/": {"results": _ROWS}})
    assert c.horse_results("hrs_1") == _ROWS
    assert not c._hr_demoted
    assert c.calls == ["/horses/hrs_1/results"]


def test_plan_gate_demotes_to_racecards_door_and_stays_there():
    c = _client({"/horses/": 401, "/racecards/": {"results": _ROWS}})
    assert c.horse_results("hrs_1") == _ROWS
    assert c._hr_demoted
    # the second horse goes STRAIGHT to the standard door — no 401 per horse
    assert c.horse_results("hrs_2") == _ROWS
    assert c.calls == ["/horses/hrs_1/results", "/racecards/hrs_1/results",
                       "/racecards/hrs_2/results"]


def test_not_on_card_is_an_honest_blank_not_a_crash():
    c = _client({"/horses/": 401, "/racecards/": 422})
    assert c.horse_results("hrs_1") == []


def test_unknown_horse_404_is_blank_without_demotion():
    c = _client({"/horses/": 404})
    assert c.horse_results("hrs_1") == []
    assert not c._hr_demoted


def test_server_error_stays_loud():
    c = _client({"/horses/": 500})
    with pytest.raises(RacingAPIError):
        c.horse_results("hrs_1")


def test_pin_standard_skips_the_pro_door(monkeypatch):
    monkeypatch.setenv("RACING_API_HORSE_RESULTS", "standard")
    c = _client({"/racecards/": {"results": _ROWS}})
    assert c.horse_results("hrs_1") == _ROWS
    assert c.calls == ["/racecards/hrs_1/results"]


def test_pin_pro_keeps_the_plan_gate_loud(monkeypatch):
    monkeypatch.setenv("RACING_API_HORSE_RESULTS", "pro")
    c = _client({"/horses/": 401})
    with pytest.raises(RacingAPIError):
        c.horse_results("hrs_1")
