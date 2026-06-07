"""
helpers.py — shared utility functions used across all pipeline scripts.

Design principles
-----------------
- Functions are pure or have explicit, logged side-effects.
- File/path helpers create directories automatically so callers never have to.
- JSON helpers never raise on corrupt/missing files — they log and return None.
- All public functions have type annotations.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

from src.config import get_config

# ---------------------------------------------------------------------------
# Internal: resolve PROJECT_DIR once at import time.
# ---------------------------------------------------------------------------
_cfg = get_config()
_PROJECT_DIR = Path(_cfg.project_dir)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Path helpers — create directories on demand
# ---------------------------------------------------------------------------

def _ensure(path: Path) -> str:
    """Create parent directories if they do not exist and return str path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def data_path(filename: str) -> str:
    """Return absolute path to PROJECT_DIR/data/<filename>, creating dirs."""
    return _ensure(_PROJECT_DIR / "data" / filename)


def report_path(filename: str) -> str:
    """Return absolute path to PROJECT_DIR/reports/<filename>, creating dirs."""
    return _ensure(_PROJECT_DIR / "reports" / filename)


def archive_path(filename: str) -> str:
    """Return absolute path to PROJECT_DIR/archive/<filename>, creating dirs."""
    return _ensure(_PROJECT_DIR / "archive" / filename)


def snapshot_path(filename: str) -> str:
    """Return absolute path to PROJECT_DIR/archive/system_snapshots/<filename>."""
    return _ensure(_PROJECT_DIR / "archive" / "system_snapshots" / filename)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str, level: str = "INFO") -> None:
    """Print a timestamped log line to stdout.

    Format: 2025-06-01 14:32:01 [INFO] message
    PythonAnywhere scheduled tasks capture stdout, so this is sufficient
    without adding a heavyweight logging framework.
    """
    from datetime import datetime

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [{level.upper()}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def safe_load_json(path: str) -> Optional[dict]:
    """Load JSON from *path*.

    Returns:
        Parsed dict on success.
        None if the file does not exist or is corrupt — logs a WARNING in
        both cases so the caller always gets a visible signal.
    """
    p = Path(path)
    if not p.exists():
        log(f"safe_load_json: file not found — {path}", "WARNING")
        return None
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        log(f"safe_load_json: corrupt JSON in {path} — {exc}", "WARNING")
        return None
    except OSError as exc:
        log(f"safe_load_json: OS error reading {path} — {exc}", "WARNING")
        return None


def safe_write_json(path: str, data: dict) -> bool:
    """Serialise *data* as indented JSON and write to *path*.

    Creates parent directories automatically.

    Returns:
        True on success, False on any write error (logs ERROR).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        return True
    except (OSError, TypeError, ValueError) as exc:
        log(f"safe_write_json: failed to write {path} — {exc}", "ERROR")
        return False


# ---------------------------------------------------------------------------
# Odds formatting
# ---------------------------------------------------------------------------

# Common fractional equivalents (decimal -> fractional string).
# Ordered so that the closest match wins for non-standard prices.
_COMMON_FRACTIONS: list[tuple[float, str]] = [
    (1.10, "1/10"),
    (1.14, "1/7"),
    (1.17, "1/6"),
    (1.20, "1/5"),
    (1.25, "1/4"),
    (1.33, "1/3"),
    (1.40, "2/5"),
    (1.44, "4/9"),
    (1.50, "1/2"),
    (1.57, "4/7"),
    (1.62, "5/8"),
    (1.67, "4/6"),
    (1.72, "8/11"),
    (1.80, "4/5"),
    (1.90, "9/10"),
    (2.00, "Evs"),
    (2.10, "11/10"),
    (2.20, "6/5"),
    (2.25, "5/4"),
    (2.33, "11/8"),  # actually 2.375 but bookmaker shorthand
    (2.38, "11/8"),
    (2.50, "6/4"),
    (2.62, "13/8"),
    (2.75, "7/4"),
    (3.00, "2/1"),
    (3.25, "9/4"),
    (3.50, "5/2"),
    (3.75, "11/4"),
    (4.00, "3/1"),
    (4.50, "7/2"),
    (5.00, "4/1"),
    (5.50, "9/2"),
    (6.00, "5/1"),
    (6.50, "11/2"),
    (7.00, "6/1"),
    (7.50, "13/2"),
    (8.00, "7/1"),
    (9.00, "8/1"),
    (10.00, "9/1"),
    (11.00, "10/1"),
    (12.00, "11/1"),
    (13.00, "12/1"),
    (14.00, "13/1"),
    (15.00, "14/1"),
    (16.00, "15/1"),
    (17.00, "16/1"),
    (21.00, "20/1"),
    (26.00, "25/1"),
    (34.00, "33/1"),
    (41.00, "40/1"),
    (51.00, "50/1"),
    (67.00, "66/1"),
    (101.00, "100/1"),
]


def format_odds(sp_dec: float) -> str:
    """Convert a decimal odds value to a fractional display string.

    Examples:
        4.5  -> "7/2"
        3.0  -> "2/1"
        2.0  -> "Evs"
        1.5  -> "1/2"
        10.0 -> "9/1"

    For prices not in the lookup table the nearest common fraction is used.
    If *sp_dec* is <= 1.0 (invalid) returns "N/A".
    """
    if sp_dec is None or sp_dec <= 1.0:
        return "N/A"

    best_label = "N/A"
    best_diff = math.inf
    for dec_val, label in _COMMON_FRACTIONS:
        diff = abs(sp_dec - dec_val)
        if diff < best_diff:
            best_diff = diff
            best_label = label

    # If we are within 0.05 of a known price, use the label.
    # Otherwise, express as an integer fraction (e.g. "23/1").
    if best_diff <= 0.07:
        return best_label

    # Generic fallback: numerator / 1 for round integers
    numerator = round(sp_dec - 1)
    return f"{numerator}/1"


# ---------------------------------------------------------------------------
# Going normalisation
# ---------------------------------------------------------------------------

# Map of lowercased substrings/patterns to canonical going description.
# Evaluated in order — more specific patterns first.
_GOING_RULES: list[tuple[str, str]] = [
    # All-weather surfaces
    ("standard to slow", "Slow"),
    ("slow",             "Slow"),
    ("standard",         "Standard"),
    ("fast",             "Standard"),  # AW "fast" ~ standard
    # Turf going — compound first
    ("good to firm",     "Good to Firm"),
    ("good to soft",     "Good to Soft"),
    ("soft to heavy",    "Heavy"),
    ("heavy",            "Heavy"),
    ("firm",             "Firm"),
    ("good",             "Good"),
    ("soft",             "Soft"),
    ("yielding to soft", "Soft"),
    ("yielding",         "Good to Soft"),  # Irish equivalent
    ("hard",             "Firm"),
]


def going_normalise(going_str: str) -> str:
    """Normalise a raw going description to a canonical value.

    Canonical values: Firm | Good to Firm | Good | Good to Soft |
                      Soft | Heavy | Standard | Slow

    Unknown/empty strings are returned as-is so the caller can decide
    how to handle them rather than silently masking the raw value.
    """
    if not going_str:
        return going_str

    normalised = going_str.strip().lower()
    # Strip parenthetical qualifiers like "(watered)"
    normalised = re.sub(r"\(.*?\)", "", normalised).strip()

    for pattern, canonical in _GOING_RULES:
        if pattern in normalised:
            return canonical

    # Return the title-cased original if no rule matched so it at least
    # looks consistent in output.
    return going_str.strip().title()


# ---------------------------------------------------------------------------
# Distance conversion
# ---------------------------------------------------------------------------

_DIST_RE = re.compile(
    r"(?:(\d+)m)?\s*(?:(\d+)f)?\s*(?:(\d+)y)?",
    re.IGNORECASE,
)


def distance_to_furlongs(dist_str: str) -> float:
    """Convert a British-format distance string to furlongs (float).

    Supported formats:
        "5f"        ->  5.0
        "6f"        ->  6.0
        "1m"        ->  8.0
        "1m2f"      -> 10.0
        "1m4f"      -> 12.0
        "1m4f50y"   -> 12.227...  (yards converted at 220 yds/furlong)
        "2m"        -> 16.0
        "2m4f"      -> 20.0

    Returns 0.0 for unparseable strings (logs a warning).
    """
    if not dist_str:
        log(f"distance_to_furlongs: empty distance string", "WARNING")
        return 0.0

    cleaned = dist_str.strip().lower().replace(" ", "")
    m = _DIST_RE.fullmatch(cleaned)
    if not m:
        log(f"distance_to_furlongs: unrecognised format '{dist_str}'", "WARNING")
        return 0.0

    miles_part, furlongs_part, yards_part = m.groups()
    miles     = int(miles_part)   if miles_part   else 0
    furlongs  = int(furlongs_part) if furlongs_part else 0
    yards     = int(yards_part)   if yards_part   else 0

    total = miles * 8.0 + furlongs + yards / 220.0

    if total == 0.0:
        log(f"distance_to_furlongs: parsed zero furlongs from '{dist_str}'", "WARNING")

    return round(total, 4)
