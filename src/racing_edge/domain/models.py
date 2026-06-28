"""The internal contracts — frozen dataclasses every layer speaks.

Raw Racing API dicts are normalised into these ONCE (see data.normalise), so no
downstream code re-derives position / won / sp / going from raw JSON. Fields are
biased toward winter National Hunt (jumps): going, days-since-run, headgear,
wind-surgery, breeding, trainer/jockey, official mark — and draw is optional
because it's usually irrelevant over jumps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from racing_edge.domain.season import racing_season
from racing_edge.domain.units import going_band, race_code


@dataclass(frozen=True)
class Odds:
    """The prices for one runner. `consensus` (median across books) is the
    decision price; `sp` is the settled price for honest grading and CLV."""

    morning: float | None = None
    consensus: float | None = None
    late: float | None = None
    sp: float | None = None
    bsp: float | None = None


@dataclass(frozen=True)
class PastRun:
    """One historical run for a horse — the raw material for the proven-at-the-
    level, ground, trip, course and weight reads."""

    date: date
    position: int | None
    race_class: int | None = None
    going: str = ""
    distance_f: float | None = None
    weight_lbs: int | None = None
    course: str = ""
    race_type: str = ""
    field_size: int | None = None    # how competitive the race was — quality of a win
    race_id: str = ""                # to fetch that race's field and FRANK the form

    @property
    def won(self) -> bool:
        return self.position == 1

    @property
    def placed(self) -> bool:
        return self.position is not None and self.position in (2, 3)


@dataclass(frozen=True)
class Runner:
    horse_id: str
    horse: str
    trainer: str = ""
    trainer_id: str = ""
    jockey: str = ""
    jockey_id: str = ""
    claim_lbs: int | None = None     # a claiming/conditional jockey's allowance — weight off the back
    age: int | None = None
    sex: str = ""
    weight_lbs: int | None = None
    official_rating: int | None = None
    rpr: int | None = None
    form: str = ""
    days_since_run: int | None = None
    headgear: str = ""
    headgear_first_time: bool = False  # first time in this headgear — trainer looking for improvement
    wind_surgery: str = ""           # e.g. "1" = first time after a wind op (a positive signal)
    trainer_14d_runs: int | None = None   # the yard's recent form — the owner's "critical" stable read
    trainer_14d_wins: int | None = None
    draw: int | None = None          # usually None/irrelevant over jumps
    sire: str = ""
    sire_id: str = ""
    dam: str = ""
    dam_id: str = ""
    damsire: str = ""
    damsire_id: str = ""
    odds: Odds = field(default_factory=Odds)
    spotlight: str = ""              # narrative — for the AI to read, never to score


@dataclass(frozen=True)
class Race:
    race_id: str
    course: str
    off_time: str
    date: date
    race_type: str = ""              # Hurdle / Chase / NH Flat / Flat ...
    is_handicap: bool = False
    is_novice: bool = False          # novice/maiden = UNEXPOSED horses, form unreliable — avoid
    is_all_weather: bool = False     # AW = dodgy: non-triers + sand kickback buries slow starts
    race_class: int | None = None
    distance_f: float | None = None
    going: str = ""
    going_detailed: str = ""
    region: str = ""
    runners: tuple[Runner, ...] = ()

    @property
    def code(self) -> str:
        """'jump' | 'flat'."""
        return race_code(self.race_type)

    @property
    def going_band(self) -> str:
        return going_band(self.going_detailed or self.going)

    @property
    def season(self) -> str:
        """'nh_winter' | 'flat_summer' | 'shoulder' — for season-stratified truth."""
        return racing_season(self.date)

    @property
    def field_size(self) -> int:
        return len(self.runners)

    @property
    def is_readable_handicap(self) -> bool:
        """The race-selection GATE: an established handicap whose form is exposed and
        trustworthy (jumps OR flat). Excludes novice/maiden/bumper — where the form
        book doesn't apply. Race selection comes first; this is what enforces it."""
        return self.is_handicap and not self.is_novice


@dataclass(frozen=True)
class RunnerResult:
    horse_id: str
    position: int | None        # finishing position; None for non-completions
    status: str = ""            # "" finished, else F/U/P/PU/RR/etc (faller, pulled-up...)
    sp_dec: float | None = None
    bsp: float | None = None
    beaten_lengths: float | None = None
    horse: str = ""             # name — for the study/post-mortem
    comment: str = ""           # in-running comment — read the FINISH, not the figures

    @property
    def won(self) -> bool:
        return self.position == 1

    def placed(self, places: int) -> bool:
        return self.position is not None and self.position <= places


@dataclass(frozen=True)
class RaceResult:
    race_id: str
    date: date
    runners: tuple[RunnerResult, ...] = ()

    def of(self, horse_id: str) -> RunnerResult | None:
        return next((r for r in self.runners if r.horse_id == horse_id), None)

    @property
    def favourite(self) -> RunnerResult | None:
        """The SP-favourite (shortest priced finisher with a price)."""
        priced = [r for r in self.runners if r.sp_dec and r.sp_dec > 1.0]
        return min(priced, key=lambda r: r.sp_dec) if priced else None  # type: ignore[arg-type,return-value]


@dataclass(frozen=True)
class Selection:
    """One pick — the owner's, or a benchmark's. `reasons` is the transparent
    case (named signal lines), never a black-box score."""

    date: date
    race_id: str
    horse_id: str
    horse: str
    system: str                       # "method" (the owner), "favourite", ...
    price_taken: float | None = None  # the price actually available when picked
    reasons: tuple[str, ...] = ()
    confidence: int = 0               # 1-3, the owner's own confidence; 0 = unset
