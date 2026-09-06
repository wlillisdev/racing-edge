"""Frank the form — the grunt work nobody does, done bounded.

Take a horse's recent races and check how many of the rivals it ran against have
WON or PLACED since. If several have, the form line was solid — the horse mixed
with animals that turned out useful. That's franking, and it's the tiebreaker
because it's pure legwork.

THE TRAP (learned the hard way): you cannot frank a race that just happened — the
beaten horses haven't had time to run again, so "0 franked" there means "too soon",
NOT "thin form". So we walk back from the most recent race to the most recent one
that is actually FRANKABLE: where at least two rivals have re-run and so can be
judged. The real denominator is `rivals_ran_since`, not the field size.

Bounded hard so it isn't a fetch-storm: at most `max_lookback` races back, only the
first `cap` rivals each. The counting is pure; the fetching is isolated behind the
client protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from racing_edge.data.normalise import past_runs_from_raw, results_from_raw
from racing_edge.domain.models import PastRun


class _Fetcher(Protocol):
    def results_by_date(self, date_str: str) -> dict: ...
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...


@dataclass(frozen=True)
class Franking:
    last_race_date: date | None  # the race we actually franked (old enough to judge)
    rivals_checked: int          # rivals from that race we looked at
    rivals_ran_since: int        # of those, how many have run AGAIN at all — the real denominator
    rivals_franked: int          # of those, how many won or placed since
    note: str

    @property
    def is_franked(self) -> bool:
        # a fair sample of rivals re-ran and at least two went on to win/place
        return self.rivals_ran_since >= 2 and self.rivals_franked >= 2

    @property
    def is_thin(self) -> bool:
        # the sample re-ran and the form did NOT stack up — the ONLY case worth a veto.
        # "too soon" (rivals_ran_since < 2) is deliberately NOT thin: absence of a
        # re-run is the calendar, not evidence against the horse.
        # RECALIBRATED 2026-07-25 (the Saturday wipe-out: the veto crossed off every
        # candidate on the best card of the week): 1 placer from 2 re-runners was
        # scoring 'thin' — that's an ambiguous small sample, not evidence of a hollow
        # race. Thin now means a FAIR sample re-ran and NOBODY placed. Franking is a
        # tiebreaker (#15), and an ambiguous frank is no frank at all.
        return self.rivals_ran_since >= 3 and self.rivals_franked == 0


def _scored_after(runs: tuple[PastRun, ...], after: date,
                  before: date | None = None) -> tuple[bool, bool]:
    """(ran_since, placed_since) for a rival's runs strictly after `after` — and,
    for backtests, strictly BEFORE `before` (no look-ahead into the future)."""
    later = [r for r in runs if r.date > after and (before is None or r.date < before)]
    placed = any(r.position is not None and r.position <= 3 for r in later)
    return bool(later), placed


def frank_form(client: _Fetcher, horse_id: str, history: tuple[PastRun, ...],
               cap: int = 6, max_lookback: int = 3,
               as_of: date | None = None, code: str | None = None) -> Franking:
    """Frank the most recent FRANKABLE race in `horse_id`'s history — the most
    recent one where at least two rivals have run again since (so it can be judged).
    Walks back at most `max_lookback` races. Returns a Franking summary; if nothing
    is frankable yet (recent form too fresh), is_franked and is_thin are both False.

    With `code`, the walk prefers SAME-CODE races (2026-07-21 audit: a code-switcher's
    flat pick was being franked — or vetoed — on its recent jumps races while the
    relevant flat form went unexamined). Falls back to any code only when the horse
    has no same-code past at all."""
    if not history:
        return Franking(None, 0, 0, 0, "no prior form to frank")

    pool = history
    if code:
        from racing_edge.domain.units import race_code
        same = tuple(h for h in history
                     if h.race_type and race_code(h.race_type) == code)
        pool = same or history

    refused = None
    for last in pool[:max_lookback]:
        if not (last.race_id and last.date):
            continue
        # THE SCAR OF 2026-09-06 (the 07:30 nap run DIED here, unhandled: HTTP
        # 422 'start date must be 12 months or less in the past'): the pick's
        # frankable race can be older than the results-by-DATE door serves.
        # The results-by-ID door serves any race in full (live-checked on a
        # 16-month-old race, 2026-09-05) — ask it first; fall back to the date
        # door only when the client has no id door; and a refusal from either
        # is an UNREAD frank, never a dead run.
        try:
            field = _field_for(client, last)
        except Exception as exc:                       # RacingAPIError, network, plan gate
            refused = exc
            continue
        if field is None:
            continue
        rivals = [rr.horse_id for rr in field.runners
                  if rr.horse_id and rr.horse_id != horse_id][:cap]
        ran_since = franked = 0
        for rid in rivals:
            runs = past_runs_from_raw(client.horse_results(rid), rid)
            ran, placed = _scored_after(runs, last.date, before=as_of)
            ran_since += int(ran)
            franked += int(placed)
        if ran_since >= 2:                       # frankable — enough rivals have re-run to judge
            # three-way label mirroring is_franked/is_thin (2026-07-25 audit: the
            # note said 'thin' on a 1/5 frank that the recalibration deliberately
            # no longer vetoes — the email must not say what the code doesn't mean)
            verdict = ("FRANKED" if franked >= 2
                       else "THIN (nobody placed)" if ran_since >= 3 and franked == 0
                       else "mixed/ambiguous — no frank either way")
            return Franking(last.date, len(rivals), ran_since, franked,
                            f"{last.date.isoformat()} race {verdict}: "
                            f"{franked}/{ran_since} re-runners won/placed since")

    if refused is not None:
        return Franking(None, 0, 0, 0,
                        f"frank UNREAD — the results door refused "
                        f"({refused.__class__.__name__}); not a thin frank, not a veto")
    return Franking(pool[0].date, 0, 0, 0,
                    "too soon to frank — rivals from recent races haven't run again yet")


def _field_for(client, last: PastRun):
    """The past race's full field: by ID when the client has that door (no
    date limit), else by DATE (12 months on the standard plan). None when the
    race is not in the answer."""
    by_id = getattr(client, "result_by_id", None)
    if callable(by_id):
        doc = by_id(last.race_id)
        if doc and doc.get("runners"):
            fields = results_from_raw({"results": [doc]})
            return fields[0] if fields else None
    matches = results_from_raw(client.results_by_date(last.date.isoformat()))
    return next((r for r in matches if r.race_id == last.race_id), None)
