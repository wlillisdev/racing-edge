"""Read the race narrative — structured, source-cited, never a score.

The evidence-backed sweet spot for an LLM in this domain: turn the unstructured
comment / spotlight ("hampered 2 out, stayed on well when no chance, remains
ahead of the handicapper") into typed reads the human can verify. Every read
MUST quote the source text verbatim — reads whose citation isn't grounded in the
source are dropped (the strongest hallucination control there is). Output is
advisory only: shown beside the method's reasons, never fed into a score.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from racing_edge.domain.models import Runner

# A constrained vocabulary — the reads worth extracting for jumps handicapping.
ALLOWED_TAGS = frozenset({
    "ground_preference", "stays_well", "needs_further", "needs_shorter",
    "trouble_in_running", "finished_well", "weakened", "jumping",
    "target_race", "trainer_intent", "well_handicapped", "unlucky", "excuse",
    "first_time_out", "needed_run", "improving", "one_to_note",
})


@dataclass(frozen=True)
class NarrativeRead:
    tag: str         # from ALLOWED_TAGS
    note: str        # plain-English read
    citation: str    # the exact phrase from the source it is grounded in


def _source_text(runner: Runner) -> str:
    return (runner.spotlight or "").strip()


def parse_reads(items: object, source_text: str) -> list[NarrativeRead]:
    """Validate the model's output and ENFORCE grounding: keep only reads with a
    known tag, a note, and a citation that actually appears in the source text."""
    src = (source_text or "").lower()
    out: list[NarrativeRead] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        tag = str(it.get("tag", "")).strip().lower()
        note = str(it.get("note", "")).strip()
        cite = str(it.get("citation", "")).strip()
        if tag not in ALLOWED_TAGS or not note or not cite:
            continue
        if cite.lower() not in src:        # hallucination control: must be grounded
            continue
        out.append(NarrativeRead(tag=tag, note=note, citation=cite))
    return out


_PROMPT = """You are reading a single horse's pre-race comment/spotlight for an
experienced handicapper. Extract ONLY reads that are explicitly supported by the
text. For each, give:
  - "tag": one of {tags}
  - "note": a short plain-English read
  - "citation": the EXACT phrase from the text that supports it (verbatim)
Rules: do NOT predict, rate, rank, or recommend. Do NOT invent anything not in
the text. If nothing notable, return []. Output a JSON array only.

TEXT:
{text}"""


def read_narrative(runner: Runner, complete: Callable[[str], str] | None) -> list[NarrativeRead]:
    """Extract source-cited reads from the runner's narrative. Returns [] with no
    LLM configured, empty narrative, or any error — it never raises and never
    blocks a pick."""
    source = _source_text(runner)
    if not source or complete is None:
        return []
    try:
        raw = complete(_PROMPT.format(tags=sorted(ALLOWED_TAGS), text=source))
        return parse_reads(json.loads(raw), source)
    except Exception:
        return []
