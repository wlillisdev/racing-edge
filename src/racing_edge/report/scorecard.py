"""The contender scorecard — the forcing function against half-arsed reads.

For each readable race it runs EVERY lens across the live contenders and lays them
side by side, so no horse is read in isolation and no angle is skipped. Crucially it
prints what it COULD NOT check — the OWED cells — instead of hiding it, so a lazy gap
is a visible blank, not a silent miss. The machine does the tireless reading; the
human judges a complete brief. Pure: a race + its evidence in, a Scorecard out.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from racing_edge.domain.mark import mark_read
from racing_edge.domain.models import PastRun, Race
from racing_edge.domain.tells import match_tells
from racing_edge.domain.units import going_band
from racing_edge.selection.case import RunnerEvidence


@dataclass(frozen=True)
class Cell:
    text: str
    owed: bool = False          # True = we COULD NOT check it (data missing), not "checked, absent"


@dataclass(frozen=True)
class Column:
    horse: str
    rank: int | None            # market rank (1 = fav)
    price: float | None
    cells: tuple[tuple[str, Cell], ...]   # (lens label, cell)
    tells: tuple[str, ...]


@dataclass(frozen=True)
class Scorecard:
    course: str
    off_time: str
    race_type: str
    columns: tuple[Column, ...]

    @property
    def owed(self) -> tuple[str, ...]:
        return tuple(f"{c.horse} — {label}"
                     for c in self.columns for label, cell in c.cells if cell.owed)


# --------------------------------------------------------------------------- #
# lens helpers
# --------------------------------------------------------------------------- #
def _won(h: PastRun) -> bool:
    return h.position == 1


def _placed(h: PastRun) -> bool:
    return h.position is not None and h.position <= 3


def _same_course(h: PastRun, race: Race) -> bool:
    return (bool(h.course and race.course)
            and h.course.strip().lower() == race.course.strip().lower())


def _same_trip(h: PastRun, race: Race) -> bool:
    return bool(h.distance_f and race.distance_f) and abs(h.distance_f - race.distance_f) <= 1.0


def _same_going(h: PastRun, race: Race) -> bool:
    target = race.going_detailed or race.going
    return bool(h.going and target) and going_band(h.going) == going_band(target)


# each lens: (RunnerEvidence, Race) -> Cell. owed=True means "go and get it".
def _mark(ev: RunnerEvidence, race: Race) -> Cell:
    mr = mark_read(ev.runner.official_rating, ev.history)
    if mr.today is None:
        return Cell("OR?", owed=True)                       # no mark on the card
    if mr.last_won is None:
        return Cell(f"OR{mr.today}", owed=True)             # no prior win to judge it against
    return Cell(f"OR{mr.today} {mr.verdict}")               # WELL-IN / +Nlb — the decisive read


def _course(ev: RunnerEvidence, race: Race) -> Cell:
    if not ev.history:
        return Cell("·", owed=True)
    w = sum(1 for h in ev.history if _won(h) and _same_course(h, race))
    p = sum(1 for h in ev.history if _placed(h) and not _won(h) and _same_course(h, race))
    if w:
        return Cell(f"{w}W" + (f"+{p}P" if p else ""))   # depth: 2W beats 1W (Friday's lesson)
    return Cell(f"{p}P" if p else "—")


def _trip(ev: RunnerEvidence, race: Race) -> Cell:
    if not ev.history:
        return Cell("·", owed=True)
    return Cell("✓" if any(_placed(h) and _same_trip(h, race) for h in ev.history) else "—")


def _going(ev: RunnerEvidence, race: Race) -> Cell:
    if not ev.history:
        return Cell("·", owed=True)
    return Cell("✓" if any(_placed(h) and _same_going(h, race) for h in ev.history) else "—")


def _manner(ev: RunnerEvidence, race: Race) -> Cell:
    # the API carries no in-running comment — rule #1 (read the finish) is blind. OWED.
    return Cell("·", owed=True)


def _yard(ev: RunnerEvidence, race: Race) -> Cell:
    if not ev.stable_runs:
        return Cell("?", owed=True)
    strike = f"{round(100 * ev.stable_wins / ev.stable_runs)}%"
    local = "moffatt" in (ev.runner.trainer or "").lower() and "cartmel" in race.course.lower()
    return Cell(strike + (" ★LOCAL" if local else ""))


def _jockey(ev: RunnerEvidence, race: Race) -> Cell:
    r = ev.runner
    if r.jockey_id and r.jockey_id in ev.stable_jockey_ids:
        return Cell("YARD#1")                       # the yard's main rider booked = intent
    if not r.jockey:
        return Cell("?", owed=True)
    return Cell(r.jockey.split()[-1][:9])


def _headgear(ev: RunnerEvidence, race: Race) -> Cell:
    return Cell("1st-HG" if ev.runner.headgear_first_time else "—")


def _move(ev: RunnerEvidence, race: Race) -> Cell:
    # morning -> now movement isn't in the data (no live-odds feed). The smart-money
    # read (#17/#18) can't be made yet — OWED, and flagged as the door to open next.
    return Cell("·", owed=True)


_LENSES: tuple[tuple[str, Callable[[RunnerEvidence, Race], Cell]], ...] = (
    ("mark", _mark),
    ("course", _course),
    ("trip", _trip),
    ("going", _going),
    ("manner", _manner),
    ("yard", _yard),
    ("jockey", _jockey),
    ("h'gear", _headgear),
    ("mkt-move", _move),
)


def build_scorecard(race: Race, evidence: list[RunnerEvidence], top_n: int = 4) -> Scorecard:
    """The top `top_n` contenders by market rank, each read on EVERY lens, side by side."""
    by_id = {ev.runner.horse_id: ev for ev in evidence}
    priced = sorted([r for r in race.runners if r.odds.consensus and r.odds.consensus > 1],
                    key=lambda r: r.odds.consensus)              # type: ignore[arg-type,return-value]
    ranks = {r.horse_id: i + 1 for i, r in enumerate(priced)}
    field = priced[:top_n] if priced else list(race.runners)[:top_n]
    columns: list[Column] = []
    for r in field:
        ev = by_id.get(r.horse_id) or RunnerEvidence(runner=r)
        cells = tuple((label, fn(ev, race)) for label, fn in _LENSES)
        columns.append(Column(horse=r.horse or r.horse_id, rank=ranks.get(r.horse_id),
                              price=r.odds.consensus, cells=cells,
                              tells=match_tells(r, race, ev.history)))
    return Scorecard(course=race.course, off_time=race.off_time,
                     race_type=race.race_type, columns=tuple(columns))


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
_W = 14


def _fit(s: str) -> str:
    return (s[:_W - 1]).ljust(_W)


def _price(c: Column) -> str:
    r = f"#{c.rank}" if c.rank else "#?"
    return f"{r} {c.price:.1f}" if c.price else r


def render_scorecard(sc: Scorecard) -> str:
    lines = [
        "=" * (12 + _W * len(sc.columns)),
        f"  {sc.course} {sc.off_time} — {sc.race_type}   (contenders by market)",
        "  " + "lens".ljust(11) + "".join(_fit(c.horse) for c in sc.columns),
        "  " + "rank/price".ljust(11) + "".join(_fit(_price(c)) for c in sc.columns),
        "  " + "-" * (11 + _W * len(sc.columns)),
    ]
    for i, (label, _) in enumerate(_LENSES):
        row = "  " + label.ljust(11)
        for c in sc.columns:
            cell = c.cells[i][1]
            row += _fit(cell.text + ("?" if cell.owed else ""))
        lines.append(row)
    for c in sc.columns:
        for t in c.tells:
            lines.append(f"    ★ {c.horse}: {t}")
    if sc.owed:
        lines.append("  OWED — couldn't check, go and get it (a blank is not a pass):")
        for o in sc.owed:
            lines.append(f"    · {o}")
    lines.append("  '?' = OWED (data missing). You judge — complete brief, gaps named.")
    return "\n".join(lines)
