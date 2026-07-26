"""Course HANDEDNESS — which way the track turns (the master, 2026-07-26: 'how many
wins going left-handed or right-handed' is one of the finding-tools).

Horses genuinely prefer a direction — they jump one way, hang one way, balance one
way — and a horse whose wins all came one-handed is a question mark turning the
other way. Static public knowledge, but ONLY courses we are certain of are listed:
a wrong handedness silently poisoning reads is worse than an honest OWED. The map
grows as entries are verified; unknown courses return None and print as OWED.
"""

from __future__ import annotations

_LEFT = {
    "aintree", "ayr", "bangor-on-dee", "bangor", "bath", "brighton", "cartmel",
    "catterick", "chelmsford", "cheltenham", "chepstow", "chester", "doncaster",
    "epsom", "epsom downs", "ffos las", "fakenham", "haydock", "hexham", "kelso",
    "lingfield", "newbury", "newcastle", "newton abbot", "nottingham", "plumpton",
    "pontefract", "redcar", "sedgefield", "southwell", "stratford", "thirsk",
    "uttoxeter", "warwick", "wetherby", "wolverhampton", "worcester", "yarmouth",
    "york",
    # Ireland
    "leopardstown", "naas", "navan", "listowel",
}
_RIGHT = {
    "ascot", "beverley", "carlisle", "exeter", "goodwood", "hamilton",
    "huntingdon", "kempton", "leicester", "ludlow", "market rasen", "musselburgh",
    "perth", "ripon", "salisbury", "sandown", "taunton",
    # Ireland
    "curragh", "the curragh", "fairyhouse", "punchestown", "galway", "cork",
    "gowran park", "tramore",
}


def handedness(course: str) -> str | None:
    """'left' | 'right' | None (unknown/figure-eight — honest OWED, never guessed)."""
    c = (course or "").strip().lower()
    if c in _LEFT:
        return "left"
    if c in _RIGHT:
        return "right"
    return None
