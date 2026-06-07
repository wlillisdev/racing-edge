"""
api_client.py — Racing API Pro HTTP client.

Design principles
-----------------
- All public methods return safe types (dict, list, None) — callers never
  need to catch network errors for normal flow.
- 404 responses are not errors: results/odds may not yet be available.
- 4xx/5xx responses that are not 404 raise RacingAPIError so the caller
  can distinguish a genuine API fault from "data not yet ready".
- Retry logic is applied to transient connection failures only (not HTTP
  error responses), with exponential backoff.
- Authentication uses Bearer token in the Authorization header, which is
  the scheme documented by The Racing API Pro.
"""

from __future__ import annotations

import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, ReadTimeout, Timeout
from urllib3.util.retry import Retry

from src.config import get_config
from src.helpers import log


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class RacingAPIError(Exception):
    """Raised when the Racing API returns an unexpected 4xx/5xx status."""

    def __init__(self, status_code: int, url: str, message: str = "") -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(
            f"RacingAPI HTTP {status_code} for {url}"
            + (f": {message}" if message else "")
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class RacingAPIClient:
    """Thin wrapper around the Racing API Pro REST endpoints."""

    _TIMEOUT = 30          # seconds per request
    _MAX_RETRIES = 3       # connection-level retries
    _RETRY_BACKOFF = 2.0   # seconds between retries (doubles each attempt)

    def __init__(self, api_key: str, base_url: str, api_password: str = "") -> None:
        if not api_key:
            raise ValueError("RacingAPIClient: api_key must not be empty")
        self._api_key = api_key.strip()
        self._api_password = api_password.strip()
        self._base_url = base_url.rstrip("/")
        self._session = self._build_session()

    # ------------------------------------------------------------------
    # Session / transport
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        """Build a requests Session with a retry-capable HTTP adapter."""
        session = requests.Session()
        # Use Basic Auth (username=api_key, password=api_password) when a
        # password is supplied — The Racing API Pro uses this scheme.
        # Fall back to Bearer token if no password is configured.
        if self._api_password:
            session.auth = (self._api_key, self._api_password)
            session.headers.update({"Accept": "application/json", "User-Agent": "racing-edge/1.0"})
        else:
            session.headers.update(
                {
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "application/json",
                    "User-Agent": "racing-edge/1.0",
                }
            )
        # Retry only on connection-level failures and 429/503 (transient).
        # We do NOT retry on 4xx/5xx in general — those are handled by
        # _get() which raises RacingAPIError.
        retry = Retry(
            total=self._MAX_RETRIES,
            backoff_factor=self._RETRY_BACKOFF,
            status_forcelist=[429, 503],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # ------------------------------------------------------------------
    # Core HTTP helper
    # ------------------------------------------------------------------

    def _get(
        self,
        path: str,
        params: Optional[dict] = None,
        allow_404: bool = True,
    ) -> Optional[dict]:
        """Perform a GET request and return the parsed JSON body.

        Args:
            path: Endpoint path, relative to base URL (e.g. "/racecards/standard").
            params: Query string parameters.
            allow_404: If True, a 404 response returns None instead of raising.

        Returns:
            Parsed JSON dict, or None if the response was 404 and allow_404=True.

        Raises:
            RacingAPIError: For non-404 HTTP errors.
            RacingAPIError: For repeated connection failures after retries.
        """
        url = f"{self._base_url}{path}"
        log(f"GET {url} params={params}")

        attempt = 0
        while True:
            try:
                resp = self._session.get(
                    url,
                    params=params,
                    timeout=self._TIMEOUT,
                )
                break  # successful HTTP exchange (any status)
            except (ConnectionError, ReadTimeout, Timeout) as exc:
                attempt += 1
                if attempt > self._MAX_RETRIES:
                    log(
                        f"RacingAPI: connection failed after {self._MAX_RETRIES} "
                        f"retries for {url} — {exc}",
                        "ERROR",
                    )
                    raise RacingAPIError(0, url, str(exc)) from exc
                wait = self._RETRY_BACKOFF * (2 ** (attempt - 1))
                log(
                    f"RacingAPI: connection error (attempt {attempt}/{self._MAX_RETRIES}), "
                    f"retrying in {wait:.0f}s — {exc}",
                    "WARNING",
                )
                time.sleep(wait)

        # Handle HTTP status codes
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                log(f"RacingAPI: non-JSON 200 response from {url} — {exc}", "ERROR")
                raise RacingAPIError(200, url, "Non-JSON response body") from exc

        if resp.status_code == 404 and allow_404:
            log(f"RacingAPI: 404 for {url} (data not available)", "INFO")
            return None

        # All other error codes
        try:
            detail = resp.json().get("message", resp.text[:200])
        except Exception:
            detail = resp.text[:200]

        log(
            f"RacingAPI: HTTP {resp.status_code} for {url} — {detail}",
            "ERROR",
        )
        raise RacingAPIError(resp.status_code, url, detail)

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_racecards(
        self,
        day: str = "today",
        region_codes: str = "gb,ire",
    ) -> dict:
        """Fetch standard racecards for a given day and region(s).

        Endpoint: GET /racecards/standard

        Args:
            day: "today", "tomorrow", or a date string YYYY-MM-DD.
            region_codes: Comma-separated region codes, e.g. "gb,ire".

        Returns:
            Full racecard response dict (always a dict — empty {"races": []}
            on unexpected None so callers can safely iterate).

        Raises:
            RacingAPIError: On API fault.
        """
        result = self._get(
            "/racecards/standard",
            params={"day": day, "region_codes": region_codes},
            allow_404=False,
        )
        if result is None:
            return {"races": []}
        return result

    def get_horse_results(self, horse_id: str, limit: int = 10) -> list[dict]:
        """Fetch recent results for a specific horse.

        Endpoint: GET /horses/{horse_id}/results

        Args:
            horse_id: The API's internal horse identifier.
            limit: Maximum number of results to request.

        Returns:
            List of result dicts, or [] if horse not found (404) or on error.
        """
        if not horse_id:
            log("get_horse_results: empty horse_id supplied", "WARNING")
            return []

        result = self._get(
            f"/horses/{horse_id}/results",
            params={"limit": limit},
            allow_404=True,
        )
        if result is None:
            return []

        # The API wraps results in a "results" key
        if isinstance(result, dict):
            return result.get("results", result.get("data", []))
        if isinstance(result, list):
            return result
        return []

    def get_race_results(self, race_id: str) -> Optional[dict]:
        """Fetch post-race result for a completed race.

        Endpoint: GET /results/{race_id}

        Args:
            race_id: The API's race identifier.

        Returns:
            Result dict if the race has been run and results are published,
            or None if the race hasn't finished yet (404).

        Raises:
            RacingAPIError: On API fault other than 404.
        """
        if not race_id:
            log("get_race_results: empty race_id supplied", "WARNING")
            return None

        return self._get(f"/results/{race_id}", allow_404=True)

    def get_runner_odds(self, race_id: str) -> Optional[dict]:
        """Fetch live or latest ante-post odds for a race's runners.

        Endpoint: GET /odds/live/{race_id}

        Args:
            race_id: The API's race identifier.

        Returns:
            Odds data dict, or None if not available (race not yet priced /
            odds not published).

        Raises:
            RacingAPIError: On API fault other than 404.
        """
        if not race_id:
            log("get_runner_odds: empty race_id supplied", "WARNING")
            return None

        return self._get(f"/odds/live/{race_id}", allow_404=True)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_client() -> RacingAPIClient:
    """Construct a RacingAPIClient from environment configuration."""
    cfg = get_config()
    return RacingAPIClient(
        api_key=cfg.racing_api_key,
        base_url=cfg.racing_api_base,
        api_password=cfg.racing_api_password,
    )
