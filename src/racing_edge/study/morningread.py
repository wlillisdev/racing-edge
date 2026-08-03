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
    "RULE ONE, ABOVE EVERYTHING (the master, 2026-07-26): THE BEST HORSE WINS THE "
    "RACE. FIND THE BEST HORSE. Everything numbered below is nothing but WAYS to "
    "find him — and ways to stop fooling yourself that you have. Number-crunching "
    "and stats alone will not find him; joining the dots of the whole jigsaw will. "
    "When any rule below and this one seem to pull apart, THIS one wins.\n"
    "1. RACE FIRST (#3/#31): pick the most READABLE race — decent class, exposed "
    "field, a market with an anchor. A strong horse in a dangerous race is a pass. "
    "BUT (the master, 2026-07-26): every race is unique — races arrive with their "
    "WARNING FLAGS printed, and a flag is a caution, not a blindfold. Read every "
    "horse in every candidate with a NEUTRAL eye first; a gem can hide in a flagged "
    "race. A pick from a flagged race carries a HIGHER burden: the case must answer "
    "every warning explicitly, and it is LEAN at best — but 'flagged' alone is "
    "never the reason to skip the reading.\n"
    "1b. THE MASTER'S GLANCE (taught 2026-08-03, after the Galway 5:00 nap lost — "
    "his words: 'bang average horse, hard to read form... I would never have "
    "looked at it. You have the basic toolkit to do an autopsy of a race but you "
    "are picking bad races that makes it even harder for a novice to excel'): "
    "the NAP comes only from a race a 30-year handicapper would actually STUDY. "
    "A field of wall-to-wall moderate, in-and-out handicappers is NEVER a nap "
    "candidate, however tidy its market shape — average animals run to no "
    "script. Big-festival plot handicaps (Galway week and their like, "
    "especially late on the card) are decided in the betting ring, not the form "
    "book — that autopsy proved it: the winner's only pre-race signal was a "
    "26->15 gamble. You are a NOVICE: excel on readable material — quality "
    "animals, honest exposed form, a race where reading decides — and when the "
    "candidate races are all the wrong type, the correct nap is a PASS naming "
    "that. Hard races stay as study, never as bets.\n"
    "1c. STACK THE CARDS (taught 2026-08-03 — the master: 'you need to stack "
    "the cards in your favour, build your confidence, focus on races where you "
    "can join the dots'). The RECORD's winning profile, 22 picks in: honest "
    "UK-style handicaps at straightforward tracks, decent class, exposed "
    "readable fields — 6 of 8 winners came from exactly there at SP 2.6-4.5, "
    "while picks at 11/2+ are 1 from 7. So: the PRICE TRIPWIRE — this does NOT "
    "overturn #12 (the price never disqualifies a form-proven case): when your "
    "chosen best horse stands at 11/2 or bigger, that price is the market's "
    "CHALLENGE — re-walk the corroboration checklist out loud in the case, and "
    "unless it survives at full strength the pick is a LEAN at best; a "
    "wrong-type race AND a big price together is a PASS. Confidence is built "
    "by winning winnable races — when in doubt between a marginal bet and a "
    "named pass, the pass is the professional play.\n"
    "2. FORM FIRST, ODDS LAST (#29): build the best horse from the jigsaw — the mark "
    "(well-in, and by how MUCH), HOW it ran (manner/comments), course/trip fit, yard "
    "intent — before weighing its price. The market confirms or warns; it never picks.\n"
    "3. ELIMINATE (#25): in your chosen race, cross off what can't win on FACTS, then "
    "beat the survivors against each other. Pick LAST.\n"
    "4. USE THE TOOLS: frank the key form (what did the beaten horses do since?), pull "
    "deeper history where a line is thin. Spend lookups on your top candidates — and "
    "ALWAYS pull history (horse_runs) for any all-OWED runner in the top half of the "
    "market before crossing it: an OWED horse is a QUESTION, not an answer (the "
    "all-OWED 10/1 winner we dismissed unread, 2026-07-25).\n"
    "5. LOOK HARDER before passing — but a pass is CORRECT when no candidate matches "
    "the profile in rule 6. Across a full card there is usually one readable winner: "
    "dig for it, frank it, chase the threads. If after real work nothing matches, PASS "
    "and earn it — name what kills EACH candidate race. Never force the least-bad pick "
    "on a bad card: that is how both losing naps happened.\n"
    "6. THE WHOLE JIGSAW (rewritten 2026-07-26 — the master: 'the well-in claim is "
    "skewing all your picks; it is ONE piece'): the winning profile is the FULL "
    "jigsaw — current form, the manner read, course/trip fit, yard intent, a readable "
    "race — with the mark as ONE piece and a VETO only: never back a horse wrong at "
    "the weights, but a well-in figure is NEVER a case by itself and A BIGGER GAP IS "
    "NOT A BETTER HORSE (mark erosion flatters exposed losers — Woodstock, 07-25: "
    "'-7lb well-in' placed as its profile said it would). A well-in claim must pass the "
    "CORROBORATION CHECKLIST before it counts as a dot at all: (a) GRADE — was the "
    "mark earned at today's level? well-in from a Cl6 win means little in a Cl4; "
    "(b) FORM — is the horse AND its stable in current form? well-in plus cold form "
    "is erosion, not treatment; (c) FIT — does today's trip and track suit? a mark "
    "earned at the wrong distance transfers poorly; (d) THE MARKET CROSS-CHECK — if "
    "a horse is well-in at a BIG price with nothing else in its favour, the bookies "
    "have seen the same figure and do not fear it: they usually know why. This does "
    "NOT overturn #12 — the price never disqualifies a FORM-PROVEN case — but a "
    "mark-ONLY case at big odds is the market telling you the figure is hollow. "
    "Class 4+ preferred; Class 5 demands a STRONGER multi-fact case; Class 6 flat is "
    "a pass. THE PRICE NEVER DISQUALIFIES a form-proven case (#12) — in EITHER "
    "direction (the master, 2026-07-26: 'if there is a great case for an evens or "
    "odds-on horse we should not rule it out'): a big price on a real case is "
    "EACH-WAY VALUE (#28), and a short price on a GREAT case is still a bet — the "
    "price sets the stake and the expectation, never the eligibility. What a short "
    "price does demand is a case strong enough to be worth taking short odds about: "
    "the market already agrees, so the case must show WHY it is right and the risk "
    "small.\n"
    "7. LESSONS AND LEADS: MASTER-VALIDATED lines are real evidence — apply and cite "
    "them. Lines marked 'unverified lead' are COLOUR ONLY: they may tip a close call "
    "but a case may NEVER rest on one — the form facts must stand alone without the "
    "lead. (2026-07-21: two losing cases were built on unverified leads mislabelled "
    "as validated. Never again.)\n"
    "8. BEAT THE DANGER (2026-07-09, after the nap lost to an in-form rival who won "
    "easily): a case is NOT finished until you name the single most feared rival — "
    "usually the in-form one, the horse winning its recent races — state honestly why "
    "IT can win, and then beat it with cited facts. If you cannot beat the danger "
    "honestly, then the danger IS the pick, or the race is a pass. Never bank a case "
    "that only argues FOR your horse.\n"
    "9. THE REMATCH READ — A LEAD, NOT A LAW (demoted 2026-07-26: it rests on ONE "
    "race, Ebony Maw at 12.0, and by the master's standard one race is a sighting, "
    "not a pattern — weigh it like an unproven nuance): when today's race is a "
    "REMATCH of a recent race "
    "on the same terms, the previous running IS the trial run. The horse that won the "
    "rematch off today's mark, with course form, is the angle EVEN AT A BIG PRICE "
    "(each-way, #28). A favourite already BEATEN on today's terms by re-opposers is a "
    "FALSE anchor — oppose it, and its falseness makes the race MORE readable, not "
    "less. Recommend the instrument in the case: win single in the fair band, "
    "each-way only when the PLACE TERMS pay — roughly 5.0+ in 12+ runner "
    "handicaps (1/4 odds), 6.0+ in 8-11 fields (1/5 odds), never by a price cliff.\n"
    "IRON RULES: THE RULEBOOK IS CLOSED (the master, 2026-08-01: 'the biggest "
    "problem is the system not following its rules and creating rules to fill in "
    "gaps — wrong ones'): reason ONLY from the rules above, the MASTER-VALIDATED "
    "and FIELD-TESTED lessons, and the evidence in front of you. If a situation "
    "is not covered by a rule, SAY SO in the case and weigh the plain ledger of "
    "pros and cons — NEVER coin a new principle, threshold, or pattern mid-read. "
    "A rule is born in only three ways: the master teaches it, the master "
    "validates it, or the record field-tests it. Only facts from the readouts "
    "and tool results; cite the exact fact "
    "for every claim; a blank is OWED, never filled; never let the price pick. OWED "
    "IS SYMMETRIC (2026-07-25): a blank on a RIVAL is owed exactly as a blank on your "
    "pick — absence of evidence never counts AGAINST the danger; beat it only with "
    "facts you HAVE. And any fatal fact you use to cross off a rival that also "
    "applies to your own pick must be confronted in the case, never parked in owed.\n"
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
    '  "danger": {"horse": "the most feared rival (usually the in-form one)", '
    '"its_case": "why IT can win — honest", "beaten_because": "the cited facts that '
    'beat it"},\n'
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
    danger_horse: str = ""
    danger_case: str = ""
    danger_beaten: str = ""
    profile_note: str = ""
    profile_flags: tuple[bool, bool, bool] = (False, False, False)   # well_in, class, anchor
    confidence: str = ""
    is_pass: bool = False
    pass_reason: str = ""
    raw: str = ""

    @property
    def ok(self) -> bool:
        # a pick is NOT ok without (a) the profile checklist and (b) the DANGER named
        # and beaten — a case that only argues FOR its horse is half a case
        pick_ok = bool(self.horse and self.race_label and self.profile_note
                       and self.danger_horse and self.danger_beaten)
        return pick_ok or (self.is_pass and bool(self.pass_reason))


def build_lessons(nap_history: list[dict], strike: tuple[int, int],
                  nuances: list[dict], tracked_today: list[dict],
                  rule_tally: list[dict]) -> list[str]:
    """The student's notes for the exam, assembled PURE so a test can prove the loop
    is closed: the record and the last losses (with their night-autopsy verdicts),
    the master-validated lessons, the freshest unproven ones (weigh lightly), today's
    tracked leads (honestly labelled unverified), and rules dying on the scoreboard.

    This is the wire the coroner found cut (2026-07-21): huge credits went on night
    study whose output never reached the morning pick — validated=0 by construction,
    losses taught nothing forward. Everything the loop banks now flows through here.

    `nap_history` rows: date/horse/course/race_id/won. `tracked_today` rows:
    angle/horse/course/off_time/note (the tracked horses running TODAY)."""
    lines: list[str] = []
    w, n = strike
    if n:
        lines.append(f"- RECORD: {w}/{n} settled — "
                     + ("COLD: tighten race selection, demand the full profile"
                        if w * 2 < n else "steady"))
    nu_by_race: dict[str, dict] = {}
    for nu in nuances:
        nu_by_race.setdefault(nu["race_id"], nu)
    for x in [x for x in nap_history if x["won"] == 0][-5:]:
        aut = nu_by_race.get(x["race_id"])
        missed = (aut.get("what_missed") or "")[:140] if aut else ""
        lines.append(f"- RECENT LOSS {x['date']} {x['horse']} ({x['course']})"
                     + (f": missed — {missed}" if missed else ""))
    lines += [f"- MASTER-VALIDATED: {nu['nuance']}"
              for nu in nuances if nu["status"] == "validated"]
    # record-earned tier (2026-07-25): themes whose settled clues proved out
    lines += [f"- FIELD-TESTED by results: {nu['nuance'][:140]}"
              for nu in nuances if nu["status"] == "field-tested"][:4]
    # UNPROVEN proposals NO LONGER RIDE to the morning pick (the master,
    # 2026-08-01: 'the biggest problem is creating rules to fill in gaps that
    # are wrong' — the machine's own untested theories were whispering in the
    # picker's ear before he or the record ever ruled). The three roads a rule
    # can still take to this prompt: the master TEACHES it (NAP_SYSTEM), the
    # master VALIDATES it (doorbell), or the record FIELD-TESTS it (clues).
    # Proposals keep flowing to the doorbell and the night clue-trial unchanged.
    # REVERT-IF: 4+ weeks with zero promotions arriving by either road — then
    # the pipeline, not this gate, is what needs fixing.
    # tracked clues are UNVERIFIED leads (2026-07-21: two losers were built on tracked
    # clues the old header mislabelled 'master validated' — the model believed the
    # label). Honest label + explicit weight instruction. The clue's DATE prints too
    # (2026-07-25 audit: notes narrate the PAST race that taught them — 'won today',
    # 'finished 2nd' — and without the date they read as today's results), and a
    # CONFLICT note when the lead points against the engine's own read.
    tracked_lines = [
        f"- unverified lead ({t['angle']}, banked {t.get('date', '?')} — the note "
        f"describes THAT day's run, not today): {t['horse']} runs today "
        f"{t['course']} {t['off_time']}: {t['note'][:120]}"
        + (f" (NB: {t['conflict']})" if t.get("conflict") else "")
        for t in tracked_today[:8]]
    if tracked_lines:
        lines.append("UNVERIFIED TRACKED LEADS — colour only, weigh lightly, "
                     "NEVER the foundation of a case:")
        lines += tracked_lines
    # significance-gated (ROI audit: contradicts>=3 flagged ~2-3 innocent rules at
    # any moment across 22 on trial — 2-sigma on a fair coin, and n>=10, or silence)
    for t in rule_tally:
        n = t["contradicts"] + t["supports"]
        if n >= 10 and (t["contradicts"] - t["supports"]) >= 2 * (n ** 0.5):
            lines.append(f"- RULE UNDER FIRE: {t['rule']} contradicted "
                         f"{t['contradicts']}-{t['supports']} over {n} races — "
                         f"weigh it lightly")
        elif n >= 10 and (t["supports"] - t["contradicts"]) >= 2 * (n ** 0.5):
            lines.append(f"- RULE EARNING: {t['rule']} supported "
                         f"{t['supports']}-{t['contradicts']} over {n} races")
    return lines


def build_nap_prompt(candidates: list[tuple[str, str]], lessons: str = "") -> str:
    """candidates: (label, pre-race readout) per shortlisted race. `lessons` is the
    student's own notes — validated nuances + tracked horses — injected so the pick
    is made WITH the banked learning, not from a blank slate every morning."""
    blocks = [f"CANDIDATE RACE — {label}\n{readout}" for label, readout in candidates]
    lessons_block = (f"LESSONS & LEADS (labels matter — see rule 7):\n{lessons}\n\n"
                     if lessons.strip() else "")
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
    dg = d.get("danger") if isinstance(d.get("danger"), dict) else {}
    return MorningPick(
        race_label=str(d.get("race", "")).strip(),
        horse=str(d.get("horse", "")).strip(),
        case=str(d.get("case", "")),
        race_readable_because=str(d.get("race_readable_because", "")),
        crossed_off=_tup(d.get("crossed_off")),
        cite=_tup(d.get("cite")),
        owed=str(d.get("owed", "")),
        danger_horse=str(dg.get("horse", "")).strip(),
        danger_case=str(dg.get("its_case", "")),
        danger_beaten=str(dg.get("beaten_because", "")),
        profile_note=str(pm.get("note", "")),
        profile_flags=(bool(pm.get("well_in")), bool(pm.get("class_ok")),
                       bool(pm.get("market_anchor"))),
        confidence=str(d.get("confidence", "")).lower().strip(),
        is_pass=bool(d.get("pass")),
        pass_reason=str(d.get("pass_reason", "")),
        raw=text,
    )
