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
class DBConfig:
    host: str
    name: str
    user: str
    password: str
    port: int = 3306


@dataclass(frozen=True)
class Config:
    api: APIConfig
    db: DBConfig
    project_dir: Path


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


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
        db=DBConfig(
            host=_require("DB_HOST"),
            name=_require("DB_NAME"),
            user=_require("DB_USER"),
            password=_require("DB_PASS"),
            port=int(os.environ.get("DB_PORT", "3306")),
        ),
        project_dir=Path(os.environ.get("PROJECT_DIR", str(_PROJECT_ROOT))),
    )
