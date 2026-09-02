"""Pure racing-unit converters — odds, going, distance, form, code.

Salvaged and consolidated from the old src/helpers.py and the scattered copies
that drifted across the root scripts (the audits found 3-5 near-identical
parsers). One home, one behaviour, fully tested.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# race code — jump vs flat (this system is jumps-first)
# --------------------------------------------------------------------------- #
_JUMP_TYPES = ("chase", "hurdle", "nh flat", "national hunt flat", "bumper")


def race_code(race_type: str) -> str:
    """'jump' | 'flat' from the race type string."""
    t = (race_type or "").strip().lower()
    if any(k in t for k in _JUMP_TYPES):
        return "jump"
    return "flat"


def is_jump(race_type: str) -> bool:
    return race_code(race_type) == "jump"


def uk_today():
    """THE RACING DAY — Europe/London, never the box's UTC clock (2026-07-25
    reliability audit; fourth audit 2026-09-02 F19: eight sites still asked
    the box's own clock). Every ledger row, default day and cutoff keys on this."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Europe/London")).date()


def norm_horse_name(s: str) -> str:
    """ONE way to compare horse names (second audit 2026-09-02, bot E: the
    danger was graded by exact string match — a curly apostrophe or an '(IRE)'
    suffix scored a present danger as absent; fourth audit, bot B5: three
    more ad-hoc strip().lower() matches lived in cli/nap.py and cli/learn.py):
    lowercase, straight quotes, no country suffix, single spaces."""
    import re
    s = (s or "").replace("’", "'").replace("‘", "'").replace("`", "'")
    s = re.sub(r"\s*\([A-Za-z]{2,3}\)\s*$", "", s.strip())
    return re.sub(r"\s+", " ", s).strip().lower()


def book_code(race_type: str | None) -> str | None:
    """The SHAPE BOOK's letter for a race type — F / H / C / N — ONE SITE
    (audit 2026-09-02: byte-identical copies lived in cli/nap.py and
    pipeline/nap.py, and neither knew 'NH Flat'). None = not a book code."""
    t = (race_type or "").strip().lower()
    if not t:
        return None
    if t == "flat":
        return "F"
    if "hurdle" in t:
        return "H"
    if "chase" in t:
        return "C"
    if "nh flat" in t or "bumper" in t or "national hunt flat" in t:
        return "N"
    return None


# --------------------------------------------------------------------------- #
# going — canonical band (winter jumps lives on the soft end)
# --------------------------------------------------------------------------- #
def going_band(going: str) -> str:
    """Canonical ground band: firm / good / soft / heavy / aw / unknown.

    'heavy' is tested before 'soft' so 'Soft (Heavy in places)' reads as the
    more testing band — the winter-jumps-relevant call.
    """
    s = (going or "").strip().lower()
    if not s:
        return "unknown"
    if "heavy" in s:
        return "heavy"
    if "soft" in s or "yielding" in s or "holding" in s:
        return "soft"
    if "firm" in s or "hard" in s:
        return "firm"
    if "good" in s:
        return "good"
    if any(k in s for k in ("standard", "slow", "fast", "tapeta", "polytrack", "fibresand")):
        return "aw"
    return "unknown"


# --------------------------------------------------------------------------- #
# distance -> furlongs
# --------------------------------------------------------------------------- #
def distance_to_furlongs(value: object) -> float | None:
    """Parse a distance to furlongs. Accepts a number (already furlongs) or a
    string like '3m2f', '2m4½f', '5f', '1m'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    s = str(value).strip().lower().replace("½", ".5").replace("¼", ".25").replace("¾", ".75")
    if not s:
        return None
    miles = re.search(r"(\d+(?:\.\d+)?)\s*m", s)
    furlongs = re.search(r"(\d+(?:\.\d+)?)\s*f", s)
    total = 0.0
    if miles:
        total += float(miles.group(1)) * 8.0
    if furlongs:
        total += float(furlongs.group(1))
    if total == 0.0:
        try:
            total = float(s)
        except ValueError:
            return None
    return round(total, 2) if total > 0 else None


# --------------------------------------------------------------------------- #
# form string -> finishing positions ('0' = 10th-or-worse, NOT a win)
# --------------------------------------------------------------------------- #
def parse_form(form: str) -> list[int]:
    """Digits of a form string as finishing positions, oldest->newest.

    '0' means finished outside the first nine (a bad run), mapped to 10.
    Non-finishers (P, F, U, etc.) are skipped — handle them as flags elsewhere.
    """
    return [10 if c == "0" else int(c) for c in (form or "") if c.isdigit()]


# --------------------------------------------------------------------------- #
# decimal odds -> fractional display
# --------------------------------------------------------------------------- #
_FRACTIONS: tuple[tuple[float, str], ...] = (
    (1.2, "1/5"), (1.25, "1/4"), (1.33, "1/3"), (1.4, "2/5"), (1.5, "1/2"),
    (1.62, "8/13"), (1.73, "8/11"), (1.8, "4/5"), (1.91, "10/11"), (2.0, "evens"),
    (2.5, "6/4"), (3.0, "2/1"), (3.5, "5/2"), (4.0, "3/1"), (4.5, "7/2"),
    (5.0, "4/1"), (6.0, "5/1"), (7.0, "6/1"), (8.0, "7/1"), (9.0, "8/1"),
    (11.0, "10/1"), (13.0, "12/1"), (17.0, "16/1"), (21.0, "20/1"), (34.0, "33/1"),
)


def format_odds(decimal: float | None) -> str:
    """Nearest conventional fractional label for a decimal price."""
    if not decimal or decimal <= 1.0:
        return "—"
    return min(_FRACTIONS, key=lambda f: abs(f[0] - decimal))[1]
