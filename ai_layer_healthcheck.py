"""
ai_layer_healthcheck.py — one-command diagnostic for the AI intelligence layer.

Run this FIRST on PythonAnywhere after adding ANTHROPIC_API_KEY to .env. It
validates the one seam that cannot be exercised offline: a real structured-output
call against the live Anthropic API (SDK shape + model id).

It is completely safe to run repeatedly:
    - No key / no SDK  -> reports DISABLED and exits 0 (nothing to validate yet).
    - Key present       -> makes ONE tiny real call and reports PASS/FAIL with the
                           raw result or the exact error, so any needed tweak to
                           the call signature or model id is obvious immediately.

Usage:
    python ai_layer_healthcheck.py

Exit codes:
    0  — layer healthy, OR gracefully disabled (no key) — nothing is broken.
    1  — key IS present but the live call failed (action needed).
"""

from __future__ import annotations

import sys

from src.config import get_config
from src.helpers import log
from src.llm_client import get_llm_client, llm_available, _SDK_AVAILABLE


_PROBE_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "horse": {"type": "string"},
        "verdict": {"type": "string", "enum": ["SOLID", "AVOID"]},
    },
    "required": ["ok", "horse", "verdict"],
    "additionalProperties": False,
}

_PROBE_SYSTEM = (
    "You are validating a structured-output pipeline. Return ONLY the JSON the "
    "schema requires: set ok=true, echo the horse name you are given, and pick a "
    "verdict. No commentary."
)

_PROBE_PAYLOAD = {"horse": "Healthcheck Lad", "instruction": "confirm the pipeline works"}


def main() -> int:
    log("ai_layer_healthcheck.py started")
    print("=" * 60)
    print("  AI LAYER HEALTHCHECK")
    print("=" * 60)

    try:
        cfg = get_config()
    except Exception as exc:
        print(f"  CONFIG ERROR: {exc}")
        return 1

    key_present = bool(cfg.anthropic_api_key)
    print(f"  ANTHROPIC_API_KEY present : {key_present}")
    print(f"  anthropic SDK importable  : {_SDK_AVAILABLE}")
    print(f"  Configured model          : {cfg.anthropic_model}")
    print("-" * 60)

    if not key_present:
        print("  STATUS: DISABLED (no API key) — the whole AI layer degrades to")
        print("          no-ops and the numeric model runs exactly as today.")
        print("          Add ANTHROPIC_API_KEY to .env to enable, then re-run.")
        return 0

    if not _SDK_AVAILABLE:
        print("  STATUS: KEY PRESENT but anthropic SDK is not importable.")
        print("          Run: pip install -r requirements.txt")
        return 1

    if not llm_available():
        print("  STATUS: llm_available() returned False unexpectedly.")
        return 1

    client = get_llm_client()
    if client is None:
        print("  STATUS: client construction failed (see log). Check key/SDK.")
        return 1

    print(f"  Making ONE live probe call to model '{client.default_model}' ...")
    result = client.call_structured(_PROBE_SYSTEM, _PROBE_PAYLOAD, _PROBE_SCHEMA, max_tokens=256)

    if result is None:
        print("-" * 60)
        print("  STATUS: FAIL — the live call returned None.")
        print("  Likely causes (check the WARNING in the log just above):")
        print("    • outbound network to api.anthropic.com is blocked by policy")
        print("    • the model id is wrong/unavailable for this account")
        print("    • the structured-output call shape needs an SDK-version tweak")
        print("  The pipeline is still SAFE — it degrades to numeric-only.")
        return 1

    print("-" * 60)
    print(f"  STATUS: PASS — live structured call succeeded.")
    print(f"  Raw result: {result}")
    print("  The AI layer is fully operational. Form reader, pace, arbiter,")
    print("  autopsy, and briefing writer will now produce real output.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
