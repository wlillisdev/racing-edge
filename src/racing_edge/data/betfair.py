"""The Betfair Exchange client — FREE data for the box (his word, 2026-10-26:
"i want to get rid of api ... i need to streamline costs" -> "Yes, build it").

A free Betfair account and its free delayed app key give every GB/IE race,
every runner's price at any time, the winner and the Betfair starting price.
That is all the frozen method reads (prices and results — the form dots are
printed, never ranked), so this replaces The Racing API's paid subscription.

Transport only, like data.client: it returns the SAME raw shapes the Racing
API client returns, so favfilter, the guard and the settle run unchanged.
  racecards(day)        -> {"racecards": [{race_id, course, off_time, off_dt,
                            date, race_name, race_class, type, race_status,
                            runners: [{horse_id, horse, odds: [{decimal}]}]}]}
  results_by_date(day)  -> {"results": [{race_id, date, runners: [{horse_id,
                            horse, position, sp_dec}]}]}
  horse_results(...)    -> []  (Betfair holds no form; the dots print "unread")

Ids are prefixed so they can never collide with Racing API ids: a race is
"bf_<marketId>", a horse "bf_<selectionId>". The price of a runner is the
middle of the best back and best lay (the exchange's own fair price), else
the last traded price, else the best back.

Env: BETFAIR_USERNAME, BETFAIR_PASSWORD, BETFAIR_APP_KEY. Hosts:
identitysso.betfair.com (login) and api.betfair.com (data).
"""

from __future__ import annotations

import csv
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

LOGIN_URL = "https://identitysso.betfair.com/api/login"
API_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/"
UK = ZoneInfo("Europe/London")
HORSE_RACING = "7"
BOOK_BATCH = 25          # listMarketBook weight: 200 per call; SP_TRADED is 7 a market


class BetfairError(RuntimeError):
    pass


def _uk_day(day: str) -> date:
    if day in ("today", "", None):
        return datetime.now(UK).date()
    if day == "tomorrow":
        return datetime.now(UK).date() + timedelta(days=1)
    return date.fromisoformat(str(day)[:10])


def _race_type(market: dict) -> str:
    """Flat / Hurdle / Chase / NH Flat, from Betfair's own description or name."""
    rt = str((market.get("description") or {}).get("raceType") or "").lower()
    name = str(market.get("marketName") or "").lower()
    if "hurdle" in rt or " hrd" in f" {name}":
        return "Hurdle"
    if "chase" in rt or " chs" in f" {name}":
        return "Chase"
    if "bumper" in rt or "nh flat" in rt or "nhf" in name:
        return "NH Flat"
    return "Flat"


def runner_price(book_runner: dict) -> float | None:
    """The exchange's fair price for a runner: mid of best back and best lay,
    else the last traded price, else the best back. None when unpriced."""
    ex = book_runner.get("ex") or {}
    back = (ex.get("availableToBack") or [{}])[0].get("price")
    lay = (ex.get("availableToLay") or [{}])[0].get("price")
    if back and lay:
        return round((float(back) + float(lay)) / 2, 2)
    ltp = book_runner.get("lastPriceTraded")
    if ltp:
        return round(float(ltp), 2)
    return round(float(back), 2) if back else None


def card_from(market: dict, book: dict | None) -> dict:
    """One Betfair WIN market (+ its book) in the Racing API racecard shape."""
    start = datetime.fromisoformat(str(market["marketStartTime"]).replace("Z", "+00:00"))
    local = start.astimezone(UK)
    names = {r["selectionId"]: r.get("runnerName", "") for r in market.get("runners") or []}
    status = str((book or {}).get("status") or "OPEN").upper()
    runners = []
    for br in (book or {}).get("runners") or []:
        if br.get("status") not in (None, "ACTIVE"):
            continue                     # a non-runner is not on the card
        p = runner_price(br)
        sid = br.get("selectionId")
        runners.append({"horse_id": f"bf_{sid}", "horse": names.get(sid, str(sid)),
                        "odds": [{"decimal": str(p)}] if p else []})
    return {"race_id": f"bf_{market['marketId']}",
            "course": (market.get("event") or {}).get("venue") or "",
            "off_time": f"{(local.hour % 12) or 12}:{local.minute:02d}",
            "off_dt": start.isoformat(),
            "date": local.date().isoformat(),
            "race_name": market.get("marketName") or "",
            "race_class": "",
            "type": _race_type(market),
            "race_status": "result" if status == "CLOSED" else "declared",
            "runners": runners}


def result_from(book: dict, day: str) -> dict | None:
    """A settled Betfair market in the Racing API results shape, or None while
    it is still open. Winner = position "1"; a loser "2" (the exchange keeps
    no placings); a non-runner has no position, so it settles VOID."""
    if str(book.get("status") or "").upper() != "CLOSED":
        return None
    runners = []
    for br in book.get("runners") or []:
        st = br.get("status")
        sp = (br.get("sp") or {}).get("actualSP")
        try:
            sp = round(float(sp), 2) if sp and float(sp) > 1.0 else None
        except (TypeError, ValueError):
            sp = None
        row = {"horse_id": f"bf_{br.get('selectionId')}", "horse": "",
               "position": "1" if st == "WINNER" else (None if st == "REMOVED" else "2")}
        if sp:
            row["sp_dec"] = sp
        runners.append(row)
    return {"race_id": f"bf_{book.get('marketId')}", "date": day, "runners": runners}


class BetfairClient:
    _TIMEOUT = 30

    def __init__(self, username: str | None = None, password: str | None = None,
                 app_key: str | None = None, record: Path | None = None) -> None:
        self._user = username or os.environ.get("BETFAIR_USERNAME", "")
        self._pass = password or os.environ.get("BETFAIR_PASSWORD", "")
        self._key = app_key or os.environ.get("BETFAIR_APP_KEY", "")
        if not (self._user and self._pass and self._key):
            raise BetfairError("BETFAIR_USERNAME, BETFAIR_PASSWORD and BETFAIR_APP_KEY "
                               "must be set in the environment")
        self._record = record or Path("data/filter_record.csv")
        self._session = requests.Session()
        self._token = ""

    # -- transport ---------------------------------------------------------
    def _login(self) -> None:
        r = self._session.post(LOGIN_URL, data={"username": self._user, "password": self._pass},
                               headers={"X-Application": self._key,
                                        "Accept": "application/json"},
                               timeout=self._TIMEOUT)
        doc = r.json() if r.content else {}
        if r.status_code != 200 or doc.get("status") != "SUCCESS":
            raise BetfairError(f"Betfair login failed: HTTP {r.status_code} "
                               f"{doc.get('error') or doc.get('status') or ''}")
        self._token = doc["token"]

    def _call(self, method: str, body: dict) -> Any:
        if not self._token:
            self._login()
        for attempt in range(3):
            r = self._session.post(API_URL + method + "/", json=body, timeout=self._TIMEOUT,
                                   headers={"X-Application": self._key,
                                            "X-Authentication": self._token,
                                            "Content-Type": "application/json",
                                            "Accept": "application/json"})
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 401) and "INVALID_SESSION" in r.text and attempt == 0:
                self._login()            # an expired session: log in once more
                continue
            if r.status_code >= 500 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise BetfairError(f"Betfair {method}: HTTP {r.status_code} {r.text[:200]}")
        raise BetfairError(f"Betfair {method}: no answer")

    def _books(self, ids: list[str], price_data: list[str]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(ids), BOOK_BATCH):
            out += self._call("listMarketBook", {
                "marketIds": ids[i:i + BOOK_BATCH],
                "priceProjection": {"priceData": price_data}}) or []
        return out

    # -- the Racing API's shapes ----------------------------------------------
    def racecards(self, day: str = "today") -> dict:
        d = _uk_day(day)
        start = datetime(d.year, d.month, d.day, tzinfo=UK).astimezone(timezone.utc)
        markets = self._call("listMarketCatalogue", {
            "filter": {"eventTypeIds": [HORSE_RACING], "marketCountries": ["GB", "IE"],
                       "marketTypeCodes": ["WIN"],
                       "marketStartTime": {
                           "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "to": (start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}},
            "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION",
                                 "MARKET_DESCRIPTION"],
            "sort": "FIRST_TO_START", "maxResults": "1000"}) or []
        books = {b["marketId"]: b for b in
                 self._books([m["marketId"] for m in markets], ["EX_BEST_OFFERS"])}
        return {"racecards": [card_from(m, books.get(m["marketId"])) for m in markets]}

    def results_by_date(self, date_str: str) -> dict:
        """Settled results for the races the box recorded that day. A closed
        market drops out of the catalogue, so the market ids come from the
        day's rows in the filter record (every favourite is there)."""
        day = _uk_day(date_str).isoformat()
        ids = sorted({r["race_id"][3:] for r in self._record_rows()
                      if r.get("date") == day and str(r.get("race_id", "")).startswith("bf_")})
        res = [result_from(b, day) for b in self._books(ids, ["SP_TRADED"])] if ids else []
        return {"results": [r for r in res if r]}

    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]:
        return []                        # the exchange holds no form

    def _record_rows(self) -> list[dict]:
        if not self._record.exists():
            return []
        with open(self._record, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
