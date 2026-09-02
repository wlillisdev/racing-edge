"""Typed, grouped configuration — loaded lazily, never at import time.

The audits flagged two faults in the old config: a flat bag mixing every
concern, and `get_config()` called at module import (so importing a helper with
an incomplete .env raised KeyError). Here config is grouped, validated, and
resolved only when first asked for.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class APIConfig:
    """The Racing API — HTTP Basic Auth (username + password), never a key."""

    username: str
    password: str
    base_url: str = "https://api.theracingapi.com/v1"
    regions: str = "gb,ire"


@dataclass(frozen=True)
class Config:
    api: APIConfig
    project_dir: Path
    # The ledgers are SQLite under data/ — nap.db (the record), nuances.db (the
    # learning), study.db (old system, dormant); text twin data/nap_record.csv.
    # No MySQL, no DB creds to configure. (audit 2026-09-02: 'ledger.db' was stale)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def racing_creds() -> tuple[str, str]:
    """The Racing API credentials, from .env or the environment — ONE DOOR
    (2026-09-02, the box: night school asked os.environ directly, the
    scheduler's shell never carries .env, so the corpus fetch was SKIPPED
    every night since deployment and the ladder's fav benchmark stayed at
    n=0). Raises RuntimeError when neither holds them."""
    load_dotenv(_PROJECT_ROOT / ".env")
    return _require("RACING_API_USERNAME"), _require("RACING_API_PASSWORD")


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Build Config from the environment (.env at the repo root). Cached."""
    load_dotenv(_PROJECT_ROOT / ".env")
    return Config(
        api=APIConfig(
            username=_require("RACING_API_USERNAME"),
            password=_require("RACING_API_PASSWORD"),
            base_url=os.environ.get("RACING_API_BASE", "https://api.theracingapi.com/v1"),
            regions=os.environ.get("REGIONS", "gb,ire"),
        ),
        project_dir=Path(os.environ.get("PROJECT_DIR", str(_PROJECT_ROOT))),
    )
