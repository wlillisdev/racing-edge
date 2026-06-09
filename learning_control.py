"""
learning_control.py — control panel + kill-switch for the self-tuning loop.

One command to see what the learning machine has done to the model and to take
control of it: inspect the live parameter version, what changed from defaults,
the auto-tune history, and pending proposals — then freeze, unfreeze, or
instantly revert.

Usage:
    python learning_control.py                 # status dashboard (default)
    python learning_control.py status
    python learning_control.py history [N]     # full change history (last N)
    python learning_control.py freeze          # STOP auto-tuning (kill-switch)
    python learning_control.py unfreeze        # resume auto-tuning
    python learning_control.py revert <ver>    # roll live params back to a version
    python learning_control.py revert last     # undo the most recent change

Nothing here touches betting directly — it only reads/controls the versioned
model parameters and the auto-tune kill-switch. Every revert is itself recorded
as a new version, so the audit trail is never lost.

Exit codes:
    0 — success
    1 — bad arguments / revert failure
"""

from __future__ import annotations

import sys

from src.helpers import data_path, log, safe_load_json
from src.model_params import (
    get_params, current_version, history, diff_from_defaults,
    revert_to_version, is_auto_tune_enabled, set_auto_tune_enabled,
    DEFAULTS,
)

_SEP = "=" * 60


def _latest_proposals() -> dict | None:
    """Best-effort: surface the most recent proposed_params_*.json if present."""
    import glob
    import os
    files = sorted(glob.glob(data_path("proposed_params_*.json")))
    if not files:
        return None
    doc = safe_load_json(files[-1])
    if isinstance(doc, dict):
        doc["_file"] = os.path.basename(files[-1])
    return doc


def cmd_status() -> int:
    ver = current_version()
    auto = is_auto_tune_enabled()
    changes = diff_from_defaults()
    hist = history()

    print(_SEP)
    print("  LEARNING MACHINE — CONTROL PANEL")
    print(_SEP)
    print(f"  Live params version : v{ver}" + ("  (defaults — never tuned)" if ver == 0 else ""))
    print(f"  Auto-tune           : {'🟢 ENABLED' if auto else '🔴 FROZEN (kill-switch on)'}")
    print(f"  Tunables off default: {len(changes)} of {len(DEFAULTS)}")
    print("-" * 60)

    if changes:
        print("  CHANGED FROM DEFAULTS:")
        for c in changes:
            print(f"    • {c['param']}: default {c['default']} → live {c['live']}")
    else:
        print("  No tunables differ from defaults — model is running stock.")
    print("-" * 60)

    if hist:
        print(f"  RECENT AUTO-TUNE HISTORY (last {min(5, len(hist))} of {len(hist)}):")
        for h in hist[-5:]:
            print(f"    v{h.get('version')}  {str(h.get('applied_at',''))[:19]}  {h.get('change','')}")
    else:
        print("  No auto-tune history yet — nothing has been applied.")
    print("-" * 60)

    prop = _latest_proposals()
    if prop and prop.get("proposals"):
        print(f"  PENDING PROPOSALS ({prop['_file']}):")
        for p in prop["proposals"]:
            print(f"    • {p.get('target')}: {p.get('current_value')} → {p.get('proposed_value')} "
                  f"(n={p.get('sample_size')}, conf={p.get('confidence')})")
    else:
        print("  No pending proposals.")
    print(_SEP)
    print("  Commands: freeze | unfreeze | history [N] | revert <ver|last>")
    print(_SEP)
    return 0


def cmd_history(n: int | None) -> int:
    hist = history()
    if not hist:
        print("No auto-tune history yet.")
        return 0
    rows = hist if n is None else hist[-n:]
    print(_SEP)
    print(f"  AUTO-TUNE HISTORY ({len(rows)} of {len(hist)})")
    print(_SEP)
    for h in rows:
        print(f"  v{h.get('version')}  {str(h.get('applied_at',''))[:19]}")
        print(f"     change   : {h.get('change','')}")
        ev = h.get("evidence") or {}
        if ev.get("changes"):
            for ch in ev["changes"]:
                print(f"     - {ch.get('target')}: {ch.get('from')} → {ch.get('to')} "
                      f"(n={ch.get('sample_size')}) {ch.get('rationale','')}")
        elif ev:
            print(f"     evidence : {ev}")
    print(_SEP)
    return 0


def cmd_freeze(enable: bool) -> int:
    ok = set_auto_tune_enabled(enable)
    state = "ENABLED — model will self-tune nightly within its safety gates" if enable \
        else "FROZEN — auto-tuning is OFF; the learner still analyses & proposes, but no change applies"
    print(f"Auto-tune {state}." if ok else "Failed to update the control file.")
    return 0 if ok else 1


def cmd_revert(arg: str) -> int:
    hist = history()
    if arg == "last":
        if len(hist) < 2:
            print("Nothing to revert to — fewer than 2 versions in history.")
            return 1
        target = hist[-2].get("version")
    else:
        try:
            target = int(arg)
        except ValueError:
            print(f"revert: '{arg}' is not a version number or 'last'.")
            return 1
    print(f"Reverting live params to v{target} ...")
    if revert_to_version(int(target)):
        print(f"Done — params reverted to v{target} (recorded as v{current_version()}).")
        return 0
    print(f"Revert failed — version {target} not found in history.")
    return 1


def main() -> int:
    args = sys.argv[1:]
    cmd = (args[0].lower() if args else "status")

    if cmd in ("status", ""):
        return cmd_status()
    if cmd == "history":
        n = None
        if len(args) > 1:
            try:
                n = int(args[1])
            except ValueError:
                print("history: N must be an integer.")
                return 1
        return cmd_history(n)
    if cmd in ("freeze", "disable", "stop", "off"):
        return cmd_freeze(False)
    if cmd in ("unfreeze", "enable", "resume", "on"):
        return cmd_freeze(True)
    if cmd == "revert":
        if len(args) < 2:
            print("revert: supply a version number or 'last'.")
            return 1
        return cmd_revert(args[1])

    print(f"Unknown command '{cmd}'. Use: status | history [N] | freeze | unfreeze | revert <ver|last>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
