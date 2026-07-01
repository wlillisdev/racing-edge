"""Tests for the self-teaching loop — prompt grounding, parsing, and the nuance store."""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

from racing_edge.study.nuances import NuanceLog
from racing_edge.study.selfcritique import (
    SYSTEM,
    build_prompt,
    parse_critique,
    render_critique,
)


def test_system_prompt_forbids_inventing_facts() -> None:
    # the guardrail that rebuilds trust must be explicit in the system prompt
    assert "NEVER introduce a fact not present" in SYSTEM
    assert "OWED" in SYSTEM and "PROPOSAL" in SYSTEM


def test_build_prompt_carries_the_readout_and_the_blind_pick() -> None:
    p = build_prompt("READOUT-BODY", winner="Timber Twelve", blind_pick="Alma Latina")
    assert "READOUT-BODY" in p
    assert "Timber Twelve" in p and "Alma Latina" in p
    # cold study when no pick was banked
    assert "study the winner cold" in build_prompt("R", "W", None)


def test_parse_critique_extracts_json_even_with_prose_around_it() -> None:
    reply = (
        'Here is my honest self-study:\n'
        '{"why_i_picked": "market rank", "what_i_missed": "winner was well-in off 82, '
        'commented stayed on", "nuance": "trust the well-in horse that stayed on last time", '
        '"cite": ["mark WELL-IN", "comment stayed on strongly"], "owed": "the live move", '
        '"confidence": "Medium"}\n'
        'That is the lesson.'
    )
    c = parse_critique(reply)
    assert c.ok
    assert c.nuance.startswith("trust the well-in")
    assert c.confidence == "medium"                 # normalised
    assert len(c.cite) == 2
    assert "well-in" in render_critique(c, "Epsom 18:57", "Timber Twelve").lower()


def test_record_fields_feed_the_nuance_ledger_signature() -> None:
    """The Critique->store mapping must match NuanceLog.record's kwargs exactly — this
    is the guard for the what_missed/what_i_missed field-name drift that crashed the box."""
    from datetime import date

    c = parse_critique('{"what_i_missed": "well-in, stayed on", "nuance": "trust it", '
                       '"cite": ["a", "b"], "owed": "the move", "confidence": "high"}')
    fields = c.record_fields()
    assert fields["what_missed"] == "well-in, stayed on"     # mapped, not what_i_missed
    assert fields["cite"] == "a | b"
    with tempfile.TemporaryDirectory() as d:
        log = NuanceLog(Path(d) / "n.db")
        # the real call shape from cli.learn — must not raise on unknown/missing kwargs
        log.record(day=date(2026, 7, 1), race_id="r", course="Epsom", winner="W",
                   blind_pick="", **fields)
        assert log.all()[0]["what_missed"] == "well-in, stayed on"
        log.close()


def test_parse_critique_survives_a_non_json_reply() -> None:
    c = parse_critique("the model rambled with no json")
    assert not c.ok
    assert c.raw == "the model rambled with no json"
    assert "no reasoning available" in render_critique(c, "x", "y")


def test_nuance_log_banks_proposed_and_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as d:
        log = NuanceLog(Path(d) / "nuances.db")
        for _ in range(2):        # same nuance twice -> one row (idempotent)
            log.record(day=date(2026, 7, 1), race_id="r1", course="Epsom",
                       winner="Timber Twelve", blind_pick="Alma Latina",
                       nuance="oppose the smashed short fav in a deep field",
                       what_missed="winner was backed 44->29", cite="move BACKED",
                       owed="live move", confidence="medium")
        rows = log.proposed()
        assert len(rows) == 1
        assert rows[0]["status"] == "proposed"
        log.set_status(rows[0]["id"], "validated")
        assert log.proposed() == []                 # no longer proposed
        assert log.all()[0]["status"] == "validated"
        log.close()


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
