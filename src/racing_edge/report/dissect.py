"""Dissect the day — a per-horse readout for the nightly 'go through it together' study.

For each readable handicap it lays out the WHOLE field: every runner's finishing
position, SP, and the MARKET MOVE (morning -> SP: BACKED / drifted / steady) — the facts
the API actually gives us, including the one that beat us all night, the move. The
manner / running comment is left as OWED: that's the column the human fills from the
form, where the forward reads live (#27 — stayed on -> wants further; weakened -> why).

Pure: a race + its studied runners in, a readout out.
"""

from __future__ import annotations

from racing_edge.domain.models import Race
from racing_edge.study.postmortem import StudiedRunner


def market_move(r: StudiedRunner) -> str:
    """Morning price -> SP, the smart-money read. OWED if either price is missing."""
    m, sp = r.morning_dec, r.sp_dec
    if not (m and sp and m > 1 and sp > 1):
        return "move OWED"
    if sp <= m * 0.92:
        return f"BACKED  {m:.1f}->{sp:.1f}"
    if sp >= m * 1.08:
        return f"drifted {m:.1f}->{sp:.1f}"
    return f"steady  {sp:.1f}"


def _pos(r: StudiedRunner) -> str:
    return str(r.finish_pos) if r.finish_pos else "—"


def render_race_dissection(race: Race, runners: list[StudiedRunner]) -> str:
    ordered = sorted(runners, key=lambda r: (r.finish_pos is None, r.finish_pos or 99))
    hcap = "Handicap " if race.is_handicap else ""
    lines = [
        f"  {race.course} {race.off_time} — {hcap}{race.race_type}  ({len(runners)} ran)",
        f"    {'pos':<4}{'horse':<20}{'SP':<7}{'market move':<18}manner (fill from the form)",
        "    " + "-" * 64,
    ]
    for r in ordered:
        sp = f"{r.sp_dec:.1f}" if r.sp_dec else "?"
        btn = f"  btn {r.beaten_lengths}" if r.beaten_lengths else ""
        lines.append(f"    {_pos(r):<4}{r.name[:19]:<20}{sp:<7}{market_move(r):<18}OWED{btn}")
    lines.append("    > read each line for next time (#27): stayed on -> trip up; "
                 "weakened -> trip/weight/ground; hung -> headgear; unlucky -> mark up")
    return "\n".join(lines)
