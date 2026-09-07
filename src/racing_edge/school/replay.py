"""THE BACKWARD REPLAY — read a past day the way the morning would have read it.

The master, 2026-09-07: "there has to be a better way of making the final
call... learn and improve." Three tie-breaks were invented from good weeks in
a fortnight and all three were wrong. The counting study of the same night
(docs/FINAL_CALL_2026-09-07.md) ranked every tie-break the CORPUS can see and
found none that beats the market — while naming the one lens it could not
see: MANNER OF RUNNING, which the six-week synthesis says has been winning
consistently. The comments live behind the results door, and this module is
how we get at them: rebuild a past race as a RACECARD, push it through the
real engine, and score what each candidate final call would have done.

MEASUREMENT ONLY. Nothing here picks, banks, emails or changes a rule. It
imports no model. The plan it follows is docs/plans/backward_replay.md.

Design rule (plan §2): build a RACECARD-SHAPED dict and hand it to the
existing normaliser. ONE home for normalisation — this module never builds a
Race or a Runner itself.

THE LOOK-AHEAD LINE, drawn once and named: a result document holds the
answer sheet as well as the card. Everything post-race — position, beaten
lengths, time, prize, the RPR/TS/performance/speed figures and the run
COMMENT — is stripped by `card_from_result` and returned separately by
`outcome_from_result`, which the scorer reads and the engine never sees.
The single exception is the price: no morning price exists in a result, so
the SP stands in for it, confined to the odds slot and declared in every
report. It is identical for every candidate rule, so a head-to-head stays
clean while the absolute strike is inflated against a live morning.
"""
from __future__ import annotations

from typing import Any

from racing_edge.data.normalise import _dist_f, _str

# post-race keys that must never reach a Runner (the test asserts it)
_POST_RACE = ("position", "sp", "btn", "ovr_btn", "time", "prize", "comment",
              "rpr", "tsr", "performance_rating", "speed_rating")


def card_from_result(doc: dict) -> dict:
    """One /results race document -> the RACECARD-shaped raw dict
    `race_from_raw` expects. Pre-race fields only.

    The mark a horse RAN OFF (`or`) is legitimately pre-race and is kept: it
    is the mark the handicapper had set before the race was run. Everything
    in _POST_RACE is dropped. `last_run` is left absent for the caller to
    fill from the history cache (days-since-run cannot be read off a result).
    """
    runners = []
    for r in doc.get("runners") or []:
        sp = r.get("sp_dec")
        out: dict[str, Any] = {
            "horse_id": _str(r.get("horse_id")),
            "horse": _str(r.get("horse")),
            "trainer": _str(r.get("trainer")),
            "trainer_id": _str(r.get("trainer_id")),
            "jockey": _str(r.get("jockey")),
            "jockey_id": _str(r.get("jockey_id")),
            "claim": r.get("jockey_claim_lbs"),
            "age": r.get("age"),
            "sex": _str(r.get("sex")),
            "lbs": r.get("weight_lbs"),
            "ofr": r.get("or"),
            "draw": r.get("draw"),
            "headgear": _str(r.get("headgear")),
            "sire": _str(r.get("sire")), "sire_id": _str(r.get("sire_id")),
            "dam": _str(r.get("dam")), "dam_id": _str(r.get("dam_id")),
            "damsire": _str(r.get("damsire")), "damsire_id": _str(r.get("damsire_id")),
            "owner": _str(r.get("owner")), "owner_id": _str(r.get("owner_id")),
        }
        # unpriced runners exist (no SP recorded) — they drop out of the field
        # exactly as a live unpriced runner does, never priced at a guess
        if sp not in (None, "", 0, "0"):
            out["odds"] = [{"decimal": sp}]
        runners.append(out)
    return {
        "race_id": _str(doc.get("race_id")),
        "date": _str(doc.get("date")),
        "course": _str(doc.get("course")),          # keeps " (AW)" — the AW gate reads it
        "off_time": _str(doc.get("off")),
        "race_name": _str(doc.get("race_name")),
        "type": _str(doc.get("type")),
        "class": _str(doc.get("class")),            # "Class 6" — _class digs the digit out
        "pattern": _str(doc.get("pattern")),
        "distance_f": _dist_f(doc),                 # "12f" -> 12.0, else yards/220
        "going": _str(doc.get("going")),
        "region": _str(doc.get("region")),
        "surface": _str(doc.get("surface")),
        "runners": runners,
    }


def outcome_from_result(doc: dict) -> dict:
    """The answer sheet, kept OUT of the card: {horse_id: {...}}.

    `comment` is the running comment for THIS race. It is the manner of
    running the reader would only ever see AFTERWARDS, so it belongs here,
    never on the card. A horse's manner going INTO a race comes from its own
    earlier runs, which the history door serves and `as_of` bounds.
    """
    out = {}
    for r in doc.get("runners") or []:
        hid = _str(r.get("horse_id"))
        if not hid:
            continue
        pos = _str(r.get("position"))
        out[hid] = {
            "position": int(pos) if pos.isdigit() else None,
            "status": "" if pos.isdigit() else pos.upper(),
            "sp_dec": r.get("sp_dec"),
            "btn": r.get("ovr_btn") or r.get("btn"),
            "comment": _str(r.get("comment")),
            "horse": _str(r.get("horse")),
        }
    return out


def winner_of(outcome: dict) -> str:
    """The winning horse_id, or '' when the document names no first."""
    for hid, o in outcome.items():
        if o["position"] == 1:
            return hid
    return ""
