"""A Signal — one named, signed, reasoned read.

The audits' core verdict on selection: NO black-box score. Each handicapping
read returns a Signal the owner can see and overrule. `weight` exists only to
rank a busy card; the `reason` is the point. `veto` is a hard "leave it" (an
exposed non-winner) that the selection layer may forgive given a let-off.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    name: str            # short tag, e.g. "well_in_proven"
    weight: float        # signed contribution for ranking (transparency is the real point)
    reason: str          # the plain-English line the owner reads
    veto: bool = False   # a hard leave-it, unless a let-off (e.g. class drop) overrides it
