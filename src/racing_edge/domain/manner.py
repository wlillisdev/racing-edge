"""Reading the FINISH, not the figures — notebook rule #1, in code.

A horse with every surface tick is still a placer, not a NAP, if its running
comments say it doesn't finish. This reads an in-running / closing comment and
classifies the MANNER: did it finish like a winner, get out-battled like a
nearly-type, or have an excuse (trouble in running)? Aggregated over a horse's
recent runs, a repeated non-finishing manner downgrades a NAP candidate to
place-only — the fix for "close but not winning".

Pure: text in, classification out. The phrase lists ARE the handicapper's
vocabulary; they grow as the eye sharpens (that's the learning loop).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Manner = Literal["finisher", "non_finisher", "trouble", "green", "neutral"]

# A winning/strong flourish — the horse saw it out.
_FINISHER = (
    "ran on well", "ran on strongly", "stayed on well", "stayed on strongly",
    "kept on well", "battled on", "battled back", "rallied", "found plenty",
    "found extra", "quickened", "drew clear", "drew away", "went clear",
    "readily", "comfortably", "easily", "willingly", "stayed on to win",
    "ran on to win", "ran out a ready winner", "always doing enough", "in command",
    # earned 2026-07-01 (Worcester 1:50 self-study): "asserted on the run-in" read as
    # NEUTRAL and the rules missed the winner — the vocabulary grows as the eye sharpens
    "asserted", "forged clear", "went on to win", "finished strongly",
)
# An excuse — the bare result lies, don't downgrade the manner.
_TROUBLE = (
    "hampered", "badly hampered", "short of room", "no room", "denied a clear run",
    "denied clear run", "checked", "squeezed", "lost his place", "carried wide",
    "slowly away", "missed the break", "blocked", "no clear run", "shuffled back",
    "fell", "unseated", "brought down", "pulled up", "ran out", "refused",
    "hung badly", "jumped slowly",
)
# The nearly-type tells — got its chance and found nothing.
_NON_FINISHER = (
    "no extra", "found little", "found nothing", "no impression", "one paced",
    "one-paced", "never nearer", "ran on never nearer", "kept on same pace",
    "out-battled", "outbattled", "outpaced", "weakened", "faded", "no response",
    "plugged on", "failed to quicken", "soon beaten", "well held", "every chance",
    "no further progress", "lacked a turn of foot", "stayed on past beaten horses",
    # led-and-caught (2026-07-25 Woodstock audit: 'driven to the front... overtaken
    # inside the final 110 yards' read NEUTRAL — the textbook nearly-type went unseen)
    "overtaken", "headed", "collared", "caught inside the final", "caught close home",
)
_GREEN = (
    "green", "ran green", "will improve", "needed the run", "should improve",
    "first run", "wandered", "raced keenly", "too free",
)


_FRONT = ("made all", "made most", "made the running", "made running", "soon led",
          "led for", "led until", "led early", "set the pace", "took the field",
          "jumped off in front", "pace-setter", "disputed the lead early")
_HELD_UP = ("held up", "in rear", "towards rear", "raced in last", "waited with",
            "at the back", "detached in last")


def run_style(recent_comments: list[str]) -> tuple[str, int, int]:
    """(style, front_runs, held_runs) from recent comments — 'front' | 'held up' |
    'mixed/unknown'. The silliest blind spot (the master, 2026-07-26): the morning
    read stamped 'run-style OWED' daily while HOLDING the comments that answer it —
    who leads is written in the running lines the machine already fetches."""
    fronts = sum(1 for c in recent_comments
                 if c and any(k in c.lower() for k in _FRONT))
    helds = sum(1 for c in recent_comments
                if c and any(k in c.lower() for k in _HELD_UP))
    read = sum(1 for c in recent_comments if c and c.strip())
    if read >= 2 and fronts >= 2 and fronts > helds:
        return "front", fronts, helds
    if read >= 2 and helds >= 2 and helds > fronts:
        return "held up", fronts, helds
    return "mixed/unknown", fronts, helds


def read_manner(comment: str) -> tuple[Manner, str]:
    """Classify one running comment. Priority: a winning flourish first (it finished),
    then an excuse, then the nearly-type tell, then green. Returns (manner, phrase)."""
    c = f" {comment.lower().strip()} "
    for manner, phrases in (("finisher", _FINISHER), ("trouble", _TROUBLE),
                            ("non_finisher", _NON_FINISHER), ("green", _GREEN)):
        for p in phrases:
            if p in c:
                return manner, p  # type: ignore[return-value]
    return "neutral", ""


@dataclass(frozen=True)
class MannerVerdict:
    recommendation: Literal["win_positive", "place_only", "excuse_upgrade", "neutral"]
    reason: str
    non_finisher_runs: int
    finisher_runs: int


def nap_verdict(recent_comments: list[str],
                positions: list[int | None] | None = None) -> MannerVerdict:
    """Read a horse's recent comments (MOST RECENT FIRST) and judge it as a NAP.
    Repeated out-battled/found-little = a placer, not a NAP (rule #1's 'again').

    `positions`, when given (aligned with recent_comments), guards the vocabulary:
    a comment from a run the horse WON can never read non-finisher (2026-07-25
    adversarial review: 'made most, headed over 1f out, kept on to lead again close
    home, won going away' classified non_finisher on the word 'headed' — a rallying
    front-running WINNER flagged as a placer)."""
    pairs = [(c, positions[i] if positions and i < len(positions) else None)
             for i, c in enumerate(recent_comments) if c and c.strip()]
    manners = []
    for c, pos in pairs:
        m = read_manner(c)[0]
        if m == "non_finisher" and pos == 1:
            m = "finisher"                     # it WON — the finish speaks for itself
        manners.append(m)
    if not manners:
        return MannerVerdict("neutral", "no running comments to read", 0, 0)
    nonf = manners.count("non_finisher")
    fin = manners.count("finisher")
    trouble = manners.count("trouble")
    recent = manners[0]

    if nonf >= 2 and nonf >= fin:
        return MannerVerdict(
            "place_only",
            f"out-battled / found little in {nonf} of the last {len(manners)} — "
            "a placer, not a NAP",
            nonf, fin)
    if recent == "finisher" or (fin >= 1 and fin > nonf):
        return MannerVerdict(
            "win_positive", f"finishes his races ({fin} strong finish(es) recently)", nonf, fin)
    if recent == "trouble" or (trouble and trouble >= nonf):
        return MannerVerdict(
            "excuse_upgrade", "met trouble in running — the bare form understates him", nonf, fin)
    return MannerVerdict("neutral", "manner unclear from the comments", nonf, fin)
