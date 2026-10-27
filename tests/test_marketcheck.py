"""The pre-off market check (his word, 27 Oct): flags only, never a pick."""

from datetime import datetime, timezone

from racing_edge.cli.marketcheck import check, flags, price, render


def _runner(sid, name, back, lay, fc=(9, 1)):
    return {"selection_id": sid, "name": name, "back": back, "lay_best": lay, "ltp": back,
            "meta": {"FORECASTPRICE_NUMERATOR": str(fc[0]), "FORECASTPRICE_DENOMINATOR": str(fc[1])}}


def _race(start, runners):
    return [{"venue": f"Newcastle {start}", "start": f"2026-10-27T{start}:00Z",
             "market_id": "1.1", "market_name": "2m Hcap Hrd", "runners": runners}]


def test_price_trusts_only_a_tight_spread():
    assert price({"back": 3.0, "lay_best": 3.2}) == (3.1, True)
    assert price({"back": 10.0, "lay_best": 20.0, "ltp": 12.0}) == (12.0, False)
    assert price({}) == (None, False)


def test_north_of_richmond_shape_is_supported_and_firmed():
    # 27 Oct: forecast 6/1, 3.85 at 08:05, 3.12 at 12:05, won at 9/4
    f = flags(2.2, 3.85, 3.12, True)
    assert f == ["SUPPORTED x2.2 v forecast", "FIRMED 3.85->3.12"]
    assert flags(0.5, None, 12.0, True) == ["FRIENDLESS x0.5 v forecast"]
    assert flags(1.0, None, 4.0, True) == []


def test_an_untrusted_price_raises_no_flag():
    assert flags(4.8, 20.0, 6.0, False) == []


def test_drifter_flagged():
    assert flags(1.0, 4.0, 7.0, True) == ["DRIFT 4->7"]


def test_shares_are_normalised_to_each_book():
    # a forecast book of 200% and an exchange book of 100% with the same shape: no move
    runners = [_runner(1, "A", 2.0, 2.0, (0, 1)), _runner(2, "B", 4.0, 4.0, (1, 1)),
               _runner(3, "C", 4.0, 4.0, (1, 1))]
    rows = check(_race("15:01", runners))[0]["rows"]
    assert all(r["flags"] == [] for r in rows)


def test_morning_matched_and_too_late_races_named():
    morning = _race("15:01", [_runner(1, "North of Richmond", 3.8, 3.9, (6, 1))])
    now = _race("15:01", [_runner(1, "North of Richmond", 3.1, 3.15, (6, 1))])
    races = check(now, morning, datetime(2026, 10, 27, 11, 5, tzinfo=timezone.utc), 15)
    r = races[0]["rows"][0]
    assert r["morning"] == 3.85 and r["now"] == 3.12
    assert not races[0]["too_late"]
    late = check(now, morning, datetime(2026, 10, 27, 14, 50, tzinfo=timezone.utc), 15)
    assert late[0]["too_late"]
    assert "TOO LATE" in render(late)


def test_render_shows_leaders_and_every_flagged_runner():
    runners = [_runner(i, f"H{i}", 2.0 + i, 2.0 + i, (1 + i, 1)) for i in range(6)]
    out = render(check(_race("18:30", runners)))
    assert "H3" in out and "H5" not in out      # leaders shown, an unflagged outsider not
    runners[5] = _runner(5, "H5", 3.0, 3.0, (6, 1))
    out = render(check(_race("18:30", runners)))
    assert "| H5 |" in out and "SUPPORTED" in out
