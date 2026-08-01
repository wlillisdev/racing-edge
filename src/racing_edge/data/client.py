"""The Racing API client — transport only. HTTP Basic Auth (NOT a key/Bearer).

Salvaged from the old src/api_client.py (its retry + allow_404 design was sound)
with the audit's fixes: the docstring no longer lies about Bearer auth, region
is passed to /results, and the client returns raw JSON or None — it never
normalises (that's data.normalise's job).
"""

from __future__ import annotations

import time
from typing import Any

import requests
from requests.exceptions import ConnectionError, ReadTimeout, Timeout

from racing_edge.config import Config, get_config


class RacingAPIError(RuntimeError):
    def __init__(self, status_code: int, url: str, message: str = "") -> None:
        super().__init__(f"HTTP {status_code} for {url}: {message}")
        self.status_code = status_code
        self.url = url


class RacingAPIClient:
    _TIMEOUT = 30
    _MAX_RETRIES = 6
    _BACKOFF = 2.0
    _MIN_INTERVAL = 0.25     # proactive throttle ~4 req/s — stay under the rate limit

    def __init__(self, cfg: Config | None = None) -> None:
        self._cfg = cfg or get_config()
        self._session = requests.Session()
        self._session.auth = (self._cfg.api.username, self._cfg.api.password)  # Basic Auth
        self._last_request = 0.0
        self._hr_demoted = False   # /horses/…/results plan-gated? remembered per process

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_request
        if gap < self._MIN_INTERVAL:
            time.sleep(self._MIN_INTERVAL - gap)
        self._last_request = time.monotonic()

    def _get(self, path: str, params: Any = None, allow_404: bool = True) -> Any:
        url = f"{self._cfg.api.base_url}{path}"
        attempt = 0
        while True:
            self._throttle()
            try:
                resp = self._session.get(url, params=params, timeout=self._TIMEOUT)
            except (ConnectionError, ReadTimeout, Timeout) as exc:
                attempt += 1
                if attempt > self._MAX_RETRIES:
                    raise RacingAPIError(0, url, str(exc)) from exc
                time.sleep(self._BACKOFF * (2 ** (attempt - 1)))
                continue
            if resp.status_code == 429:        # rate limited — back off and retry
                attempt += 1
                if attempt > self._MAX_RETRIES:
                    raise RacingAPIError(429, url, "rate limited after retries")
                try:
                    wait = float(resp.headers.get("Retry-After", ""))
                except ValueError:
                    wait = self._BACKOFF * (2 ** (attempt - 1))
                time.sleep(min(max(wait, 1.0), 30.0))
                continue
            if resp.status_code == 200:
                return resp.json()
            # 404 = not found; 403 = plan doesn't cover the endpoint (2026-07-25
            # reliability audit: a tier downgrade must degrade an OPTIONAL lens to
            # OWED, never crash the whole morning) — both read as honest empties
            # where the caller allows it
            if resp.status_code in (404, 403) and allow_404:
                return None
            raise RacingAPIError(resp.status_code, url, resp.text[:200])

    # ---- racecards / results ------------------------------------------------
    def racecards(self, day: str = "today") -> dict:
        """Pro racecards for a day (accepts 'today', 'tomorrow', or YYYY-MM-DD —
        a past date for backtesting). Returns the raw doc (key 'racecards')."""
        from datetime import date, timedelta
        if day == "today":
            ds = date.today().isoformat()
        elif day == "tomorrow":
            ds = (date.today() + timedelta(days=1)).isoformat()
        else:
            ds = day
        regions = [r.strip() for r in self._cfg.api.regions.split(",")]
        # tier from env so a plan downgrade is one .env line, not a code change
        # (RACING_API_CARDS=standard after dropping Pro; default stays pro)
        import os
        tier = os.environ.get("RACING_API_CARDS", "pro").strip() or "pro"
        if tier == "pro":
            params = [("date", ds)] + [("region_codes", r) for r in regions]
        else:
            # standard/basic take day=today|tomorrow ONLY — no date param (the 422
            # that silently killed every morning after the downgrade, 2026-07-13)
            today = date.today().isoformat()
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            if ds == today:
                dayp = "today"
            elif ds == tomorrow:
                dayp = "tomorrow"
            else:
                return {"racecards": []}   # past cards are Pro-only — honest empty
            params = [("day", dayp)] + [("region_codes", r) for r in regions]
        return self._get(f"/racecards/{tier}", params=params,
                         allow_404=True) or {"racecards": []}

    def results_by_date(self, date_str: str) -> dict:
        params = [("start_date", date_str), ("end_date", date_str), ("limit", 100)]
        return self._get("/results", params=params, allow_404=True) or {"results": []}

    def result_by_id(self, race_id: str) -> dict | None:
        """One past race's full result — the FRANKING door (#5/#15): who else was in
        it, where they finished, their comments. None if unknown."""
        if not race_id:
            return None
        return self._get(f"/results/{race_id}", allow_404=True)

    # ---- per-horse / per-trainer (for the evidence the method needs) --------
    @staticmethod
    def _result_rows(doc: Any) -> list[dict]:
        if isinstance(doc, dict):
            rows = doc.get("results") or doc.get("data") or []
            return rows if isinstance(rows, list) else []
        return doc if isinstance(doc, list) else []

    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]:
        """A horse's past runs — the raw material for the proven-at-level reads.

        TWO DOORS (2026-08-01, the blind Saturday: /horses/{id}/results is a PRO
        endpoint and started answering 401 on the Standard plan — every history
        died and the morning read went in blind). The Pro door is tried first;
        on a plan-gate status (401/402/403) the client demotes itself for the
        rest of the process to the Basic-tier /racecards/{horse_id}/results door
        — the SAME race-shaped rows, but only for horses on today/tomorrow's
        cards, which is exactly the morning's use. Histories are NOT an optional
        lens, so plan-gates here fall through loudly instead of the silent
        403-empty other endpoints get. Pin a door with
        RACING_API_HORSE_RESULTS=pro|standard.
        REVERT-IF: on-card horses come back history-empty two mornings running.
        """
        if not horse_id:
            return []
        import os
        pin = (os.environ.get("RACING_API_HORSE_RESULTS", "") or "").strip().lower()
        if pin != "standard" and not self._hr_demoted:
            try:
                doc = self._get(f"/horses/{horse_id}/results",
                                params={"limit": limit}, allow_404=False)
                return self._result_rows(doc)
            except RacingAPIError as exc:
                if exc.status_code == 404:
                    return []                      # unknown horse — honest blank
                if pin == "pro" or exc.status_code not in (401, 402, 403):
                    raise
                self._hr_demoted = True
                print(f"      ⚠ /horses/…/results plan-gated (HTTP {exc.status_code})"
                      " — switching to the racecards results door for this run",
                      flush=True)
        try:
            doc = self._get(f"/racecards/{horse_id}/results",
                            params={"limit": limit}, allow_404=False)
        except RacingAPIError as exc:
            if exc.status_code == 422:
                return []          # not on today/tomorrow's cards — this door can't see it
            raise                  # anything else (incl. 404) stays LOUD — see docstring
        return self._result_rows(doc)

    def trainer_ages(self, trainer_id: str) -> list[dict]:
        """The trainer's record BY HORSE AGE — the specialty read (the master,
        2026-07-26: 'if the trainer has an amazing strike rate for his 4-year-old
        chasers this is a HUGE tick'). Honest empty when the plan lacks it."""
        if not trainer_id:
            return []
        doc = self._get(f"/trainers/{trainer_id}/analysis/horse-age", allow_404=True)
        if isinstance(doc, dict):
            rows = doc.get("horse_ages") or doc.get("ages") or doc.get("data") or []
            return rows if isinstance(rows, list) else []
        return doc if isinstance(doc, list) else []

    def trainer_course(self, trainer_id: str, course_id: str = "") -> list[dict]:
        """The trainer's record BY COURSE — rule #10 (the local master) finally gets
        data: win% at THIS track instead of a prose rule. Standard plan and up."""
        if not trainer_id:
            return []
        doc = self._get(f"/trainers/{trainer_id}/analysis/courses", allow_404=True)
        if isinstance(doc, dict):
            for key in ("courses", "analysis", "data", "results"):
                v = doc.get(key)
                if isinstance(v, list):
                    return v
        return doc if isinstance(doc, list) else []

    def jockey_course(self, jockey_id: str) -> list[dict]:
        """The jockey's record BY COURSE — the #30 lens (jockey class at this track).
        Standard plan and up."""
        if not jockey_id:
            return []
        doc = self._get(f"/jockeys/{jockey_id}/analysis/courses", allow_404=True)
        if isinstance(doc, dict):
            for key in ("courses", "analysis", "data", "results"):
                v = doc.get(key)
                if isinstance(v, list):
                    return v
        return doc if isinstance(doc, list) else []

    def horse_distance_times(self, horse_id: str) -> list[dict]:
        """The horse's record BY DISTANCE (win%, times) — the trip lens that has
        printed '—' on every brief. Basic plan and up."""
        if not horse_id:
            return []
        doc = self._get(f"/horses/{horse_id}/analysis/distance-times", allow_404=True)
        if isinstance(doc, dict):
            for key in ("distances", "analysis", "data", "results"):
                v = doc.get(key)
                if isinstance(v, list):
                    return v
        return doc if isinstance(doc, list) else []

    def trainer_jockeys(self, trainer_id: str) -> list[dict]:
        """A trainer's per-jockey record — to identify the stable's number-one
        rider for the jockey-intent read."""
        if not trainer_id:
            return []
        doc = self._get(f"/trainers/{trainer_id}/analysis/jockeys", allow_404=True)
        if isinstance(doc, dict):
            for key in ("jockeys", "analysis", "data", "results"):
                v = doc.get(key)
                if isinstance(v, list):
                    return v
        return doc if isinstance(doc, list) else []


def get_client() -> RacingAPIClient:
    return RacingAPIClient()
