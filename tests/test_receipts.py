"""THE RECEIPTS REGISTER — the suite goes red on a rule with no birth receipt.

Law 2 says a rule is born THREE ways only: the master teaches it, the master
validates it (doorbell), or the record field-tests it. Until tonight nothing
enforced it — a threshold typed at midnight looked exactly like a taught law.
`data/receipts.csv` is the register: one row per rule, flag, caution, aligned
label, bonus, penalty, gate, term and constant in the engine's live pick path,
each with the quote or the number that bought it.

THE SENTENCE TO ADD TO CLAUDE.md, LAW 2 (verbatim):

    Every rule in the pick path carries a row in `data/receipts.csv` naming
    how it was born — taught, doorbell, field-tested or UNRECEIPTED — and
    `tests/test_receipts.py` turns the suite red on any rule the code fires
    that the register does not name.

What this module proves:
  1. every aligned / flag / caution label the engine can emit is named in the
     register (matched on the label HEAD, exactly as school/yardstick.lens_key
     cuts it, so a reworded percentage never orphans a rule);
  2. every scoring term in race_quality_score and every named constant in the
     fixed list below has a row;
  3. no row has an empty or invented `born_by`.
It does NOT assert the UNRECEIPTED count: that number is printed, so the health
page can carry it and the master can retire rules one at a time. Turning
UNRECEIPTED into a failure is his word to give, never the apprentice's.

Register path: `data/receipts.csv`, overridable with RECEIPTS_CSV for a
pre-commit dry run against a register that is not in the tree yet.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTER = Path(os.environ.get("RECEIPTS_CSV") or (ROOT / "data" / "receipts.csv"))

CONVICTION = ROOT / "src/racing_edge/selection/conviction.py"
PIPELINE = ROOT / "src/racing_edge/pipeline/nap.py"

BORN_BY = {"taught", "doorbell", "field-tested", "UNRECEIPTED"}

# name -> the file it is defined in. A constant absent from its file is skipped
# (the register must not fail because a module was refactored), a constant
# PRESENT and unregistered is a failure.
CONSTANTS = {
    "BETTING_BAR": "src/racing_edge/pipeline/nap.py",
    "STALE_RUNS": "src/racing_edge/domain/mark.py",
    "COMBO_MIN_RIDES": "src/racing_edge/school/signposts.py",
    "COURSE_TYPE_MIN_RUNS": "src/racing_edge/school/signposts.py",
    "RATING_CLEAR_LB": "src/racing_edge/school/signposts.py",
    "FRESH_DAYS": "src/racing_edge/school/signposts.py",
    "COLD_YARD_DAYS": "src/racing_edge/school/signposts.py",
    "MIN_JUDGE": "src/racing_edge/school/ladder.py",
    "WINDOW": "src/racing_edge/school/ladder.py",
    "MIN_CELL_N": "src/racing_edge/school/bar_backtest.py",
    "MONTH_MIN_N": "src/racing_edge/school/tier0.py",
}

# --------------------------------------------------------------------------- #
# the label HEAD — mirrors school/yardstick.lens_key exactly, so the register
# and the ledger key a lens the same way
# --------------------------------------------------------------------------- #
_FIGURE_RE = re.compile(r"#?\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*(?:lb|kg|f|yo|%)?")


def head(tag: str) -> str:
    s = (tag or "").strip().lower()
    cuts = [i for i in (s.find(" ("), s.find(" —"), s.find(":")) if i != -1]
    if cuts:
        s = s[: min(cuts)]
    s = _FIGURE_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------- #
# the register
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def rows() -> list[dict]:
    if not REGISTER.exists():
        pytest.fail(
            f"THE RECEIPTS REGISTER IS MISSING: {REGISTER}. Every rule in the pick "
            "path carries a row naming how it was born (law 2). No register, no picks.")
    with REGISTER.open(encoding="utf-8") as fh:
        out = list(csv.DictReader(fh))
    assert out, "the receipts register is empty"
    return out


@pytest.fixture(scope="module")
def heads(rows) -> set[str]:
    return {head(r["label_or_value"]) for r in rows if head(r["label_or_value"])}


def _labels(path: Path, bucket: str) -> list[tuple[str, int]]:
    """Every literal label the source hands to `bucket`.append(...), with its
    line. Tolerant of f-strings and of multi-line implicit concatenation: the
    FIRST string literal of the call carries the head, which is all the register
    keys on (`race_flags.append(` matches `flags.append(` by design)."""
    text = path.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(rf'{bucket}\.append\(\s*f?"([^"]*)"', text, re.DOTALL):
        out.append((m.group(1), text.count("\n", 0, m.start()) + 1))
    return out


def _all_labels() -> list[tuple[str, int, str]]:
    out = []
    for path in (CONVICTION, PIPELINE):
        for bucket in ("aligned", "flags", "cautions"):
            for label, line in _labels(path, bucket):
                out.append((label, line, f"{path.relative_to(ROOT)}:{line}"))
    return out


# --------------------------------------------------------------------------- #
# 1. every label the engine can fire is in the register
# --------------------------------------------------------------------------- #
def test_every_engine_label_has_a_register_row(heads):
    found = _all_labels()
    assert len(found) >= 25, (
        f"only {len(found)} labels scanned out of conviction.py and pipeline/nap.py — "
        "the scanner has lost its grip on the source, not the engine its rules")
    orphans = sorted({(head(lab), where) for lab, _ln, where in found
                      if head(lab) and head(lab) not in heads})
    assert not orphans, (
        "RULES THE ENGINE FIRES THAT THE REGISTER DOES NOT NAME (law 2 — a rule is "
        "born three ways only; add the row with its receipt, or delete the rule):\n"
        + "\n".join(f"  {where}  '{h}'" for h, where in orphans))


# --------------------------------------------------------------------------- #
# 2. every scoring term and every named constant is in the register
# --------------------------------------------------------------------------- #
def test_every_race_quality_term_has_a_register_row(rows):
    text = PIPELINE.read_text(encoding="utf-8").splitlines()
    pipe = str(PIPELINE.relative_to(ROOT))
    by_line = {}
    for r in rows:
        by_line.setdefault((r["file"], r["line"]), []).append(r)
    missing, unnamed = [], []
    for i, line in enumerate(text, start=1):
        if "q += " not in line and "q -= " not in line:
            continue
        here = by_line.get((pipe, str(i)), [])
        if not here:
            missing.append(f"  {pipe}:{i}  {line.strip()}")
            continue
        # every literal that is not the bare +1/-1 step must be visible in a row
        for lit in re.findall(r"\d+\.\d+|\d+", line):
            if lit in ("0", "1"):
                continue
            if not any(lit in r["label_or_value"] for r in here):
                unnamed.append(f"  {pipe}:{i}  the number {lit} appears in no row")
    assert not missing and not unnamed, (
        "RACE-QUALITY TERMS WITH NO RECEIPT ROW (every +1/-1/+2/-2 that picks the "
        "race must name what bought it):\n" + "\n".join(missing + unnamed))


def test_every_named_constant_has_a_register_row(rows):
    blob = "\n".join(f"{r['rule_id']} {r['label_or_value']}" for r in rows)
    missing = []
    for name, rel in CONSTANTS.items():
        src = ROOT / rel
        if not src.exists():
            continue
        if not re.search(rf"^{name}\s*(?::[^=]+)?=", src.read_text(encoding="utf-8"),
                         re.MULTILINE):
            continue                       # moved or renamed — not this test's business
        if not re.search(rf"\b{name}\b", blob):
            missing.append(f"  {rel}  {name}")
    assert not missing, (
        "CONSTANTS THAT GATE THE PICK WITH NO RECEIPT ROW:\n" + "\n".join(missing))


# --------------------------------------------------------------------------- #
# 3. the register itself is honest
# --------------------------------------------------------------------------- #
def test_every_row_declares_how_it_was_born(rows):
    bad = [f"  {r['rule_id']}: born_by={r['born_by']!r}" for r in rows
           if r["born_by"].strip() not in BORN_BY]
    assert not bad, (
        "ROWS WITH NO BIRTH (born_by must be exactly one of taught / doorbell / "
        "field-tested / UNRECEIPTED — a blank is the disease law 2 names):\n"
        + "\n".join(bad))


def test_rule_ids_are_unique(rows):
    seen, dupes = set(), []
    for r in rows:
        if r["rule_id"] in seen:
            dupes.append(r["rule_id"])
        seen.add(r["rule_id"])
    assert not dupes, f"duplicate rule_id(s) in the register: {sorted(set(dupes))}"


def test_unreceipted_rules_are_counted_not_hidden(rows, capsys):
    """PRINTS the count — never asserts it. Retiring a rule is his word."""
    un = [r for r in rows if r["born_by"].strip() == "UNRECEIPTED"]
    by_kind: dict[str, int] = {}
    for r in un:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    with capsys.disabled():
        print(f"\nRECEIPTS: {len(rows)} rules registered · UNRECEIPTED {len(un)} "
              + "(" + ", ".join(f"{k} {n}" for k, n in sorted(by_kind.items())) + ")")
    assert len(un) <= len(rows)      # the register can only ever be honest about itself
