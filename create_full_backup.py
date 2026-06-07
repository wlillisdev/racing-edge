"""
create_full_backup.py — Create a disaster-recovery tar.gz backup of the project.

What is included:
    - All .py files
    - sql/
    - .env.example (NOT .env)
    - requirements.txt
    - README.md
    - data/*.json (today's and yesterday's)
    - reports/*.txt (recent)
    - performance_log.csv
    - archive/system_snapshots/ (last 7 days only)

What is excluded:
    - .env (credentials are NEVER backed up)
    - venv/
    - __pycache__/
    - *.tar.gz (old backups)
    - archive/external_exports/ (avoids recursive inclusion)

Outputs:
    archive/external_exports/racing_model_lean_export_{YYYY-MM-DD}_{HHMM}.tar.gz
    archive/external_exports/RESTORE_INSTRUCTIONS_{YYYY-MM-DD}_{HHMM}.txt

Usage:
    python create_full_backup.py

Exit codes:
    0 — success
    1 — backup failed
"""

from __future__ import annotations

import sys
import tarfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from src.helpers import log


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_DIR = Path(__file__).parent
_EXPORTS_DIR = _PROJECT_DIR / "archive" / "external_exports"
_SNAPSHOTS_DIR = _PROJECT_DIR / "archive" / "system_snapshots"

# How many days of system_snapshots to include
SNAPSHOT_DAYS = 7


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

def _is_excluded(path: Path) -> bool:
    """Return True if the path should be excluded from the backup."""
    # Never include .env (credentials)
    if path.name == ".env":
        return True
    # Never include the exports directory itself (would be recursive)
    try:
        path.relative_to(_EXPORTS_DIR)
        return True
    except ValueError:
        pass
    # Skip virtual environments
    for part in path.parts:
        if part in ("venv", ".venv", "env", "node_modules"):
            return True
        if part == "__pycache__":
            return True
    # Skip old tar.gz backups
    if path.suffix == ".gz" and path.suffixes == [".tar", ".gz"]:
        return True
    if path.name.endswith(".tar.gz"):
        return True
    return False


def _recent_json_files(directory: Path, days_back: int = 2) -> Iterator[Path]:
    """Yield .json files from a directory that are within `days_back` days old."""
    cutoff = datetime.now() - timedelta(days=days_back)
    for f in directory.glob("*.json"):
        if f.is_file():
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime >= cutoff:
                    yield f
            except OSError:
                yield f  # include if we can't stat


def _recent_txt_files(directory: Path, days_back: int = 14) -> Iterator[Path]:
    """Yield .txt files from reports/ that are within `days_back` days old."""
    cutoff = datetime.now() - timedelta(days=days_back)
    for f in directory.glob("*.txt"):
        if f.is_file():
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime >= cutoff:
                    yield f
            except OSError:
                yield f


def _recent_snapshots() -> Iterator[Path]:
    """Yield system_snapshot files from the last SNAPSHOT_DAYS days."""
    cutoff = datetime.now() - timedelta(days=SNAPSHOT_DAYS)
    for f in _SNAPSHOTS_DIR.glob("*.json"):
        if f.is_file():
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime >= cutoff:
                    yield f
            except OSError:
                yield f


def _collect_files() -> list[tuple[Path, str]]:
    """Return a list of (absolute_path, archive_name) tuples to include.

    archive_name is the path as it will appear inside the tar.gz.
    """
    included: list[tuple[Path, str]] = []

    def _add(path: Path) -> None:
        if not path.exists():
            return
        if _is_excluded(path):
            return
        # Archive name is relative to project dir
        try:
            arc_name = str(path.relative_to(_PROJECT_DIR))
        except ValueError:
            arc_name = path.name
        included.append((path, arc_name))

    # --- All .py files in project root and src/ ---
    for py_file in _PROJECT_DIR.glob("*.py"):
        if py_file.is_file() and not _is_excluded(py_file):
            _add(py_file)

    src_dir = _PROJECT_DIR / "src"
    if src_dir.is_dir():
        for py_file in src_dir.glob("*.py"):
            if py_file.is_file() and not _is_excluded(py_file):
                _add(py_file)

    # --- sql/ directory ---
    sql_dir = _PROJECT_DIR / "sql"
    if sql_dir.is_dir():
        for f in sql_dir.iterdir():
            if f.is_file() and not _is_excluded(f):
                _add(f)

    # --- Project meta files ---
    for fname in (".env.example", "requirements.txt", "README.md"):
        _add(_PROJECT_DIR / fname)

    # --- data/*.json (today's and yesterday's) ---
    data_dir = _PROJECT_DIR / "data"
    if data_dir.is_dir():
        for f in _recent_json_files(data_dir, days_back=2):
            if not _is_excluded(f):
                _add(f)

    # --- reports/*.txt (recent 14 days) ---
    reports_dir = _PROJECT_DIR / "reports"
    if reports_dir.is_dir():
        for f in _recent_txt_files(reports_dir, days_back=14):
            if not _is_excluded(f):
                _add(f)

    # --- performance_log.csv ---
    perf_log = _PROJECT_DIR / "performance_log.csv"
    if perf_log.exists():
        _add(perf_log)

    # --- archive/system_snapshots/ (last SNAPSHOT_DAYS days) ---
    if _SNAPSHOTS_DIR.is_dir():
        for f in _recent_snapshots():
            if not _is_excluded(f):
                _add(f)

    return included


# ---------------------------------------------------------------------------
# Restore instructions
# ---------------------------------------------------------------------------

def _write_restore_instructions(
    instructions_path: Path,
    backup_filename: str,
    date_str: str,
    hhmm: str,
    file_count: int,
    backup_size_mb: float,
) -> None:
    lines = [
        "=" * 60,
        "RACING EDGE — RESTORE INSTRUCTIONS",
        f"Backup created: {date_str} at {hhmm}",
        f"Archive:        {backup_filename}",
        f"Files included: {file_count}",
        f"Archive size:   {backup_size_mb:.1f} MB",
        "=" * 60,
        "",
        "WHAT IS INCLUDED",
        "  - All Python source files (.py)",
        "  - sql/schema.sql (database schema)",
        "  - .env.example (credentials template — NOT .env)",
        "  - requirements.txt",
        "  - README.md",
        "  - Recent data files (today's and yesterday's .json)",
        "  - Recent reports (last 14 days .txt)",
        "  - performance_log.csv",
        f"  - archive/system_snapshots/ (last {SNAPSHOT_DAYS} days)",
        "",
        "WHAT IS NOT INCLUDED",
        "  - .env (credentials — NEVER backed up for security)",
        "  - venv/ or __pycache__/",
        "  - Old *.tar.gz backups",
        "  - archive/external_exports/ (to avoid recursive inclusion)",
        "",
        "RESTORE STEPS",
        "",
        "1. Create a fresh project directory:",
        "     mkdir racing_model_restored",
        "     cd racing_model_restored",
        "",
        "2. Extract the backup:",
        f"     tar -xzf {backup_filename}",
        "",
        "3. Create a Python virtual environment:",
        "     python3 -m venv venv",
        "     source venv/bin/activate   # Linux / macOS",
        "     # or on Windows: venv\\Scripts\\activate",
        "",
        "4. Install dependencies:",
        "     pip install -r requirements.txt",
        "",
        "5. Configure credentials:",
        "     cp .env.example .env",
        "     # Edit .env and fill in all values:",
        "     #   RACING_API_KEY, DB_HOST, DB_NAME, DB_USER, DB_PASS",
        "     #   EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT",
        "     #   PROJECT_DIR (absolute path to this directory)",
        "",
        "6. Verify the database configuration:",
        "     python database_config_check.py",
        "",
        "7. If the database is empty, recreate the schema:",
        "     python database_foundation.py",
        "",
        "8. Run a system integrity check:",
        "     python system_integrity_check.py",
        "",
        "9. Run the daily pipeline:",
        "     python daily_pipeline.py",
        "",
        "DATABASE RESTORE (if you have a MySQL dump)",
        "  mysql -u USER -p DB_NAME < backup.sql",
        "",
        "IMPORTANT NOTES",
        "  - The .env file is NOT included in this backup.",
        "    You must recreate it from .env.example.",
        "  - Historical data files older than 2 days are NOT included.",
        "    Re-fetch them via the API if needed.",
        "  - Check system_integrity_check.py output before any live operation.",
        "",
        "=" * 60,
        "End of restore instructions",
        "=" * 60,
    ]
    try:
        instructions_path.parent.mkdir(parents=True, exist_ok=True)
        with open(instructions_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        log(f"create_full_backup: restore instructions saved to {instructions_path}")
    except OSError as exc:
        log(f"create_full_backup: could not write restore instructions — {exc}", "WARNING")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("create_full_backup.py started")
    start_ts = time.time()

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H%M")

    # ------------------------------------------------------------------
    # 1. Collect files to back up
    # ------------------------------------------------------------------
    log("create_full_backup: collecting files...")
    files_to_backup = _collect_files()
    log(f"create_full_backup: {len(files_to_backup)} files collected")

    if not files_to_backup:
        log("create_full_backup: no files found to back up!", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 2. Create output paths
    # ------------------------------------------------------------------
    _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    backup_filename = f"racing_model_lean_export_{date_str}_{hhmm}.tar.gz"
    backup_path = _EXPORTS_DIR / backup_filename
    instructions_filename = f"RESTORE_INSTRUCTIONS_{date_str}_{hhmm}.txt"
    instructions_path = _EXPORTS_DIR / instructions_filename

    log(f"create_full_backup: writing archive to {backup_path}")

    # ------------------------------------------------------------------
    # 3. Write tar.gz
    # ------------------------------------------------------------------
    try:
        with tarfile.open(backup_path, "w:gz", compresslevel=6) as tar:
            skipped = 0
            added = 0
            for abs_path, arc_name in files_to_backup:
                if not abs_path.exists():
                    log(f"create_full_backup: skipping missing file — {abs_path}", "WARNING")
                    skipped += 1
                    continue
                try:
                    tar.add(abs_path, arcname=arc_name, recursive=False)
                    added += 1
                except (OSError, tarfile.TarError) as exc:
                    log(f"create_full_backup: could not add {abs_path} — {exc}", "WARNING")
                    skipped += 1

    except (OSError, tarfile.TarError) as exc:
        log(f"create_full_backup: failed to create archive — {exc}", "ERROR")
        return 1

    # ------------------------------------------------------------------
    # 4. Verify and report size
    # ------------------------------------------------------------------
    try:
        backup_size_bytes = backup_path.stat().st_size
        backup_size_mb = backup_size_bytes / 1_048_576
    except OSError:
        backup_size_mb = 0.0

    log(
        f"create_full_backup: archive created — "
        f"{added} files, {skipped} skipped, {backup_size_mb:.2f} MB"
    )

    # ------------------------------------------------------------------
    # 5. Write restore instructions
    # ------------------------------------------------------------------
    _write_restore_instructions(
        instructions_path,
        backup_filename,
        date_str,
        hhmm,
        added,
        backup_size_mb,
    )

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    duration = round(time.time() - start_ts, 2)

    print("")
    print("BACKUP COMPLETE")
    print("=" * 50)
    print(f"Archive:       {backup_path}")
    print(f"Instructions:  {instructions_path}")
    print(f"Files backed up: {added}")
    print(f"Files skipped:   {skipped}")
    print(f"Archive size:    {backup_size_mb:.2f} MB")
    print(f"Duration:        {duration}s")
    print("=" * 50)

    log(f"create_full_backup.py finished in {duration}s — archive: {backup_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
