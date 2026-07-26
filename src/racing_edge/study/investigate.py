"""The investigator's evidence tools — the model PULLS threads instead of answering
a questionnaire (#5, #15, #27).

Two grounded, read-only lookups the self-study can call mid-thought:
  horse_runs    — a horse's full past runs WITH comments (any horse_id it has seen)
  race_result   — a past race's FULL result: field, finishing order, SPs, comments,
                  and each runner's horse_id (so threads can be chained). This is the
                  FRANKING door: "who did he beat that day — and what did they do since?"

Everything returned is verbatim API data; blanks render as OWED. Every call is logged
to a trail the master can audit — no invisible evidence.
"""

from __future__ import annotations

from collections.abc import Callable

from racing_edge.data.normalise import past_runs_from_raw
from racing_edge.domain.models import Race
from racing_edge.report.restudy import _past_line  # same honest rendering

TOOLS = [
    {
        "name": "horse_runs",
        "description": "Full past runs (with in-running comments where the data has "
                       "them) for a horse, by horse_id. Use ids from the readout's "
                       "runners or from a race_result lookup.",
        "input_schema": {
            "type": "object",
            "properties": {"horse_id": {"type": "string"}},
            "required": ["horse_id"],
        },
    },
    {
        "name": "race_result",
        "description": "The FULL result of a past race by race_id (ids appear on each "
                       "past-run line of a horse_runs lookup): finishing order, SPs, "
                       "comments, and each runner's horse_id — for FRANKING the form: "
                       "check what the horses it beat (or lost to) have done since.",
        "input_schema": {
            "type": "object",
            "properties": {"race_id": {"type": "string"}},
            "required": ["race_id"],
        },
    },
    {
        "name": "trainer_angle",
        "description": "The trainer's strike-rate BY HORSE AGE (trainer_id from the "
                       "readout). The specialty read: a yard with an amazing record "
                       "for exactly today's TYPE of horse — e.g. its 4yo chasers — "
                       "is a huge tick; a yard that never wins with them is a "
                       "warning. Ask it when the type looks distinctive.",
        "input_schema": {
            "type": "object",
            "properties": {"trainer_id": {"type": "string"}},
            "required": ["trainer_id"],
        },
    },
]


class _Client:
    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]: ...
    def result_by_id(self, race_id: str) -> dict | None: ...
    def trainer_ages(self, trainer_id: str) -> list[dict]: ...


def make_executor(client: _Client, race: Race) -> Callable[[str, dict], str]:
    """Bind the tools to the real API. `race` scopes the honesty rule: history returned
    for lookups is cut to runs BEFORE this race's date (no look-ahead, ever)."""

    def horse_runs(horse_id: str) -> str:
        runs = past_runs_from_raw(client.horse_results(horse_id), horse_id)
        runs = tuple(h for h in runs if h.date < race.date)
        if not runs:
            return "No runs before this race through the window (OWED)."
        return "\n".join(_past_line(h) + f"   race_id={h.race_id}" for h in runs[:10])

    def race_result(race_id: str) -> str:
        doc = client.result_by_id(race_id)
        rows = (doc or {}).get("runners") or []
        if not rows:
            return "Result not available through the window (OWED)."
        lines = []
        for r in sorted(rows, key=lambda x: (not str(x.get("position", "")).isdigit(),
                                             int(x["position"]) if str(
                                                 x.get("position", "")).isdigit() else 99)):
            pos = str(r.get("position") or "—")
            comment = str(r.get("comment") or "").strip() or "OWED"
            lines.append(f"  {pos:>3}  {r.get('horse') or '?'!s:24} "
                         f"sp {r.get('sp_dec') or '?'}  id={r.get('horse_id') or '?'}  "
                         f"{comment}")
        return "\n".join(lines[:20])

    def trainer_angle(trainer_id: str) -> str:
        rows = client.trainer_ages(trainer_id) if hasattr(client, "trainer_ages") else []
        if not rows:
            return "Trainer age analysis not available through the window (OWED)."
        lines = []
        for r in rows[:12]:
            runs = r.get("runners") or r.get("runs") or r.get("total_runs") or 0
            wins = r.get("1st") or r.get("wins") or 0
            age = r.get("age") or r.get("horse_age") or "?"
            try:
                pct = f" ({100 * int(wins) / int(runs):.0f}%)" if int(runs) else ""
            except (ValueError, ZeroDivisionError, TypeError):
                pct = ""
            lines.append(f"  age {age}: {wins} wins from {runs} runs{pct}")
        return "\n".join(lines) or "OWED"

    def execute(name: str, args: dict) -> str:
        try:
            if name == "horse_runs":
                return horse_runs(str(args.get("horse_id", "")))
            if name == "race_result":
                return race_result(str(args.get("race_id", "")))
            if name == "trainer_angle":
                return trainer_angle(str(args.get("trainer_id", "")))
            return f"Unknown tool {name!r}."
        except Exception as exc:                       # a bad lookup must not kill the study
            return f"Lookup failed ({exc.__class__.__name__}) — treat as OWED."

    return execute
