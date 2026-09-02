"""Build the evidence the method needs — the bridge from a live card to selection.

For each runner it gathers: past runs (the proven-at-level reads), the yard's
14-day form (already on the card — the owner's 'critical' stable read), and the
stable's number-one jockey(s) (for the jockey-intent read). Returns the
RunnerEvidence list that selection.pick_race consumes.

`stable_jockeys_from_analysis` is pure and tested; `build_evidence` orchestrates
the fetches.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from racing_edge.data.normalise import past_runs_from_raw
from racing_edge.domain.models import Race
from racing_edge.selection.case import RunnerEvidence

_MAIN_MIN_RIDES = 20
_MAIN_SHARE = 0.25


def _flt(v: object) -> float | None:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def stable_ae_from_analysis(rows: list[dict]) -> tuple[float | None, int]:
    """Runs-weighted Actual/Expected for the yard, from the trainer-analysis rows
    we already fetch (no extra API call). (None, 0) if A/E isn't supplied."""
    total_runs = 0.0
    weighted = 0.0
    for r in rows or []:
        runs = _flt(r.get("rides") or r.get("runners")) or 0.0
        ae = _flt(r.get("a_e") or r.get("ae") or r.get("a/e"))
        if runs > 0 and ae is not None:
            total_runs += runs
            weighted += ae * runs
    if total_runs <= 0:
        return None, 0
    return round(weighted / total_runs, 2), int(total_runs)


def course_strike_from_analysis(rows: list[dict], course: str) -> tuple[float | None, int]:
    """The yard's (win%, runs) AT THIS COURSE from trainer course-analysis rows —
    rule #10's local-master read, off data instead of prose. (None, 0) if unknown."""
    want = (course or "").strip().lower()
    if not want:
        return None, 0
    for r in rows or []:
        name = str(r.get("course") or r.get("course_name") or "").strip().lower()
        if not name or (want not in name and name not in want):
            continue
        runs = _flt(r.get("runners") or r.get("rides") or r.get("runs")) or 0.0
        wins = _flt(r.get("1st") or r.get("wins") or r.get("win")) or 0.0
        if runs > 0:
            return round(wins / runs, 2), int(runs)
    return None, 0


def trip_strike_from_analysis(rows: list[dict],
                              distance_f: float | None) -> tuple[float | None, int]:
    """The horse's (win%, runs) at ~today's DISTANCE from its distance-times rows.
    Matches within half a furlong. (None, 0) when unknown — the honest blank."""
    if not distance_f:
        return None, 0
    for r in rows or []:
        d = _flt(r.get("dist_f") or r.get("distance_f") or r.get("dist"))
        if d is None or abs(d - distance_f) > 0.5:
            continue
        runs = _flt(r.get("runners") or r.get("runs") or r.get("rides")) or 0.0
        wins = _flt(r.get("1st") or r.get("wins") or r.get("win")) or 0.0
        if runs > 0:
            return round(wins / runs, 2), int(runs)
    return None, 0


def stable_jockeys_from_analysis(rows: list[dict]) -> frozenset[str]:
    """The yard's number-one rider(s): the most-used jockey(s) clearing a real
    body of rides and a meaningful share of the yard's bookings."""
    parsed: list[tuple[str, int]] = []
    for r in rows or []:
        jid = str(r.get("jockey_id") or "")
        rides = r.get("rides") or r.get("runners") or 0
        try:
            rides = int(float(str(rides)))
        except (TypeError, ValueError):
            rides = 0
        if jid and rides > 0:
            parsed.append((jid, rides))
    if not parsed:
        return frozenset()
    total = sum(n for _, n in parsed) or 1
    top = max(n for _, n in parsed)
    return frozenset(
        jid for jid, n in parsed
        if n == top and n >= _MAIN_MIN_RIDES and n / total >= _MAIN_SHARE
    )


class _Fetcher(Protocol):
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...
    def trainer_jockeys(self, trainer_id: str) -> list[dict]: ...

    def trainer_course(self, trainer_id: str, course_id: str = "") -> list[dict]:
        return []                                    # optional — older fakes need not care

    def jockey_course(self, jockey_id: str) -> list[dict]:
        return []

    def horse_distance_times(self, horse_id: str) -> list[dict]:
        return []


def build_evidence(race: Race, client: _Fetcher, as_of: date | None = None) -> list[RunnerEvidence]:
    """Assemble each runner's evidence. `as_of` enforces NO LOOK-AHEAD for
    backtesting: a horse's history is filtered to runs strictly BEFORE that date.

    In backtest mode (as_of set) the trainer A/E and stable-jockey reads are
    SKIPPED — those come from the API's *current* analysis endpoint, which knows
    the trainer's form AFTER the race (a look-ahead leak). The card's own
    trainer_14d form is point-in-time (as of the card) and is kept. (Testing the
    A/E/jockey-intent signals historically needs trailing A/E computed from past
    results — a later build.)"""
    backtest = as_of is not None
    cache: dict[str, tuple] = {}
    evidence: list[RunnerEvidence] = []
    jcache: dict[str, tuple[float | None, int]] = {}
    for r in race.runners:
        # limit 20 (was the default 12): the form lenses now read SAME-CODE runs only,
        # and a dual-code horse whose last 12 runs are all one code would otherwise
        # have its relevant history pushed out of the window entirely (2026-07-21 audit)
        # One horse's fetch dying must not kill the whole morning (2026-07-25
        # reliability audit): the horse degrades to history-OWED, said out loud.
        try:
            history = past_runs_from_raw(client.horse_results(r.horse_id, limit=20),
                                         r.horse_id)
        except Exception as exc:
            # NAME the failure (2026-08-01: a whole Saturday of 'history fetch
            # failed' with the cause swallowed — an unnamed error is undiagnosable)
            print(f"      ⚠ evidence OWED for {r.horse} — history fetch failed: "
                  f"{exc.__class__.__name__}: {str(exc)[:100]}", flush=True)
            history = ()
        if as_of is not None:
            history = tuple(h for h in history if h.date < as_of)
        # the TRIP lens (distance-times endpoint) and the JOCKEY-AT-COURSE lens (#30) —
        # every-endpoint audit 2026-07-09: paid for, never called. Skipped in backtests
        # (current-stats look-ahead).
        try:
            trip_strike, trip_runs = (None, 0) if backtest else \
                trip_strike_from_analysis(
                    client.horse_distance_times(r.horse_id) if hasattr(
                        client, "horse_distance_times") else [], race.distance_f)
        except Exception as exc:
            # optional lens — OWED, not fatal, and NAMED (audit 2026-09-02)
            print(f"      ⚠ trip lens OWED for {r.horse}: {exc.__class__.__name__}",
                  flush=True)
            trip_strike, trip_runs = None, 0
        if backtest or not r.jockey_id:
            j_strike, j_rides = None, 0
        else:
            if r.jockey_id not in jcache:
                try:
                    jrows = client.jockey_course(r.jockey_id) if hasattr(
                        client, "jockey_course") else []
                except Exception as exc:
                    print(f"      ⚠ jockey-course lens OWED for {r.horse}: "
                          f"{exc.__class__.__name__}", flush=True)
                    jrows = []                    # optional lens — OWED, not fatal
                jcache[r.jockey_id] = course_strike_from_analysis(jrows, race.course)
            j_strike, j_rides = jcache[r.jockey_id]
        if backtest:
            jockeys, ae, ae_runs = frozenset[str](), None, 0   # no current-stats leak
            local_strike, local_runs = None, 0
        else:
            tid = r.trainer_id
            if tid not in cache:
                rows = client.trainer_jockeys(tid)
                ae, ae_runs = stable_ae_from_analysis(rows)
                crows = client.trainer_course(tid) if hasattr(client, "trainer_course") else []
                cache[tid] = (stable_jockeys_from_analysis(rows), ae, ae_runs,
                              course_strike_from_analysis(crows, race.course))
            jockeys, ae, ae_runs, (local_strike, local_runs) = cache[tid]
        evidence.append(RunnerEvidence(
            runner=r,
            history=history,
            stable_runs=r.trainer_14d_runs or 0,    # point-in-time (on the card) — kept
            stable_wins=r.trainer_14d_wins or 0,
            stable_ae=ae,
            stable_ae_runs=ae_runs,
            stable_jockey_ids=jockeys,
            local_strike=local_strike,
            local_runs=local_runs,
            trip_strike=trip_strike,
            trip_runs=trip_runs,
            jockey_course_strike=j_strike,
            jockey_course_rides=j_rides,
        ))
    return evidence
