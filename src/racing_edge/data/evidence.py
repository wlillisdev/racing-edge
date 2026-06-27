"""Build the evidence the method needs — the bridge from a live card to selection.

For each runner it gathers: past runs (the proven-at-level reads), the yard's
14-day form (already on the card — the owner's 'critical' stable read), and the
stable's number-one jockey(s) (for the jockey-intent read). Returns the
RunnerEvidence list that selection.pick_race consumes.

`stable_jockeys_from_analysis` is pure and tested; `build_evidence` orchestrates
the fetches.
"""

from __future__ import annotations

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


def build_evidence(race: Race, client: _Fetcher) -> list[RunnerEvidence]:
    # cache the trainer-analysis rows once per yard, derive both stable jockeys
    # and the A/E from the same fetch.
    cache: dict[str, tuple[frozenset[str], float | None, int]] = {}
    evidence: list[RunnerEvidence] = []
    for r in race.runners:
        history = past_runs_from_raw(client.horse_results(r.horse_id))
        tid = r.trainer_id
        if tid not in cache:
            rows = client.trainer_jockeys(tid)
            ae, ae_runs = stable_ae_from_analysis(rows)
            cache[tid] = (stable_jockeys_from_analysis(rows), ae, ae_runs)
        jockeys, ae, ae_runs = cache[tid]
        evidence.append(RunnerEvidence(
            runner=r,
            history=history,
            stable_runs=r.trainer_14d_runs or 0,
            stable_wins=r.trainer_14d_wins or 0,
            stable_ae=ae,
            stable_ae_runs=ae_runs,
            stable_jockey_ids=jockeys,
            # combo record + franked count are later data feeds; default to neutral.
        ))
    return evidence
