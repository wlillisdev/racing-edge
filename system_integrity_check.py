"""
system_integrity_check.py — THE KEY QA GATE.

Run before any live operation to verify the system is healthy.

CRITICAL: This script's final output line must be either:
  "SYSTEM_STATUS: PASS - SAFE TO CONTINUE"
  or
  "SYSTEM_STATUS: FAIL - DO NOT CONTINUE"

Usage:
    python system_integrity_check.py

Exit codes:
    0 — PASS (all checks green)
    1 — FAIL (one or more checks failed)
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Script lists
# ---------------------------------------------------------------------------

# Project root is the directory containing this script.
_PROJECT_DIR = Path(__file__).parent

CRITICAL_SCRIPTS: list[str] = [
    "run_daily.py",
    "market_snapshot.py",
    "custom_signposts.py",
    "race_shortlist.py",
    "race_reader.py",
    "full_form_reader.py",
    "nap_selector_v3.py",
    "cluster_review.py",
    "morning_briefing_report.py",
    "email_report.py",
    "market_movers.py",
    "non_runner_scan.py",
    "final_nap_decision.py",
    "final_decision_guard.py",
    "email_market_update.py",
    "results_auditor.py",
    "performance_tracker.py",
    "profit_report.py",
    "email_audit.py",
    "daily_pipeline.py",
    "market_update_pipeline.py",
    "evening_audit_pipeline.py",
]

SRC_SCRIPTS: list[str] = [
    "src/config.py",
    "src/helpers.py",
    "src/api_client.py",
    "src/db.py",
]

# Expected script order for each pipeline (just verifying references exist in file)
DAILY_PIPELINE_ORDER: list[str] = [
    "run_daily.py",
    "market_snapshot.py",
    "custom_signposts.py",
    "race_shortlist.py",
    "race_reader.py",
    "full_form_reader.py",
    "nap_selector_v3.py",
    "cluster_review.py",
    "morning_briefing_report.py",
    "email_report.py",
]

MARKET_PIPELINE_ORDER: list[str] = [
    "run_daily.py",
    "market_snapshot.py",
    "market_movers.py",
    "non_runner_scan.py",
    "final_nap_decision.py",
    "final_decision_guard.py",
    "email_market_update.py",
]

EVENING_PIPELINE_ORDER: list[str] = [
    "results_auditor.py",
    "performance_tracker.py",
    "profit_report.py",
    "email_audit.py",
]

REQUIRED_DIRS: list[str] = [
    "data",
    "data/market_snapshots",
    "reports",
    "archive/system_snapshots",
    "archive/database_backups",
    "src",
]

# Config keys that are mandatory (must be in .env)
MANDATORY_ENV_KEYS: list[str] = [
    "RACING_API_USERNAME",
    "RACING_API_PASSWORD",
    "DB_HOST",
    "DB_NAME",
    "DB_USER",
    "DB_PASS",
    "EMAIL_SENDER",
    "EMAIL_PASSWORD",
    "EMAIL_RECIPIENT",
]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

class CheckResults:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures: int = 0

    def add(self, line: str) -> None:
        self.lines.append(line)

    def pass_line(self, label: str, detail: str = "") -> None:
        suffix = f" — {detail}" if detail else ""
        self.lines.append(f"   [PASS] {label}{suffix}")

    def fail_line(self, label: str, detail: str = "") -> None:
        suffix = f" — {detail}" if detail else ""
        self.lines.append(f"   [FAIL] {label}{suffix}")
        self.failures += 1

    def warn_line(self, label: str, detail: str = "") -> None:
        suffix = f" — {detail}" if detail else ""
        self.lines.append(f"   [WARN] {label}{suffix}")

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(title)

    def print_all(self) -> None:
        print("\n".join(self.lines))


# ---------------------------------------------------------------------------
# Check 1: File compilation
# ---------------------------------------------------------------------------

def check_file_compilation(r: CheckResults) -> None:
    r.section("1. FILE COMPILATION")

    all_scripts = CRITICAL_SCRIPTS + SRC_SCRIPTS
    pass_count = 0
    fail_count = 0

    for script in all_scripts:
        script_path = _PROJECT_DIR / script
        if not script_path.exists():
            r.fail_line(script, "FILE NOT FOUND")
            fail_count += 1
            continue

        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            r.pass_line(script)
            pass_count += 1
        else:
            error = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "compile error"
            r.fail_line(script, error)
            fail_count += 1

    r.add(f"   Result: {pass_count}/{len(all_scripts)} compiled | {fail_count} failures")


# ---------------------------------------------------------------------------
# Check 2: Pipeline order
# ---------------------------------------------------------------------------

def _check_pipeline_order(pipeline_file: str, expected_order: list[str]) -> tuple[bool, str]:
    """Return (ok, detail). Verifies that each expected script appears in the
    pipeline file in the correct relative order."""
    path = _PROJECT_DIR / pipeline_file
    if not path.exists():
        return False, f"{pipeline_file} not found"

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, str(exc)

    positions: list[int] = []
    missing: list[str] = []

    for script in expected_order:
        pos = content.find(script)
        if pos == -1:
            missing.append(script)
        else:
            positions.append(pos)

    if missing:
        return False, f"missing references: {', '.join(missing)}"

    # Verify order is monotonically increasing
    for i in range(1, len(positions)):
        if positions[i] <= positions[i - 1]:
            return False, (
                f"order violation: '{expected_order[i]}' appears before "
                f"'{expected_order[i - 1]}'"
            )

    return True, "OK"


def check_pipeline_order(r: CheckResults) -> None:
    r.section("2. PIPELINE ORDER")

    checks = [
        ("Daily pipeline",   "daily_pipeline.py",         DAILY_PIPELINE_ORDER),
        ("Market pipeline",  "market_update_pipeline.py", MARKET_PIPELINE_ORDER),
        ("Evening pipeline", "evening_audit_pipeline.py", EVENING_PIPELINE_ORDER),
    ]

    for label, pipeline_file, order in checks:
        ok, detail = _check_pipeline_order(pipeline_file, order)
        if ok:
            r.pass_line(label)
        else:
            r.fail_line(label, detail)


# ---------------------------------------------------------------------------
# Check 3: Config
# ---------------------------------------------------------------------------

def check_config(r: CheckResults) -> None:
    r.section("3. CONFIG")

    env_path = _PROJECT_DIR / ".env"
    if env_path.exists():
        r.pass_line(".env file", "FOUND")
    else:
        r.fail_line(".env file", "NOT FOUND (copy from .env.example and fill in values)")

    # Try loading the config
    try:
        # Add project dir to sys.path so imports work
        if str(_PROJECT_DIR) not in sys.path:
            sys.path.insert(0, str(_PROJECT_DIR))
        from src.config import get_config
        get_config()
        r.pass_line("get_config()", "PASS")
    except KeyError as exc:
        r.fail_line("get_config()", f"Missing env var: {exc}")
    except Exception as exc:  # noqa: BLE001
        r.fail_line("get_config()", str(exc))


# ---------------------------------------------------------------------------
# Check 4: Directory structure
# ---------------------------------------------------------------------------

def check_directories(r: CheckResults) -> None:
    r.section("4. DIRECTORY STRUCTURE")

    for dir_name in REQUIRED_DIRS:
        dir_path = _PROJECT_DIR / dir_name
        if dir_path.is_dir():
            r.pass_line(f"{dir_name}/", "OK")
        else:
            r.fail_line(f"{dir_name}/", "MISSING")


# ---------------------------------------------------------------------------
# Check 5: Output freshness
# ---------------------------------------------------------------------------

def check_output_freshness(r: CheckResults) -> None:
    r.section("5. OUTPUT FRESHNESS")

    date_str = datetime.now().strftime("%Y-%m-%d")
    racecard_path = _PROJECT_DIR / "data" / f"racecards_{date_str}.json"

    if not racecard_path.exists():
        r.add(f"   racecards_{date_str}.json: NOT PRESENT (pipeline not yet run today — OK)")
        return

    # Check file modification time as a proxy for freshness
    try:
        stat = racecard_path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        age_hours = (now - mtime).total_seconds() / 3600

        if age_hours < 12:
            age_str = f"{age_hours:.1f}h ago" if age_hours >= 1 else f"{int(age_hours * 60)}m ago"
            r.pass_line(f"racecards_{date_str}.json", f"FRESH (fetched {age_str})")
        else:
            r.warn_line(
                f"racecards_{date_str}.json",
                f"STALE ({age_hours:.1f}h ago — > 12h threshold)",
            )
    except OSError as exc:
        r.warn_line(f"racecards_{date_str}.json", f"could not stat — {exc}")

    # Also check fetched_at field inside the JSON if present
    try:
        import json
        with open(racecard_path, encoding="utf-8") as fh:
            data = json.load(fh)
        fetched_at_str: Optional[str] = data.get("fetched_at") if isinstance(data, dict) else None
        if fetched_at_str:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(tz=timezone.utc) - fetched_at).total_seconds() / 3600
            if age_h >= 12:
                r.warn_line(
                    "racecard fetched_at field",
                    f"STALE ({age_h:.1f}h ago per JSON metadata)",
                )
    except Exception:  # noqa: BLE001
        pass  # Non-critical — file-level mtime check above is sufficient


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    r = CheckResults()

    border = "=" * 56
    r.add(border)
    r.add("  SYSTEM INTEGRITY CHECK")
    r.add(f"  Date: {date_str} | Run: {time_str}")
    r.add(border)

    check_file_compilation(r)
    check_pipeline_order(r)
    check_config(r)
    check_directories(r)
    check_output_freshness(r)

    r.add("")
    r.add(border)

    overall_pass = r.failures == 0

    if overall_pass:
        status_line = "SYSTEM_STATUS: PASS - SAFE TO CONTINUE"
    else:
        status_line = f"SYSTEM_STATUS: FAIL - DO NOT CONTINUE ({r.failures} check(s) failed)"

    r.add(status_line)
    r.add(border)

    r.print_all()

    # The CRITICAL final line — must match exactly
    print(
        "SYSTEM_STATUS: PASS - SAFE TO CONTINUE"
        if overall_pass
        else "SYSTEM_STATUS: FAIL - DO NOT CONTINUE"
    )

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
