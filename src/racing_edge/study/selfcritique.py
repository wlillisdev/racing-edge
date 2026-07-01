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
    "IRON RULES:\n"
    "1. Reason ONLY over the facts in the readout. NEVER introduce a fact not present "
    "(no result you 'remember', no price, no comment that isn't printed). If something "
    "is marked OWED or blank, it is UNKNOWN — say so; do not fill it.\n"
    "2. Read FORM FIRST, price/result last: ask what pointed to the winner in the form "
    "BEFORE the result gave it away.\n"
    "3. Every claim must cite the exact fact from the readout it rests on.\n"
    "4. A nuance is a PROPOSAL to be tested, not a law. State what is OWED to confirm it "
    "and how confident you are.\n"
    "Answer ONLY with a single JSON object, no prose around it."
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
    '  "confidence": "low | medium | high"\n'
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


def build_prompt(readout: str, winner: str, blind_pick: str | None = None) -> str:
    """The self-prompt: the real readout + the master's questions + the output shape."""
    pick_line = (
        f"You picked **{blind_pick}** for this race, banked BLIND before the off.\n"
        if blind_pick else
        "You did not bank a pick in this race — study the winner cold.\n"
    )
    return (
        f"{pick_line}"
        f"The winner was **{winner}**.\n\n"
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
    return Critique(
        why_i_picked=str(d.get("why_i_picked", "")),
        what_i_missed=str(d.get("what_i_missed", "")),
        nuance=str(d.get("nuance", "")),
        cite=cites,
        owed=str(d.get("owed", "")),
        confidence=str(d.get("confidence", "")).lower().strip(),
        raw=text,
    )


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
    lines.append(f"    confidence:     {c.confidence or '?'}  "
                 f"(a proposal — the record and the master decide, not the model)")
    return "\n".join(lines)
