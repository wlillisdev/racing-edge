"""The MORNING DEEP READ — the detective picks the nap, not the lens-counter.

Born 2026-07-05, the master's correction after two zero-chance naps and a lazy
"no-bet days" answer: *"you are the student, you can find a winner — just look harder.
Stop stupid picks."* The conviction engine now only SHORTLISTS candidate races; the
deep model (the same investigator that studies results, with the franking tools) does
the actual form-reading on the morning card and picks THE race and THE horse — or
makes the case, race by race, why nothing joins (a last resort it must earn).

Grounded like everything else: reasons only over the supplied pre-race readouts and
tool lookups, cites facts, blanks are OWED, and the pick is banked before the off.
Pure: prompts and parsing here; the model call and banking live in cli.nap.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

NAP_SYSTEM = (
    "You are an apprentice handicapper choosing THE NAP OF THE DAY for a master with "
    "30 years in the game, from the candidate races supplied (each a full pre-race "
    "readout: marks, form, manner reads, comments, market ranks). His method, which "
    "you follow exactly:\n"
    "1. RACE FIRST (#3/#31): pick the most READABLE race — decent class, exposed "
    "field, a market with an anchor. A strong horse in a dangerous race is a pass.\n"
    "2. FORM FIRST, ODDS LAST (#29): build the best horse from the jigsaw — the mark "
    "(well-in, and by how MUCH), HOW it ran (manner/comments), course/trip fit, yard "
    "intent — before weighing its price. The market confirms or warns; it never picks.\n"
    "3. ELIMINATE (#25): in your chosen race, cross off what can't win on FACTS, then "
    "beat the survivors against each other. Pick LAST.\n"
    "4. USE THE TOOLS: frank the key form (what did the beaten horses do since?), pull "
    "deeper history where a line is thin. Spend lookups on your top candidates.\n"
    "5. LOOK HARDER before passing — but a pass is CORRECT when no candidate matches "
    "the profile in rule 6. Across a full card there is usually one readable winner: "
    "dig for it, frank it, chase the threads. If after real work nothing matches, PASS "
    "and earn it — name what kills EACH candidate race. Never force the least-bad pick "
    "on a bad card: that is how both losing naps happened.\n"
    "6. THE RECORD'S WINNING PROFILE (every winner so far matched it; both losers "
    "broke it): WELL-IN — the bigger the gap the better — plus course-form depth, plus "
    "yard INTENT (in-form stable and/or its #1 rider up), at a fair price (roughly "
    "2.5-7.0), in a readable race: Class 4 or better, exposed field, anchored market. "
    "Prefer the candidate matching this profile. Departing from it demands STRONGER "
    "cited facts, said out loud in the case.\n"
    "7. USE THE BANKED LESSONS: if a LESSONS block is supplied (validated nuances the "
    "master promoted, tracked follow/oppose horses from past results), they are "
    "evidence — apply them and cite them like any other fact.\n"
    "IRON RULES: only facts from the readouts and tool results; cite the exact fact "
    "for every claim; a blank is OWED, never filled; never let the price pick.\n"
    "Answer ONLY a single JSON object, no prose around it."
)

_SCHEMA_HINT = (
    '{\n'
    '  "race": "the race label exactly as given, e.g. \\"Thirsk 3:00\\" (or \\"\\" if '
    'passing)",\n'
    '  "horse": "the chosen horse exactly as named in that readout (or \\"\\")",\n'
    '  "case": "the jigsaw, dots joined — why THIS horse in THIS race, citing facts",\n'
    '  "race_readable_because": "why this race passed the #31 checklist",\n'
    '  "crossed_off": ["horse — the fatal fact", "..."],\n'
    '  "cite": ["the exact readout/tool facts the case rests on"],\n'
    '  "owed": "what could not be checked (state it, never fill it)",\n'
    '  "profile_match": {"well_in": true, "class_ok": true, "market_anchor": true, '
    '"note": "how the pick fits the winning profile, or the STRONGER facts justifying '
    'a departure"},\n'
    '  "confidence": "confident | lean",\n'
    '  "pass": false,\n'
    '  "pass_reason": "ONLY if pass=true: what kills EVERY candidate race, one by one"\n'
    '}'
)


@dataclass(frozen=True)
class MorningPick:
    race_label: str = ""
    horse: str = ""
    case: str = ""
    race_readable_because: str = ""
    crossed_off: tuple[str, ...] = field(default_factory=tuple)
    cite: tuple[str, ...] = field(default_factory=tuple)
    owed: str = ""
    profile_note: str = ""
    profile_flags: tuple[bool, bool, bool] = (False, False, False)   # well_in, class, anchor
    confidence: str = ""
    is_pass: bool = False
    pass_reason: str = ""
    raw: str = ""

    @property
    def ok(self) -> bool:
        # a pick without the profile checklist stated is NOT ok — the model must say,
        # per pick, how it fits the winning profile (or justify the departure)
        pick_ok = bool(self.horse and self.race_label and self.profile_note)
        return pick_ok or (self.is_pass and bool(self.pass_reason))


def build_nap_prompt(candidates: list[tuple[str, str]], lessons: str = "") -> str:
    """candidates: (label, pre-race readout) per shortlisted race. `lessons` is the
    student's own notes — validated nuances + tracked horses — injected so the pick
    is made WITH the banked learning, not from a blank slate every morning."""
    blocks = [f"CANDIDATE RACE — {label}\n{readout}" for label, readout in candidates]
    lessons_block = (f"LESSONS BANKED (the master validated these — apply and cite "
                     f"them):\n{lessons}\n\n" if lessons.strip() else "")
    return (
        f"{lessons_block}"
        f"Today's shortlisted races ({len(candidates)}). Read them ALL, pick the most "
        f"readable one, then the best horse in it by elimination — or earn a pass.\n\n"
        + "\n\n----------------------------------------\n\n".join(blocks)
        + f"\n\nAnswer in this exact JSON shape:\n{_SCHEMA_HINT}"
    )


def parse_morning_pick(text: str) -> MorningPick:
    if not text:
        return MorningPick(raw="")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return MorningPick(raw=text)
    try:
        d = json.loads(m.group())
    except (ValueError, TypeError):
        return MorningPick(raw=text)

    def _tup(v) -> tuple[str, ...]:
        return tuple(str(x) for x in v) if isinstance(v, list) else ()

    pm = d.get("profile_match") if isinstance(d.get("profile_match"), dict) else {}
    return MorningPick(
        race_label=str(d.get("race", "")).strip(),
        horse=str(d.get("horse", "")).strip(),
        case=str(d.get("case", "")),
        race_readable_because=str(d.get("race_readable_because", "")),
        crossed_off=_tup(d.get("crossed_off")),
        cite=_tup(d.get("cite")),
        owed=str(d.get("owed", "")),
        profile_note=str(pm.get("note", "")),
        profile_flags=(bool(pm.get("well_in")), bool(pm.get("class_ok")),
                       bool(pm.get("market_anchor"))),
        confidence=str(d.get("confidence", "")).lower().strip(),
        is_pass=bool(d.get("pass")),
        pass_reason=str(d.get("pass_reason", "")),
        raw=text,
    )
