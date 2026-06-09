"""
model_param_tuner.py — Stage 5: supervised auto-tuner for the learning loop.

Consumes the nightly learner's proposals (data/proposed_params_<date>.json) and
applies model-parameter changes under a strict safety gate. This is the only
component permitted to mutate the live betting model, so every guard matters.

Autonomy mode: SUPERVISED AUTO-TUNE (the operator's chosen policy)
    - AUTO-APPLY a change only when ALL gates pass:
        * the proposal's sample_size >= MIN_SAMPLE_AUTO
        * its confidence clears MIN_CONFIDENCE_AUTO (numeric or HIGH/MED-HIGH)
        * the move, after clamping, is within src.model_params.PARAM_MAX_STEP
          (bounded drift — never a lurch) and inside PARAM_BOUNDS
        * no more than MAX_CHANGES_PER_NIGHT are applied (the strongest first)
    - Everything else is DEFERRED to a review file, never silently applied.
    - Every applied change is versioned with its evidence (src.model_params
      .write_params) and is reversible (revert_to_version).
    - A single switch (AUTO_APPLY_ENABLED) downgrades the whole stage to
      propose/review-only without touching the model.

Inputs:
    data/proposed_params_<date>.json  (from daily_learning_analysis.py)
        { date, window_days, sample_size, proposals: [
            { target, current_value, proposed_value, direction,
              sample_size, rationale, confidence }, ... ] }

Outputs:
    data/model_params.json            (updated + versioned ONLY when a change applies)
    reports/param_tuning_<date>.txt   (applied / deferred / rejected, always written)

Integration (documentation only):
    evening_audit_pipeline.py PIPELINE_STEPS — add AFTER daily_learning_analysis:
        ("model_param_tuner",  "model_param_tuner.py",   []),
    so the order is: results_auditor -> daily_outcome_join -> performance_tracker
    -> loser_autopsy_ai -> daily_learning_analysis -> model_param_tuner ->
    profit_report -> email_audit.

Exit codes:
    0 — success, INCLUDING "nothing to apply" and AUTO_APPLY disabled.
    1 — only on a write error.
"""

from __future__ import annotations

import copy
import sys
from datetime import datetime, timezone

from src.helpers import data_path, log, report_path, safe_load_json, today_str
from src.model_params import (
    get_params, write_params, current_version, is_auto_tune_enabled,
    PARAM_BOUNDS, PARAM_MAX_STEP,
)

# ---------------------------------------------------------------------------
# Safety gates (supervised auto-tune)
# ---------------------------------------------------------------------------
AUTO_APPLY_ENABLED: bool = True   # flip to False for propose/review-only
MIN_SAMPLE_AUTO: int = 50         # labelled rows behind a proposal to auto-apply
MIN_CONFIDENCE_AUTO: float = 0.60 # 0-1 scale (or HIGH/MEDIUM-HIGH strings)
MAX_CHANGES_PER_NIGHT: int = 2    # cap simultaneous changes — drift, not lurch


def _get_dotted(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set_dotted(d: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = d
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _confidence_ok(conf) -> bool:
    """Accept a numeric confidence (0-1 or 0-100) or a label."""
    if isinstance(conf, (int, float)):
        c = float(conf)
        c = c / 100.0 if c > 1.0 else c
        return c >= MIN_CONFIDENCE_AUTO
    if isinstance(conf, str):
        return conf.strip().upper() in ("HIGH", "MEDIUM-HIGH", "MEDIUM_HIGH")
    return False


def _evaluate(proposal: dict, live: dict) -> dict:
    """Decide APPLY / DEFER / REJECT for one proposal and compute the clamped value.

    Returns a verdict dict: {target, decision, reason, current, clamped_value,
    sample_size, confidence}.
    """
    target = str(proposal.get("target") or "")
    bounds = PARAM_BOUNDS.get(target)
    step = PARAM_MAX_STEP.get(target)
    current = _get_dotted(live, target)

    base = {
        "target": target,
        "current": current,
        "sample_size": proposal.get("sample_size"),
        "confidence": proposal.get("confidence"),
        "rationale": proposal.get("rationale", ""),
    }

    if bounds is None or step is None:
        return {**base, "decision": "REJECT", "reason": "unknown/untunable target", "clamped_value": current}
    if not isinstance(current, (int, float)):
        return {**base, "decision": "REJECT", "reason": "current value not numeric", "clamped_value": current}
    try:
        proposed = float(proposal.get("proposed_value"))
    except (TypeError, ValueError):
        return {**base, "decision": "REJECT", "reason": "proposed_value not numeric", "clamped_value": current}

    # Clamp the MOVE to PARAM_MAX_STEP, then clamp the RESULT to PARAM_BOUNDS.
    lo, hi = bounds
    move = max(-step, min(step, proposed - float(current)))
    clamped = max(lo, min(hi, float(current) + move))
    base["clamped_value"] = round(clamped, 4)

    if abs(clamped - float(current)) < 1e-9:
        return {**base, "decision": "REJECT", "reason": "no effective change after clamping"}

    sample = proposal.get("sample_size")
    try:
        sample_ok = int(sample) >= MIN_SAMPLE_AUTO
    except (TypeError, ValueError):
        sample_ok = False

    if not sample_ok:
        return {**base, "decision": "DEFER", "reason": f"sample {sample} < {MIN_SAMPLE_AUTO}"}
    if not _confidence_ok(proposal.get("confidence")):
        return {**base, "decision": "DEFER", "reason": "confidence below auto-apply threshold"}
    return {**base, "decision": "APPLY", "reason": "passed all gates"}


def _write_report(date_str: str, verdicts: list[dict], applied: list[dict], new_version) -> bool:
    sep = "=" * 60
    lines = [
        sep, "  MODEL PARAMETER TUNING — SUPERVISED AUTO-TUNE", f"  Date: {date_str}",
        f"  Auto-apply: {'ENABLED' if AUTO_APPLY_ENABLED else 'DISABLED (review-only)'}",
        f"  Gates: sample>={MIN_SAMPLE_AUTO}, confidence>={MIN_CONFIDENCE_AUTO}, "
        f"max {MAX_CHANGES_PER_NIGHT}/night, step-bounded", sep, "",
    ]
    if applied:
        lines.append(f"■ APPLIED ({len(applied)}) — params now at v{new_version}")
        for v in applied:
            lines.append(f"  • {v['target']}: {v['current']} → {v['clamped_value']} "
                         f"(n={v.get('sample_size')}, {v.get('rationale','')})")
    else:
        lines.append("■ APPLIED (0) — no change to the live model")
    lines.append("")

    deferred = [v for v in verdicts if v["decision"] == "DEFER"]
    rejected = [v for v in verdicts if v["decision"] == "REJECT"]
    if deferred:
        lines.append(f"■ DEFERRED FOR REVIEW ({len(deferred)})")
        for v in deferred:
            lines.append(f"  • {v['target']}: {v['current']} → {v.get('clamped_value')} "
                         f"— {v['reason']} ({v.get('rationale','')})")
        lines.append("")
    if rejected:
        lines.append(f"■ REJECTED ({len(rejected)})")
        for v in rejected:
            lines.append(f"  • {v['target']}: {v['reason']}")
        lines.append("")
    lines.append(sep)

    dest = report_path(f"param_tuning_{date_str}.txt")
    try:
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        log(f"model_param_tuner: report saved → {dest}")
        return True
    except OSError as exc:
        log(f"model_param_tuner: failed to write report — {exc}", "ERROR")
        return False


def main() -> int:
    log("model_param_tuner.py started")
    date_str = sys.argv[1] if len(sys.argv) > 1 else today_str()

    proposals_doc = safe_load_json(data_path(f"proposed_params_{date_str}.json"))
    if not proposals_doc or not isinstance(proposals_doc, dict):
        log(f"model_param_tuner: no proposals for {date_str} — nothing to tune", "INFO")
        _write_report(date_str, [], [], current_version())
        return 0

    proposals = proposals_doc.get("proposals") or []
    live = copy.deepcopy(get_params())

    verdicts = [_evaluate(p, live) for p in proposals if isinstance(p, dict)]

    appliable = [v for v in verdicts if v["decision"] == "APPLY"]
    # Strongest first (largest sample), capped per night. The rest are deferred.
    appliable.sort(key=lambda v: (int(v.get("sample_size") or 0)), reverse=True)
    to_apply = appliable[:MAX_CHANGES_PER_NIGHT]
    for v in appliable[MAX_CHANGES_PER_NIGHT:]:
        v["decision"] = "DEFER"
        v["reason"] = f"exceeded {MAX_CHANGES_PER_NIGHT} changes/night cap"

    applied: list[dict] = []
    new_version = current_version()

    # Effective auto-apply = hard code switch AND the runtime kill-switch.
    auto_on = AUTO_APPLY_ENABLED and is_auto_tune_enabled()
    if not auto_on:
        _why = ("AUTO_APPLY disabled in code" if not AUTO_APPLY_ENABLED
                else "auto-tune frozen via control file (learning_control.json)")
        for v in to_apply:
            v["decision"] = "DEFER"
            v["reason"] = f"{_why} — review-only"
    elif to_apply:
        new_params = copy.deepcopy(live)
        for v in to_apply:
            _set_dotted(new_params, v["target"], v["clamped_value"])
        evidence = {
            "source": f"proposed_params_{date_str}.json",
            "window_days": proposals_doc.get("window_days"),
            "dataset_rows_in_window": proposals_doc.get("dataset_rows_in_window"),
            "changes": [
                {"target": v["target"], "from": v["current"], "to": v["clamped_value"],
                 "sample_size": v.get("sample_size"), "rationale": v.get("rationale")}
                for v in to_apply
            ],
        }
        note = "; ".join(f"{v['target']} {v['current']}→{v['clamped_value']}" for v in to_apply)
        if write_params(new_params, change_note=note, evidence=evidence):
            applied = to_apply
            new_version = current_version()
            log(f"model_param_tuner: applied {len(applied)} change(s) — params v{new_version}")
        else:
            log("model_param_tuner: write_params failed — no change applied", "ERROR")
            for v in to_apply:
                v["decision"] = "DEFER"
                v["reason"] = "params write failed"

    ok = _write_report(date_str, verdicts, applied, new_version)
    print(f"model_param_tuner: applied={len(applied)} "
          f"deferred={sum(1 for v in verdicts if v['decision']=='DEFER')} "
          f"rejected={sum(1 for v in verdicts if v['decision']=='REJECT')} "
          f"version=v{new_version}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
