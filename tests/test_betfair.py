"""THE FREE DATA DOOR (his word, 2026-10-26: "i want to get rid of api").

Offline: Betfair's own JSON shapes go in through a fake HTTP session, and the
REAL favfilter list and settle come out the other end — so the box can drop
the paid Racing API without the frozen method noticing.
"""
from __future__ import annotations

import pytest

from racing_edge.data import betfair as B
from racing_edge.school import favfilter as F

CATALOGUE = [{
    "marketId": "1.111", "marketName": "2m Hcap Hrd",
    "marketStartTime": "2026-10-27T13:20:00.000Z",
    "description": {"raceType": "Hurdle"},
    "event": {"venue": "Hereford", "countryCode": "GB"},
    "runners": [{"selectionId": s, "runnerName": n} for s, n in
                ((1, "Fav Horse"), (2, "Second"), (3, "Third"), (4, "Fourth"), (5, "NonRunner"))],
}]


def _book(status="OPEN", sp=False):
    rows = []
    for sid, back, lay in ((1, 2.1, 2.14), (2, 4.0, 4.2), (3, 6.0, 6.4), (4, 9.0, 10.0)):
        r = {"selectionId": sid, "status": "ACTIVE",
             "ex": {"availableToBack": [{"price": back}], "availableToLay": [{"price": lay}]}}
        if status == "CLOSED":
            r["status"] = "WINNER" if sid == 1 else "LOSER"
            r["sp"] = {"actualSP": 2.36 if sid == 1 else 5.0}
        rows.append(r)
    rows.append({"selectionId": 5, "status": "REMOVED"})
    return {"marketId": "1.111", "status": status, "runners": rows}


class FakeResp:
    def __init__(self, doc, code=200):
        self._doc, self.status_code = doc, code
        self.content = b"x"
        self.text = str(doc)

    def json(self):
        return self._doc


class FakeSession:
    def __init__(self, book_status="OPEN"):
        self.calls = []
        self.book_status = book_status

    def post(self, url, data=None, json=None, headers=None, timeout=None):
        self.calls.append((url, json))
        if url == B.LOGIN_URL:
            assert headers["X-Application"] == "KEY"
            return FakeResp({"status": "SUCCESS", "token": "TOK"})
        assert headers["X-Authentication"] == "TOK"
        if url.endswith("listMarketCatalogue/"):
            assert json["filter"]["marketTypeCodes"] == ["WIN"]
            return FakeResp(CATALOGUE)
        if url.endswith("listMarketBook/"):
            return FakeResp([_book(self.book_status)])
        raise AssertionError(url)


def _client(tmp_path, status="OPEN"):
    c = B.BetfairClient("u", "p", "KEY", record=tmp_path / "fr.csv")
    c._session = FakeSession(status)
    return c


def test_the_free_card_reads_like_the_paid_one_and_the_filter_picks_from_it(tmp_path):
    c = _client(tmp_path)
    doc = c.racecards("2026-10-27")
    card = doc["racecards"][0]
    assert card["race_id"] == "bf_1.111" and card["type"] == "Hurdle"
    assert card["course"] == "Hereford" and card["off_time"] == "1:20"
    assert [r["horse"] for r in card["runners"]] == ["Fav Horse", "Second", "Third", "Fourth"]
    assert card["runners"][0]["odds"] == [{"decimal": "2.12"}]       # mid of 2.1 / 2.14
    rows = F.daily_list("2026-10-27", client=c)
    assert [(r["horse"], r["price"]) for r in rows] == [("Fav Horse", 2.12)]
    assert [p["horse"] for p in F.todays_picks(rows)] == ["Fav Horse"]


def test_the_free_results_settle_the_record_at_betfair_sp(tmp_path):
    c = _client(tmp_path)
    rows = F.daily_list("2026-10-27", client=c)
    F.record_picks(rows, "2026-10-27", tmp_path / "fr.csv")
    c = _client(tmp_path, status="CLOSED")
    res = c.results_by_date("2026-10-27")
    assert res["results"][0]["race_id"] == "bf_1.111"
    by = {r["horse_id"]: r for r in res["results"][0]["runners"]}
    assert by["bf_1"]["position"] == "1" and by["bf_1"]["sp_dec"] == 2.36
    assert by["bf_2"]["position"] == "2" and by["bf_5"]["position"] is None
    assert F.settle_record("2026-10-27", res, tmp_path / "fr.csv") >= 2
    got = {(r["line"], r["horse"]): (r["result"], r["sp"])
           for r in F._load_record(tmp_path / "fr.csv")}
    assert got[("filter", "Fav Horse")] == ("WON", "2.36")


def test_an_open_market_is_never_settled(tmp_path):
    c = _client(tmp_path)
    F.record_picks(F.daily_list("2026-10-27", client=c), "2026-10-27", tmp_path / "fr.csv")
    assert _client(tmp_path, "OPEN").results_by_date("2026-10-27") == {"results": []}


def test_the_data_door_switches_on_the_env(monkeypatch):
    from racing_edge.data.client import RacingAPIClient, get_client
    monkeypatch.setenv("DATA_SOURCE", "betfair")
    for k, v in (("BETFAIR_USERNAME", "u"), ("BETFAIR_PASSWORD", "p"), ("BETFAIR_APP_KEY", "k")):
        monkeypatch.setenv(k, v)
    assert isinstance(get_client(), B.BetfairClient)
    monkeypatch.delenv("BETFAIR_APP_KEY")
    with pytest.raises(B.BetfairError):
        get_client()
    monkeypatch.setenv("DATA_SOURCE", "")
    monkeypatch.setenv("RACING_API_USERNAME", "x")
    monkeypatch.setenv("RACING_API_PASSWORD", "y")
    from racing_edge.config import get_config
    get_config.cache_clear()
    assert isinstance(get_client(), RacingAPIClient)
    get_config.cache_clear()
