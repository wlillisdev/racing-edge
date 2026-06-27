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
    _MAX_RETRIES = 4
    _BACKOFF = 2.0

    def __init__(self, cfg: Config | None = None) -> None:
        self._cfg = cfg or get_config()
        self._session = requests.Session()
        self._session.auth = (self._cfg.api.username, self._cfg.api.password)  # Basic Auth

    def _get(self, path: str, params: Any = None, allow_404: bool = True) -> Any:
        url = f"{self._cfg.api.base_url}{path}"
        attempt = 0
        while True:
            try:
                resp = self._session.get(url, params=params, timeout=self._TIMEOUT)
                break
            except (ConnectionError, ReadTimeout, Timeout) as exc:
                attempt += 1
                if attempt > self._MAX_RETRIES:
                    raise RacingAPIError(0, url, str(exc)) from exc
                time.sleep(self._BACKOFF * (2 ** (attempt - 1)))
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404 and allow_404:
            return None
        raise RacingAPIError(resp.status_code, url, resp.text[:200])

    # ---- racecards / results ------------------------------------------------
    def racecards(self, day: str = "today") -> dict:
        """Pro racecards for a day. Returns the raw doc (key 'racecards')."""
        regions = [r.strip() for r in self._cfg.api.regions.split(",")]
        params = [("day", day)] + [("region_codes", r) for r in regions]
        return self._get("/racecards/pro", params=params, allow_404=True) or {"racecards": []}

    def results_by_date(self, date_str: str) -> dict:
        params = [("start_date", date_str), ("end_date", date_str), ("limit", 100)]
        return self._get("/results", params=params, allow_404=True) or {"results": []}

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
