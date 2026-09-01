"""THE SITTING FLOOR — law 5c, cut on the master's word (2026-09-01: "fix it").

Born the night of the Wakeman Stayers: the sitter ordered a two-mile Class 6
stayers' race as if it were a sprint, on a sheet that knew neither the trip,
nor the class, nor the favourite. The pick ran 4th beaten 23L; the winner
stood in the sitter's own crossed-off list; the unnamed favourite ran last.
The master: "terrible read, learn from this" — and, on the root cause
(a named gap treated as a licence instead of a stop sign, three sittings
running): "fix it".

The fix is a wall, not a habit: before any read — sitting, exam, or telly —
issues an ORDER, the reader must hold the race's CLASS, its DISTANCE, and
the FAVOURITE'S IDENTITY. Missing any one, the only legal output is a NAMED
PASS. The floor is checked FIRST, before a single horse is measured, so
enthusiasm never gets a vote.
"""

from __future__ import annotations


def sitting_floor(race_class: int | None, distance: str | None,
                  fav_named: str | None) -> str | None:
    """The wall, pure and pinnable: a reason string = the sitting is a NAMED
    PASS (do not order the race); None = the floor is met and the read may
    proceed. Empty strings and None both count as not held — a blank is not
    a pass (the ledger's own words)."""
    missing = [name for name, held in (
        ("class", race_class is not None),
        ("distance", bool(distance and str(distance).strip())),
        ("favourite", bool(fav_named and str(fav_named).strip())),
    ) if not held]
    if missing:
        return ("SITTING FLOOR (5c) — cannot read this race from here: "
                f"{', '.join(missing)} unknown. NAMED PASS — a named gap is "
                "a stop sign, never a licence.")
    return None
