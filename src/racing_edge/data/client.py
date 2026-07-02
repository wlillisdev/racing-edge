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
            if resp.status_code == 404 and allow_404:
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
        params = [("date", ds)] + [("region_codes", r) for r in regions]
        return self._get("/racecards/pro", params=params, allow_404=True) or {"racecards": []}

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
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]:
        """A horse's past runs — the raw material for the proven-at-level reads."""
        if not horse_id:
            return []
        doc = self._get(f"/horses/{horse_id}/results", params={"limit": limit}, allow_404=True)
        if isinstance(doc, dict):
            rows = doc.get("results") or doc.get("data") or []
            return rows if isinstance(rows, list) else []
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
