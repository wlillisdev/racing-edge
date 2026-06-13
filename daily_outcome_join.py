"""
daily_outcome_join.py — Stage 2 of the daily closed-loop learning machine:
the OUTCOME-JOIN that labels every prediction against the actual race result
and accumulates a growing, model-trainable dataset.

What this stage does
--------------------
The nap_selector writes data/predictions_<date>.json (one row per ranked
runner per race). After the races are run and results are published, this
stage:

  1. Loads the predictions for a date (default today, or pass a date arg —
     "yesterday" is supported, since results need to exist).
  2. For every distinct race_id, calls the Racing API
     `client.get_race_results(race_id)` to fetch the finishing order and
     builds a per-horse outcome map (finishing position, won, placed,
     starting price).
  3. JOINs each prediction row to its outcome — attaching
     won / placed / finish_position / sp_decimal (None when a horse cannot
     be matched, e.g. a non-runner) plus a realised P&L figure to a flat
     1pt win stake at SP (won -> sp_decimal - 1, else -1).
  4. Writes data/labelled_<date>.json (predictions enriched with outcomes
     plus a summary).
  5. APPENDS one row per labelled runner to the cumulative
     data/learning_dataset.csv — the growing training corpus. This append
     is idempotent: rows for a (date, race_id, horse_id) already present
     are never duplicated.

Graceful behaviour
------------------
If results are not available yet for a race (get_race_results returns
None/empty), the row is still emitted with null outcomes and the race is
counted as unresolved — the script returns 0 so the evening pipeline keeps
moving and a later re-run can fill the gaps. Exit 1 is reserved for an
actual write failure.

Result field names (derived, not guessed)
-----------------------------------------
The exact shape of `client.get_race_results(race_id)` is taken from
result_enricher.py (_extract_winner / _classify_pace) and src/api_client.py:
  - The finishers list lives under one of: "results" | "runners" | "data".
  - Each finisher exposes a finishing position under one of:
      "position" | "finish_position" | "pos"   (e.g. "1", "2", or non-completion
      codes like F/U/P/PU which we treat as "did not place").
  - The runner identity comes from "horse_id" (joined on), with
      "horse" | "horse_name" as a human-readable fallback.
  - The starting price (decimal) comes from one of:
      "sp_dec" | "sp" | "starting_price_dec".
  - A pre-computed place flag, when present, is read from "placed" / "is_placed";
    otherwise a field-size rule is applied (top 3 if field >= 8 else top 2).

Inputs
------
    data/predictions_<date>.json   (from nap_selector_v3.py)

Outputs
-------
    data/labelled_<date>.json      (predictions + outcomes + summary)
    data/learning_dataset.csv      (cumulative, appended idempotently)

Exit codes
----------
    0  — success (including "results not ready yet" / "no predictions yet")
    1  — write failure (labelled JSON or CSV could not be written)

Pipeline integration (DOCUMENTED — not implemented here)
--------------------------------------------------------
This stage belongs in evening_audit_pipeline.py's PIPELINE_STEPS, inserted
AFTER results_auditor (so the results it depends on have been fetched) and
BEFORE loser_autopsy_ai and any downstream learning analysis (which want the
labelled dataset). Concretely, the PIPELINE_STEPS list would become:

    PIPELINE_STEPS = [
        ("results_auditor",     "results_auditor.py",     []),
        ("performance_tracker", "performance_tracker.py", []),
        ("daily_outcome_join",  "daily_outcome_join.py",  []),   # <-- insert here
        ("loser_autopsy_ai",    "loser_autopsy_ai.py",    []),
        ("profit_report",       "profit_report.py",       []),
        ("email_audit",         "email_audit.py",         []),
    ]

Note: evening_audit_pipeline.py is read-only for this worker — the change
above is documentation for the orchestrator to apply, not done here.
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.helpers import (
    data_path,
    log,
    safe_load_json,
    safe_write_json,
    today_str,
)
from src.api_client import get_client, RacingAPIError


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Placed rule when the API does not give an explicit place flag:
#   top 3 if the field is large (>= this size) else top 2.
LARGE_FIELD_FOR_TOP3: int = 8

# Position field aliases on a finisher row.
_POSITION_KEYS: tuple[str, ...] = ("position", "finish_position", "pos")
# Starting-price (decimal) aliases on a finisher row.
_SP_KEYS: tuple[str, ...] = ("sp_dec", "sp", "starting_price_dec")
# Explicit place-flag aliases on a finisher row (used if present).
_PLACE_FLAG_KEYS: tuple[str, ...] = ("placed", "is_placed")
# Keys under which the API may nest the list of finishers.
_FINISHER_LIST_KEYS: tuple[str, ...] = ("results", "runners", "data")

# Stable column order for the cumulative learning dataset CSV.
CSV_COLUMNS: list[str] = [
    "date",
    "race_id",
    "course",
    "race_type",
    "going",
    "distance_f",
    "horse_id",
    "horse",
    "rank_in_race",
    "score",
    "grade",
    "form_score",
    "suitability_score",
    "context_score",
    "draw_score",
    "trainer_score",
    "market_score",
    "wisdom_score",
    "ai_rating",
    "pace_fit",
    "morning_price",
    "is_nap",
    "finish_position",
    "won",
    "placed",
    "sp_decimal",
    "pnl_1pt",
    # Provenance: "live" (evening join, full scorer with AI/full_form overlays)
    # vs "backfill" (historical replay on the degraded scorer). The two score
    # distributions are NOT comparable, so the learner restricts score-sensitive
    # proposals to live rows. Legacy rows (pre-column) read as "" = unknown.
    "source",
]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# Position codes that mean the horse never took part — the stake is returned,
# so the row must be VOID (all-None outcomes), not a 1pt loss.
_VOID_CODES: frozenset[str] = frozenset({"nr", "ns", "wd", "w", "void", "voi", "abd"})
# Position codes for a horse that ran but did not complete (fell, unseated,
# pulled up, brought down, ran out, slipped up, refused, carried out). The
# stake IS lost — a genuine 1pt losing bet.
_LOSS_CODES: frozenset[str] = frozenset({"f", "u", "ur", "p", "pu", "bd", "ro", "su", "r", "ref", "co"})


def _parse_position(raw: object) -> Optional[int]:
    """Parse a finishing position to int.

    Handles "1", "1st", "2nd", "10", and dead-heat notations ("1=", "=1",
    "1 dh"). Non-completion codes (F/U/P/PU/BD/RO etc.), non-runner codes and
    blanks return None — use _position_kind() to tell those cases apart.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Leading digits (after an optional dead-heat "="): "1st"->1, "1="->1, "=2"->2.
    m = re.match(r"^=?\s*(\d+)", s)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _position_kind(raw: object) -> str:
    """Classify a raw position value: 'finished' | 'loss' | 'void' | 'unknown'.

    'loss'  — ran but didn't complete (fell/pulled up/...): a real 1pt loss.
    'void'  — never took part (non-runner/withdrawn): stake returned, no bet.
    'unknown' — blank or unrecognised: outcome cannot be labelled.
    """
    if _parse_position(raw) is not None:
        return "finished"
    s = str(raw or "").strip().lower().rstrip(".")
    if not s:
        return "unknown"
    if s in _VOID_CODES:
        return "void"
    if s in _LOSS_CODES:
        return "loss"
    return "unknown"


def _parse_sp(raw: object) -> Optional[float]:
    """Parse a decimal starting price; reject values <= 1.0 as invalid."""
    if raw is None:
        return None
    try:
        sp = float(raw)
    except (ValueError, TypeError):
        return None
    return sp if sp > 1.0 else None


def _first_present(row: dict, keys: tuple[str, ...]) -> object:
    """Return the first non-None value across *keys* in *row*."""
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k)
    return None


def _extract_finishers(api_result: Optional[dict]) -> list[dict]:
    """Pull the finishers list from a get_race_results() response."""
    if not isinstance(api_result, dict):
        return []
    for key in _FINISHER_LIST_KEYS:
        val = api_result.get(key)
        if isinstance(val, list) and val:
            return val
    return []


def _explicit_place_flag(row: dict) -> Optional[bool]:
    """Return an explicit place flag if the API provides one, else None."""
    for k in _PLACE_FLAG_KEYS:
        if k in row and row.get(k) is not None:
            v = row.get(k)
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            if s in ("true", "1", "yes", "y"):
                return True
            if s in ("false", "0", "no", "n", ""):
                return False
    return None


def _build_outcome_map(api_result: Optional[dict]) -> dict[str, dict]:
    """Build {horse_id -> outcome dict} for one race.

    Each outcome dict: {finish_position, won, placed, sp_decimal}.
    Returns {} when no usable finishers are present (race unresolved).
    """
    finishers = _extract_finishers(api_result)
    if not finishers:
        return {}

    field_size = len(finishers)
    place_cutoff = 3 if field_size >= LARGE_FIELD_FOR_TOP3 else 2

    outcome_map: dict[str, dict] = {}
    for row in finishers:
        if not isinstance(row, dict):
            continue
        horse_id = str(row.get("horse_id") or "").strip()
        if not horse_id:
            continue

        raw_pos = _first_present(row, _POSITION_KEYS)
        kind = _position_kind(raw_pos)
        # Void (non-runner/withdrawn) and unknown codes are NOT labelled: a
        # void bet returns the stake, and an unknown code can't be priced.
        # Leaving them out of the map yields all-None outcomes downstream —
        # previously both were silently counted as 1pt losses, biasing every
        # ROI figure the learner sees downward.
        if kind in ("void", "unknown"):
            continue

        pos = _parse_position(raw_pos)
        sp = _parse_sp(_first_present(row, _SP_KEYS))

        won = pos == 1
        explicit = _explicit_place_flag(row)
        if explicit is not None:
            placed = explicit
        else:
            placed = pos is not None and pos <= place_cutoff

        outcome_map[horse_id] = {
            "finish_position": pos,
            "won": won,
            "placed": placed,
            "sp_decimal": sp,
        }

    return outcome_map


def _pnl_1pt(won: bool, sp_decimal: Optional[float]) -> Optional[float]:
    """Realised P&L for a flat 1pt win stake at SP.

    won -> sp_decimal - 1 (profit), else -1 (lost stake). Returns None when
    SP is missing — for winners AND losers. A loser's -1 doesn't need the SP,
    but counting SP-less losers while excluding SP-less winners (the old
    behaviour) systematically biased every ROI average downward; missing-SP
    rows are excluded symmetrically instead.
    """
    if sp_decimal is None:
        return None
    if won:
        return round(sp_decimal - 1.0, 4)
    return -1.0


# ---------------------------------------------------------------------------
# Date resolution
# ---------------------------------------------------------------------------

def _resolve_date(arg: Optional[str]) -> str:
    """Resolve the date argument to a YYYY-MM-DD string.

    Accepts: None/"today" -> today; "yesterday" -> today-1; or an explicit
    YYYY-MM-DD string (returned as-is).
    """
    if arg is None or arg.strip().lower() == "today":
        return today_str()
    if arg.strip().lower() == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    return arg.strip()


# ---------------------------------------------------------------------------
# CSV append (idempotent)
# ---------------------------------------------------------------------------

def _row_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("date") or ""),
        str(row.get("race_id") or ""),
        str(row.get("horse_id") or ""),
    )


def _has_outcome(row: dict) -> bool:
    """True if the row carries a usable `won` label (str or bool form)."""
    v = row.get("won")
    if v is None:
        return False
    return str(v).strip() != ""


def _read_existing_rows(csv_path: str) -> tuple[list[dict], bool]:
    """Read all existing CSV rows. Returns (rows, header_current).

    header_current is False when the file's header differs from CSV_COLUMNS
    (e.g. a column was added since the file was created) — the caller must
    rewrite rather than append, or the new rows would be ragged.
    """
    p = Path(csv_path)
    if not p.exists():
        return [], True
    rows: list[dict] = []
    header_current = True
    try:
        with open(p, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            header_current = reader.fieldnames == CSV_COLUMNS
            for row in reader:
                rows.append(row)
    except OSError as exc:
        log(f"daily_outcome_join: could not read existing CSV {csv_path} — {exc}", "WARNING")
    return rows, header_current


def _append_csv(csv_path: str, labelled_rows: list[dict]) -> tuple[bool, int]:
    """Append labelled rows to the cumulative CSV, upserting late results.

    De-dups by (date, race_id, horse_id). A key already present with NULL
    outcomes is REPLACED when the new row carries an outcome — so a re-run
    after late-published results genuinely fills the gaps (previously the
    dedup froze the null row forever, contradicting the module docstring).
    Returns (success, rows_appended_or_updated).
    """
    p = Path(csv_path)
    existing_rows, header_current = _read_existing_rows(csv_path)
    by_key: dict[tuple[str, str, str], int] = {
        _row_key(r): i for i, r in enumerate(existing_rows)
    }

    to_append: list[dict] = []
    replaced = 0
    seen_this_run: set[tuple[str, str, str]] = set()
    for row in labelled_rows:
        key = _row_key(row)
        if key in seen_this_run:
            continue
        seen_this_run.add(key)
        projected = {col: row.get(col) for col in CSV_COLUMNS}
        idx = by_key.get(key)
        if idx is not None:
            old = existing_rows[idx]
            if not _has_outcome(old) and _has_outcome(projected):
                existing_rows[idx] = projected
                replaced += 1
            continue
        to_append.append(projected)

    if not to_append and not replaced:
        log("daily_outcome_join: CSV already up to date for this date — nothing appended")
        return True, 0

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if replaced or (existing_rows and not header_current):
            # Rewrite atomically: null-outcome rows were updated in place, or
            # the on-disk header is stale (a column was added since the file
            # was created) — appending to a stale header writes ragged rows.
            # The rewrite migrates everything to the current CSV_COLUMNS.
            tmp = p.with_suffix(".csv.tmp")
            with open(tmp, "w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
                writer.writeheader()
                for row in existing_rows:
                    writer.writerow({col: row.get(col) for col in CSV_COLUMNS})
                for row in to_append:
                    writer.writerow(row)
            tmp.replace(p)
            log(f"daily_outcome_join: updated {replaced} null-outcome row(s) with late results")
        else:
            file_exists = p.exists()
            with open(p, "a", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
                if not file_exists:
                    writer.writeheader()
                for row in to_append:
                    writer.writerow(row)
    except OSError as exc:
        log(f"daily_outcome_join: failed to write CSV {csv_path} — {exc}", "ERROR")
        return False, 0

    return True, len(to_append) + replaced


# ---------------------------------------------------------------------------
# Join
# ---------------------------------------------------------------------------

def _label_prediction(pred: dict, outcome_map: dict[str, dict]) -> dict:
    """Return a labelled copy of a prediction row joined to its outcome.

    All original prediction fields are preserved; outcome fields and the
    realised P&L are attached. Unmatched horses get null outcomes.
    """
    labelled = dict(pred)
    horse_id = str(pred.get("horse_id") or "").strip()
    outcome = outcome_map.get(horse_id)

    if outcome is None:
        labelled["finish_position"] = None
        labelled["won"] = None
        labelled["placed"] = None
        labelled["sp_decimal"] = None
        labelled["pnl_1pt"] = None
    else:
        won = bool(outcome.get("won"))
        sp = outcome.get("sp_decimal")
        labelled["finish_position"] = outcome.get("finish_position")
        labelled["won"] = won
        labelled["placed"] = bool(outcome.get("placed"))
        labelled["sp_decimal"] = sp
        labelled["pnl_1pt"] = _pnl_1pt(won, sp)

    return labelled


def _csv_row_from_labelled(date_str: str, row: dict) -> dict:
    """Project a labelled prediction onto the stable CSV column set."""
    return {
        "date": date_str,
        "race_id": row.get("race_id"),
        "course": row.get("course"),
        "race_type": row.get("race_type"),
        "going": row.get("going"),
        "distance_f": row.get("distance_f"),
        "horse_id": row.get("horse_id"),
        "horse": row.get("horse"),
        "rank_in_race": row.get("rank_in_race"),
        "score": row.get("score"),
        "grade": row.get("grade"),
        "form_score": row.get("form_score"),
        "suitability_score": row.get("suitability_score"),
        "context_score": row.get("context_score"),
        "draw_score": row.get("draw_score"),
        "trainer_score": row.get("trainer_score"),
        "market_score": row.get("market_score"),
        "wisdom_score": row.get("wisdom_score"),
        "ai_rating": row.get("ai_rating"),
        "pace_fit": row.get("pace_fit"),
        "morning_price": row.get("morning_price"),
        # Normalised to int 1/0 — the live path historically wrote bool
        # ("True"/"False" in CSV) while the backfill wrote 1/0 for a different
        # notion of NAP. One literal form keeps the learner's parsing trivial.
        "is_nap": int(bool(row.get("is_nap"))),
        "finish_position": row.get("finish_position"),
        "won": row.get("won"),
        "placed": row.get("placed"),
        "sp_decimal": row.get("sp_decimal"),
        "pnl_1pt": row.get("pnl_1pt"),
        "source": "live",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the outcome-join stage. Returns exit code (0 success, 1 write error)."""
    log("daily_outcome_join.py started")

    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    date_str = _resolve_date(date_arg)
    now = datetime.now(timezone.utc)
    log(f"daily_outcome_join: date={date_str}")

    # ------------------------------------------------------------------
    # 1. Load predictions
    # ------------------------------------------------------------------
    predictions_path = data_path(f"predictions_{date_str}.json")
    predictions_doc: Optional[dict] = safe_load_json(predictions_path)

    if predictions_doc is None:
        log(
            f"daily_outcome_join: no predictions file at {predictions_path} — "
            "nothing to label yet.",
            "WARNING",
        )
        return 0

    predictions: list[dict] = predictions_doc.get("predictions") or []
    if not predictions:
        log("daily_outcome_join: predictions file has no prediction rows.", "WARNING")
        # Still emit an (empty) labelled doc so downstream stages see the date.
        empty_doc = {
            "date": date_str,
            "labelled_at": now.isoformat(),
            "model_version": predictions_doc.get("model_version", ""),
            "summary": {
                "races_resolved": 0,
                "races_unresolved": 0,
                "runners_labelled": 0,
                "winners": 0,
            },
            "unresolved_races": [],
            "predictions": [],
        }
        json_dest = data_path(f"labelled_{date_str}.json")
        if not safe_write_json(json_dest, empty_doc):
            log(f"daily_outcome_join: failed to write {json_dest}", "ERROR")
            return 1
        log(f"daily_outcome_join: empty labelled doc written → {json_dest}")
        return 0

    # ------------------------------------------------------------------
    # 2. Collect distinct race IDs
    # ------------------------------------------------------------------
    race_ids: list[str] = []
    seen: set[str] = set()
    for p in predictions:
        rid = str(p.get("race_id") or "").strip()
        if rid and rid not in seen:
            seen.add(rid)
            race_ids.append(rid)

    log(
        f"daily_outcome_join: {len(predictions)} predictions across "
        f"{len(race_ids)} race(s)"
    )

    # ------------------------------------------------------------------
    # 3. Fetch results and build per-race outcome maps
    # ------------------------------------------------------------------
    client = get_client()
    outcome_maps: dict[str, dict[str, dict]] = {}
    unresolved_races: list[str] = []

    for race_id in race_ids:
        api_result: Optional[dict] = None
        try:
            api_result = client.get_race_results(race_id)
        except RacingAPIError as exc:
            log(
                f"daily_outcome_join: API error for race {race_id} — {exc}; "
                "treating as unresolved.",
                "WARNING",
            )
            api_result = None

        outcome_map = _build_outcome_map(api_result)
        outcome_maps[race_id] = outcome_map
        if not outcome_map:
            unresolved_races.append(race_id)
            log(
                f"daily_outcome_join: results not yet available for race {race_id} "
                "— labelling with null outcomes.",
                "WARNING",
            )
        else:
            log(
                f"daily_outcome_join: resolved race {race_id} "
                f"({len(outcome_map)} finishers)"
            )

    # ------------------------------------------------------------------
    # 4. Join every prediction to its outcome
    # ------------------------------------------------------------------
    labelled_predictions: list[dict] = []
    for pred in predictions:
        rid = str(pred.get("race_id") or "").strip()
        outcome_map = outcome_maps.get(rid, {})
        labelled_predictions.append(_label_prediction(pred, outcome_map))

    races_resolved = len(race_ids) - len(unresolved_races)
    runners_labelled = sum(
        1 for r in labelled_predictions if r.get("finish_position") is not None
    )
    winners = sum(1 for r in labelled_predictions if r.get("won") is True)

    # ------------------------------------------------------------------
    # 5. Write labelled JSON
    # ------------------------------------------------------------------
    labelled_doc: dict = {
        "date": date_str,
        "labelled_at": now.isoformat(),
        "model_version": predictions_doc.get("model_version", ""),
        "summary": {
            "races_total": len(race_ids),
            "races_resolved": races_resolved,
            "races_unresolved": len(unresolved_races),
            "runners_labelled": runners_labelled,
            "winners": winners,
        },
        "unresolved_races": unresolved_races,
        "predictions": labelled_predictions,
    }

    json_dest = data_path(f"labelled_{date_str}.json")
    if not safe_write_json(json_dest, labelled_doc):
        log(f"daily_outcome_join: failed to write labelled JSON {json_dest}", "ERROR")
        return 1
    log(f"daily_outcome_join: labelled JSON saved → {json_dest}")

    # ------------------------------------------------------------------
    # 6. Append to cumulative learning dataset CSV (idempotent)
    # ------------------------------------------------------------------
    csv_path = data_path("learning_dataset.csv")
    csv_rows = [_csv_row_from_labelled(date_str, r) for r in labelled_predictions]
    ok, appended = _append_csv(csv_path, csv_rows)
    if not ok:
        log(f"daily_outcome_join: failed to append learning dataset {csv_path}", "ERROR")
        return 1
    log(f"daily_outcome_join: appended {appended} row(s) to {csv_path}")

    # ------------------------------------------------------------------
    # 7. Console summary
    # ------------------------------------------------------------------
    summary = (
        f"daily_outcome_join: COMPLETE — date={date_str}, "
        f"races_resolved={races_resolved}/{len(race_ids)}, "
        f"runners_labelled={runners_labelled}, winners={winners}, "
        f"csv_appended={appended}"
    )
    if unresolved_races:
        summary += f", unresolved={len(unresolved_races)}"
    log(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
