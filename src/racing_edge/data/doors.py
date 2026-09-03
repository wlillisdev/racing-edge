"""THE LIVE DOOR CHECK — every door the scheduled tasks walk through, opened
once with a known live input, red/green with the real error.

THE SCAR (2026-09-02 22:00, the box): settle FAILED and learn CRASHED on
HTTP 422 — one API call carried the wrong parameter name
(`region_codes` copied from the racecards door onto the results door, which
takes `region` — school/fetch.py had already proven that live). 282 tests,
every one of them against a FAKE client, stayed green through it. The
master: "even after all your testing — my point exactly." A test pinned
against a mock proves the CODE's shape held; it cannot prove the API's
shape didn't move under it. Law 6: a live door gets a live test, the same
day — so here is the standing one. It opens every door the box's tasks
use, once, with a real input taken off today's own card, and reports each
one OK or FAIL with the API's own words. Wired into the 09:30 health task
(health.py calls check_doors) and runnable alone on the box the moment
something smells wrong:

    PYTHONPATH=src python -m racing_edge.data.doors

Nine doors, at most nine HTTP calls (fewer when an early door has nothing
to hand the next one — see check_doors below). Never raises: a dead door
is a row in the list, not a crash of the watchman.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from racing_edge.data.normalise import racecards_from_raw
from racing_edge.domain.units import uk_today

# the order the box's own tasks open them in — racecards first, everything
# else either off today's card or off yesterday's results
DOORS: list[str] = [
    "racecards",
    "results_by_date",
    "result_by_id",
    "horse_results",
    "horse_distance_times",
    "trainer_jockeys",
    "trainer_course",
    "jockey_course",
    "trainer_ages",
]


def _err(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc)[:160]}"


def _detail(value: Any, unit: str) -> str:
    """One phrase per shape: 'doc' for a raw dict, 'N <unit>' for a non-empty
    list, 'empty' for None or an empty list — an empty answer is a fact the
    door reported honestly, not a refused door."""
    if isinstance(value, dict):
        return "doc"
    if isinstance(value, list):
        return f"{len(value)} {unit}" if value else "empty"
    return "empty"


def _try(name: str, fn: Callable[[], Any], unit: str) -> tuple[str, bool, str]:
    try:
        return name, True, _detail(fn(), unit)
    except Exception as exc:                       # noqa: BLE001 — a door check
        return name, False, _err(exc)               # must never itself crash


def check_doors(client, today: date | None = None) -> list[tuple[str, bool, str]]:
    """Open every door once, in DOORS order. Returns [(door, ok, detail), ...].

    racecards runs first and its first fully-tagged runner (horse_id AND
    trainer_id AND jockey_id present) supplies the known input for the six
    per-horse/trainer/jockey doors — a dead racecards door skips those six
    (ok=False, "skipped — no card to try") rather than hiding whether THEY
    are open. results_by_date (yesterday) is independent of the card; its
    first race_id feeds result_by_id, which is a happy skip (ok=True, "no
    race id to try") when the day's results carried none, and an unhappy
    one (ok=False, "skipped — no results to try") when results_by_date
    itself failed. Never raises.
    """
    today = today or uk_today()
    yday = today - timedelta(days=1)
    rows: list[tuple[str, bool, str]] = []

    # ---- 1. racecards — the root: every id below is drawn from its runners
    races: list = []
    card_ok = False
    try:
        doc = client.racecards("today")
        races = racecards_from_raw(doc) if doc is not None else []
        rows.append(("racecards", True, _detail(races, "races")))
        card_ok = True
    except Exception as exc:
        rows.append(("racecards", False, _err(exc)))

    horse_id = trainer_id = jockey_id = ""
    if card_ok:
        for race in races:
            for runner in getattr(race, "runners", ()):
                if runner.horse_id and runner.trainer_id and runner.jockey_id:
                    horse_id, trainer_id, jockey_id = (
                        runner.horse_id, runner.trainer_id, runner.jockey_id)
                    break
            if horse_id:
                break

    # ---- 2. results_by_date — yesterday, needs nothing from racecards
    results_doc: Any = None
    results_ok = False
    try:
        results_doc = client.results_by_date(yday.isoformat())
        result_rows = results_doc.get("results") if isinstance(results_doc, dict) else results_doc
        rows.append(("results_by_date", True, _detail(result_rows, "rows")))
        results_ok = True
    except Exception as exc:
        rows.append(("results_by_date", False, _err(exc)))

    # ---- 3. result_by_id — the first race_id out of yesterday's results doc
    if not results_ok:
        rows.append(("result_by_id", False, "skipped — no results to try"))
    else:
        race_id = ""
        for r in (result_rows or []) if isinstance(result_rows, list) else []:
            rid = r.get("race_id") if isinstance(r, dict) else None
            if rid:
                race_id = rid
                break
        if not race_id:
            rows.append(("result_by_id", True, "no race id to try"))
        else:
            rows.append(_try("result_by_id", lambda: client.result_by_id(race_id), "rows"))

    # ---- 4-9. per-horse / per-trainer / per-jockey doors — need the card's ids
    dependents: list[tuple[str, Callable[[], Any]]] = [
        ("horse_results", lambda: client.horse_results(horse_id)),
        ("horse_distance_times", lambda: client.horse_distance_times(horse_id)),
        ("trainer_jockeys", lambda: client.trainer_jockeys(trainer_id)),
        ("trainer_course", lambda: client.trainer_course(trainer_id)),
        ("jockey_course", lambda: client.jockey_course(jockey_id)),
        ("trainer_ages", lambda: client.trainer_ages(trainer_id)),
    ]
    if not card_ok or not horse_id:
        for name, _fn in dependents:
            rows.append((name, False, "skipped — no card to try"))
    else:
        for name, fn in dependents:
            rows.append(_try(name, fn, "rows"))

    return rows


def render(rows: list[tuple[str, bool, str]]) -> list[str]:
    """One line per door, plus a closing tally — the shape health.py prints."""
    lines = [f"  {'✓' if ok else '✗'} door {name} — {detail}" for name, ok, detail in rows]
    opened = sum(1 for _, ok, _ in rows if ok)
    lines.append(f"  doors: {opened}/{len(rows)} open")
    return lines


def all_open(rows: list[tuple[str, bool, str]]) -> bool:
    return all(ok for _, ok, _ in rows)


def main(argv: list[str] | None = None) -> int:
    from racing_edge.data.client import get_client

    client = get_client()
    rows = check_doors(client)
    for line in render(rows):
        print(line)
    return 0 if all_open(rows) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
