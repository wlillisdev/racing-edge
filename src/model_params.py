"""
model_params.py — versioned, tunable model parameters for the learning loop.

The numeric model historically hard-coded its thresholds (NAP_MIN_SCORE, grade
bands, overlay caps, ...). To enable the daily closed-loop learning machine to
recalibrate WITHOUT code edits, those tunables live here with sane DEFAULTS and
can be overridden by a versioned file:

    data/model_params.json

DEFAULTS exactly match the original hard-coded constants, so until the tuner
writes an override file the model behaves precisely as before.

Safety contract (used by the supervised auto-tuner, Stage 5):
    - PARAM_BOUNDS gives a hard (min, max) clamp per tunable — the tuner can
      NEVER push a value outside these, no matter what the learner proposes.
    - PARAM_MAX_STEP gives the largest single-night change per tunable, so the
      model can drift but never lurch.
    - Every applied change is appended to the file's "history" with the evidence
      and is fully reversible (revert_to_version()).

This module performs NO betting logic — it only loads/merges/validates params.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Optional

from src.helpers import data_path, log, safe_load_json, safe_write_json

PARAMS_FILENAME = "model_params.json"

# ---------------------------------------------------------------------------
# Defaults — MUST equal the original hard-coded constants in nap_selector_v3.
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, Any] = {
    "nap_min_score": 50.0,
    "nap_min_odds": 2.0,
    "nap_max_odds": 7.0,
    "form_read_overlay_cap": 3.0,
    "pace_overlay_cap": 2.0,
    "grade_thresholds": {"A": 70.0, "B+": 60.0, "B": 50.0, "C": 40.0},
    "confidence_bands": {"high": 70.0, "medium_high": 60.0, "medium": 55.0, "low_medium": 50.0},
}

# Hard clamps the tuner may never exceed. (scalars only; nested handled below)
PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "nap_min_score": (40.0, 75.0),
    "nap_min_odds": (1.5, 4.0),
    "nap_max_odds": (4.0, 15.0),
    "form_read_overlay_cap": (0.0, 6.0),
    "pace_overlay_cap": (0.0, 5.0),
    "grade_thresholds.A": (60.0, 85.0),
    "grade_thresholds.B+": (50.0, 70.0),
    "grade_thresholds.B": (40.0, 60.0),
    "grade_thresholds.C": (30.0, 50.0),
    "confidence_bands.high": (60.0, 85.0),
    "confidence_bands.medium_high": (52.0, 70.0),
    "confidence_bands.medium": (48.0, 65.0),
    "confidence_bands.low_medium": (40.0, 58.0),
}

# Largest single-night change per tunable (bounded drift, never a lurch).
PARAM_MAX_STEP: dict[str, float] = {
    "nap_min_score": 3.0,
    "nap_min_odds": 0.5,
    "nap_max_odds": 1.0,
    "form_read_overlay_cap": 0.5,
    "pace_overlay_cap": 0.5,
    "grade_thresholds.A": 2.0,
    "grade_thresholds.B+": 2.0,
    "grade_thresholds.B": 2.0,
    "grade_thresholds.C": 2.0,
    "confidence_bands.high": 2.0,
    "confidence_bands.medium_high": 2.0,
    "confidence_bands.medium": 2.0,
    "confidence_bands.low_medium": 2.0,
}

_cache: Optional[dict[str, Any]] = None


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_params(refresh: bool = False) -> dict[str, Any]:
    """Return the effective params (DEFAULTS merged with data/model_params.json).

    Cached for the process lifetime (each pipeline run is a fresh process).
    Only the keys present in DEFAULTS are honoured from the file, so a malformed
    override can add noise but never remove a required tunable.
    """
    global _cache
    if _cache is not None and not refresh:
        return _cache
    file_doc = safe_load_json(data_path(PARAMS_FILENAME)) or {}
    overrides = file_doc.get("params") if isinstance(file_doc, dict) else {}
    if not isinstance(overrides, dict):
        overrides = {}
    merged = _deep_merge(DEFAULTS, overrides)
    # Clamp every value into PARAM_BOUNDS defensively, even on read.
    for dotted, (lo, hi) in PARAM_BOUNDS.items():
        cur = _get_dotted(merged, dotted)
        if isinstance(cur, (int, float)):
            _set_dotted(merged, dotted, max(lo, min(hi, float(cur))))
    _cache = merged
    if overrides:
        ver = file_doc.get("version", "?")
        log(f"model_params: loaded override v{ver} from {PARAMS_FILENAME}")
    return merged


def _get_dotted(d: dict, dotted: str) -> Any:
    cur: Any = d
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set_dotted(d: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = d
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def current_version() -> int:
    doc = safe_load_json(data_path(PARAMS_FILENAME)) or {}
    try:
        return int(doc.get("version", 0)) if isinstance(doc, dict) else 0
    except (TypeError, ValueError):
        return 0


def write_params(params: dict[str, Any], change_note: str, evidence: dict) -> bool:
    """Persist a new params version with an appended, reversible history entry.

    The caller (the supervised tuner) is responsible for having already clamped
    proposed values against PARAM_BOUNDS / PARAM_MAX_STEP; this function records
    the change and bumps the version. Returns True on success.
    """
    existing = safe_load_json(data_path(PARAMS_FILENAME)) or {}
    history = existing.get("history") if isinstance(existing, dict) else None
    if not isinstance(history, list):
        history = []
    new_version = (current_version() or 0) + 1
    history.append({
        "version": new_version,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "change": change_note,
        "evidence": evidence,
        "params": copy.deepcopy(params),
    })
    doc = {
        "version": new_version,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "params": params,
        "history": history[-200:],  # keep the last 200 versions for rollback
    }
    ok = safe_write_json(data_path(PARAMS_FILENAME), doc)
    if ok:
        global _cache
        _cache = None  # force reload next get_params()
        log(f"model_params: wrote v{new_version} — {change_note}")
    return ok


def revert_to_version(version: int) -> bool:
    """Roll the live params back to a prior version from history."""
    existing = safe_load_json(data_path(PARAMS_FILENAME)) or {}
    history = existing.get("history") if isinstance(existing, dict) else []
    target = next((h for h in (history or []) if h.get("version") == version), None)
    if target is None:
        log(f"model_params: cannot revert — version {version} not in history", "WARNING")
        return False
    return write_params(
        target.get("params") or {},
        change_note=f"REVERT to v{version}",
        evidence={"reverted_from": current_version(), "reverted_to": version},
    )


def history() -> list[dict]:
    """Return the full params change history (oldest → newest), or []."""
    doc = safe_load_json(data_path(PARAMS_FILENAME)) or {}
    h = doc.get("history") if isinstance(doc, dict) else None
    return h if isinstance(h, list) else []


def diff_from_defaults() -> list[dict]:
    """Return tunables whose live value differs from DEFAULTS.

    Each item: {param (dotted), default, live}.
    """
    live = get_params(refresh=True)
    out: list[dict] = []
    for dotted in PARAM_BOUNDS:
        dv = _get_dotted(DEFAULTS, dotted)
        lv = _get_dotted(live, dotted)
        if isinstance(dv, (int, float)) and isinstance(lv, (int, float)) and abs(dv - lv) > 1e-9:
            out.append({"param": dotted, "default": dv, "live": lv})
    return out


# ---------------------------------------------------------------------------
# Auto-tune kill-switch (runtime, no code edit needed)
# ---------------------------------------------------------------------------
CONTROL_FILENAME = "learning_control.json"


def is_auto_tune_enabled() -> bool:
    """Runtime kill-switch. Defaults to True when no control file exists."""
    doc = safe_load_json(data_path(CONTROL_FILENAME))
    if not isinstance(doc, dict):
        return True
    return bool(doc.get("auto_tune_enabled", True))


def set_auto_tune_enabled(enabled: bool) -> bool:
    """Flip the runtime auto-tune kill-switch. Returns True on success."""
    doc = {
        "auto_tune_enabled": bool(enabled),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    ok = safe_write_json(data_path(CONTROL_FILENAME), doc)
    if ok:
        log(f"model_params: auto-tune {'ENABLED' if enabled else 'DISABLED'} via control file")
    return ok
