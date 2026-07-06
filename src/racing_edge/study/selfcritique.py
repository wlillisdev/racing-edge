"""The SELF-INTERROGATION — the AI asks itself what the master asks it (#27/#29).

The master's teaching move is a question: *"why did you pick that horse? the winner was
there in the form — why did you miss it? what's the nuance?"* This turns that into a
self-prompt the model answers over the REAL result readout (report.restudy) — form-first,
grounded, and honest about what it can't see.

Two guardrails against the failure that broke trust (inventing a fact, enshrining a
guess):
  1. GROUNDED — the system prompt forbids any fact not in the readout; a blank is OWED,
     never filled. The model reasons over the facts; it is never the source of them.
  2. PROPOSAL — every nuance is a candidate, tagged with the facts it rests on, what's
     OWED to confirm it, and a confidence. It becomes a tell/rule only when the trial
     record or the master validates it — the model does not get to write the notebook.

Pure: text in, a prompt out / a parsed critique out. The model call lives in ai.reason.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

SYSTEM = (
    "You are an apprentice handicapper marking your OWN read against a result, the way a "
    "30-year master interrogates you. You are given a full-form readout of ONE finished "
    "race — the mark (well-in vs raised), form figures, official rating, spotlight, and "
    "each horse's last runs with their in-running comments — plus the result.\n\n"
    "QUESTION ZERO — RACE SELECTION (#3), before any horse question: was this race "
    "READABLE — decent class/grade, an exposed field with real form lines, a market "
    "with an anchor? If it was a bottom-grade scramble, an unexposed field, or an "
    "anything-could-win open market, then the right answer was PASS and any pick in it "
    "was a race-selection error regardless of which horse won. Say so explicitly in "
    "system_verdict and score rule #3 in rule_evidence.\n\n"
    "IRON RULES:\n"
    "1. Reason ONLY over the facts in the readout. NEVER introduce a fact not present "
    "(no result you 'remember', no price, no comment that isn't printed). If something "
    "is marked OWED or blank, it is UNKNOWN — say so; do not fill it.\n"
    "2. Read FORM FIRST, price/result last: ask what pointed to the winner in the form "
    "BEFORE the result gave it away.\n"
    "3. Every claim must cite the exact fact from the readout it rests on.\n"
    "4. A nuance is a PROPOSAL to be tested, not a law. State what is OWED to confirm it "
    "and how confident you are.\n"
    "5. DISSECT EVERY HORSE, not just the winner (#27) — the running line is a read for "
    "NEXT time. Mine the beaten horses for forward clues: an EXCUSE (hampered, short of "
    "room, wrong pace/trip/ground) = one to FOLLOW next start; an eye-catcher finishing "
    "powerfully = follow (unless the market has already eaten it); an exposed one "
    "flattered by the run, or repeatedly finding little = one to OPPOSE at short prices. "
    "Read the race SHAPE too (#20): if the comments show the race was run to suit "
    "(soft lead, prominent-dominated), say who was flattered and who ran better than "
    "the bare result.\n"
    "6. TEST THE NOTEBOOK: also report which numbered rules this race supported or "
    "contradicted, citing the fact. The rule index:\n"
    "   #1 read the finish/manner, not the figures; #2 2nd/3rd-fav sweet spot; "
    "#14 all-weather caution; #15 franking is a tiebreaker; #17/#18 read the smart "
    "money/gamble; #19 don't fear a fair-priced fav; #20 pace shapes the race; "
    "#22 mark vs price gap; #24/#25 evaluate all, eliminate first; #26 facts not "
    "assumptions; #29 form first, odds last.\n"
    "If a SYSTEM PRE-RACE READ is supplied, mark it like a teacher: did the rules find "
    "the winner, and if not, WHICH lens failed or was missing?\n"
    "If lookup TOOLS are available, INVESTIGATE like a detective before answering: pull "
    "the threads the readout can't show — FRANK the form (#5/#15: fetch a key past race "
    "via its [race ...] id and check what the horses it beat/lost to did since, via "
    "their ids), or fetch deeper history on a puzzle horse. Evidence from lookups is "
    "admissible and citable; spend lookups on the winner's story first. When done "
    "(or the budget is spent), answer ONLY with the single JSON object, no prose."
)

_SCHEMA_HINT = (
    '{\n'
    '  "why_i_picked": "if a blind pick is given: the honest reason it was picked, or '
    '\\"n/a\\"",\n'
    '  "what_i_missed": "what in the WINNER\'s full form pointed to it that a form-first '
    'read should have caught (cite the facts)",\n'
    '  "nuance": "one transferable sentence — the pattern to watch next time",\n'
    '  "cite": ["the exact readout facts this rests on"],\n'
    '  "owed": "what was blank/OWED that would confirm or kill this",\n'
    '  "confidence": "low | medium | high",\n'
    '  "system_verdict": "if a system read was supplied: did the rules find the winner, '
    'and which lens failed/was missing (or \\"n/a\\")",\n'
    '  "rule_evidence": [{"rule": "#22", "verdict": "supports|contradicts", '
    '"note": "the fact"}],\n'
    '  "to_follow": [{"horse": "name exactly as in the readout", '
    '"angle": "follow|oppose", "note": "the clue, citing the comment", '
    '"conditions": "when it applies (trip up / better ground / fair price...)"}]\n'
    '}'
)


@dataclass(frozen=True)
class Critique:
    why_i_picked: str = ""
    what_i_missed: str = ""
    nuance: str = ""
    cite: tuple[str, ...] = field(default_factory=tuple)
    owed: str = ""
    confidence: str = ""
    system_verdict: str = ""                                  # marking the rules' own read
    rule_evidence: tuple[tuple[str, str, str], ...] = ()      # (rule, verdict, note)
    to_follow: tuple[tuple[str, str, str, str], ...] = ()     # (horse, angle, note, conditions)
    raw: str = ""            # the model's raw text, kept if parsing fails

    @property
    def ok(self) -> bool:
        return bool(self.nuance or self.what_i_missed)

    def record_fields(self) -> dict[str, str]:
        """The subset the nuance ledger stores — one source of truth for the field
        names, so a caller can't drift (e.g. what_missed vs what_i_missed)."""
        return {
            "nuance": self.nuance,
            "what_missed": self.what_i_missed,
            "cite": " | ".join(self.cite),
            "owed": self.owed,
            "confidence": self.confidence,
        }


def build_prompt(readout: str, winner: str, blind_pick: str | None = None,
                 system_read: str = "", blind_case: str = "") -> str:
    """The self-prompt: the real readout + the master's questions + the output shape.
    `system_read` is what the RULES said pre-race; `blind_case` is the pick's OWN
    banked reasoning — so the critique marks the real case, not a guess at it (the
    audit: 'a self-critique of an invented memory')."""
    pick_line = (
        f"You picked **{blind_pick}** for this race, banked BLIND before the off"
        + (f", BECAUSE:\n{blind_case}\n" if blind_case else ".\n")
        if blind_pick else
        "You did not bank a pick in this race — study the winner cold.\n"
    )
    sys_block = (
        f"\nSYSTEM PRE-RACE READ (what the rules said BEFORE the off — mark it like a "
        f"teacher):\n{system_read}\n" if system_read else ""
    )
    return (
        f"{pick_line}"
        f"The winner was **{winner}**.\n"
        f"{sys_block}\n"
        f"FULL-FORM READOUT (the only facts you may use):\n"
        f"-----------------------------------------------\n{readout}\n"
        f"-----------------------------------------------\n\n"
        f"Interrogate yourself and answer in this exact JSON shape:\n{_SCHEMA_HINT}"
    )


def parse_critique(text: str) -> Critique:
    """Pull the JSON object out of the model's reply; keep the raw text on failure."""
    if not text:
        return Critique(raw="")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return Critique(raw=text)
    try:
        d = json.loads(m.group())
    except (ValueError, TypeError):
        return Critique(raw=text)
    cite = d.get("cite")
    cites = tuple(str(c) for c in cite) if isinstance(cite, list) else \
        ((str(cite),) if cite else ())
    rev = d.get("rule_evidence")
    rules = tuple(
        (str(e.get("rule", "")), str(e.get("verdict", "")).lower().strip(),
         str(e.get("note", "")))
        for e in rev if isinstance(e, dict)
    ) if isinstance(rev, list) else ()
    tf = d.get("to_follow")
    follows = tuple(
        (str(e.get("horse", "")), str(e.get("angle", "")).lower().strip(),
         str(e.get("note", "")), str(e.get("conditions", "")))
        for e in tf if isinstance(e, dict)
    ) if isinstance(tf, list) else ()
    return Critique(
        why_i_picked=str(d.get("why_i_picked", "")),
        what_i_missed=str(d.get("what_i_missed", "")),
        nuance=str(d.get("nuance", "")),
        cite=cites,
        owed=str(d.get("owed", "")),
        confidence=str(d.get("confidence", "")).lower().strip(),
        system_verdict=str(d.get("system_verdict", "")),
        rule_evidence=rules,
        to_follow=follows,
        raw=text,
    )


REFUTE_SYSTEM = (
    "You are the SCEPTIC — a second, adversarial pass over an apprentice handicapper's "
    "self-study. You get the SAME full-form readout and the nuance the apprentice "
    "proposes. Your one job: try to KILL the nuance using only the readout's facts.\n\n"
    "Attack it on exactly these grounds:\n"
    "1. FACT CHECK — does every claim it rests on actually appear in the readout, "
    "verbatim? (e.g. calling a horse WELL-IN when its own cited marks show it RAISED.)\n"
    "2. CONTRADICTION — does other readout evidence cut against it?\n"
    "3. ARTIFACT — is it built on a data gap (blank/OWED fields, missing coverage) "
    "rather than a racing fact?\n"
    "4. TRIVIALITY — is it just restating an obvious known rule with no new edge?\n"
    "Do NOT introduce outside facts. If the nuance survives all four, say so honestly — "
    "you are a sceptic, not a cynic.\n"
    'Answer ONLY a JSON object: {"refuted": true|false, "ground": "fact|contradiction|'
    'artifact|triviality|none", "reason": "one or two sentences citing the readout"}'
)


@dataclass(frozen=True)
class Refutation:
    refuted: bool = False
    ground: str = ""
    reason: str = ""
    raw: str = ""

    @property
    def answered(self) -> bool:
        return bool(self.reason or self.ground)


def build_refute_prompt(readout: str, critique: Critique) -> str:
    return (
        f"THE APPRENTICE'S NUANCE (attack this):\n{critique.nuance}\n\n"
        f"It claims to rest on: {' | '.join(critique.cite) or '(nothing cited)'}\n"
        f"What it says was missed: {critique.what_i_missed}\n\n"
        f"FULL-FORM READOUT (the only admissible evidence):\n"
        f"-----------------------------------------------\n{readout}\n"
        f"-----------------------------------------------\n\n"
        f"Try to kill it. JSON only."
    )


def parse_refutation(text: str) -> Refutation:
    if not text:
        return Refutation(raw="")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return Refutation(raw=text)
    try:
        d = json.loads(m.group())
    except (ValueError, TypeError):
        return Refutation(raw=text)
    return Refutation(refuted=bool(d.get("refuted")),
                      ground=str(d.get("ground", "")).lower().strip(),
                      reason=str(d.get("reason", "")), raw=text)


def render_critique(c: Critique, race_label: str, winner: str) -> str:
    """Human-readable rendering of the self-interrogation for the console/email."""
    if not c.ok:
        return (f"  SELF-STUDY {race_label}: no reasoning available "
                f"(model off, or empty reply).\n  raw: {c.raw[:200]}")
    lines = [
        f"  SELF-STUDY {race_label} — winner {winner}",
        f"    why I picked:   {c.why_i_picked or 'n/a'}",
        f"    what I missed:  {c.what_i_missed}",
        f"    → NUANCE (proposed, to be tested): {c.nuance}",
    ]
    if c.cite:
        lines.append(f"    rests on:       {' | '.join(c.cite)}")
    if c.owed:
        lines.append(f"    OWED to confirm: {c.owed}")
    if c.system_verdict and c.system_verdict.lower() != "n/a":
        lines.append(f"    marking the RULES' read: {c.system_verdict}")
    for rule, verdict, note in c.rule_evidence:
        sign = "✓" if verdict == "supports" else "✗"
        lines.append(f"    {sign} {rule} {verdict}: {note}")
    for horse, angle, note, conditions in c.to_follow:
        arrow = "→ FOLLOW" if angle == "follow" else "→ OPPOSE"
        cond = f"  [{conditions}]" if conditions else ""
        lines.append(f"    {arrow} {horse}: {note}{cond}")
    lines.append(f"    confidence:     {c.confidence or '?'}  "
                 f"(a proposal — the record and the master decide, not the model)")
    return "\n".join(lines)
