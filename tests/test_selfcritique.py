"""Tests for the self-teaching loop — prompt grounding, parsing, and the nuance store."""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

from racing_edge.study.nuances import NuanceLog
from racing_edge.study.selfcritique import (
    REFUTE_SYSTEM,
    SYSTEM,
    build_prompt,
    build_refute_prompt,
    parse_critique,
    parse_refutation,
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


def test_each_task_gets_the_right_brain_never_haiku() -> None:
    """Per-task model selection — the master's ruling after Haiku wrecked the reads.
    The sceptic must be at least as sharp as the proposer; nothing defaults small."""
    import os

    from racing_edge.ai.reason import resolve_model
    for var in ("ANTHROPIC_MODEL", "ANTHROPIC_MODEL_STUDY", "ANTHROPIC_MODEL_SCEPTIC"):
        os.environ.pop(var, None)
    assert resolve_model("study") == "claude-sonnet-5"
    assert resolve_model("sceptic") == "claude-fable-5"
    assert resolve_model("synthesis") == "claude-fable-5"
    for task in ("study", "sceptic", "synthesis"):
        assert "haiku" not in resolve_model(task)
    # override order: per-task beats global beats table
    os.environ["ANTHROPIC_MODEL"] = "claude-fable-5"
    assert resolve_model("study") == "claude-fable-5"
    os.environ["ANTHROPIC_MODEL_STUDY"] = "claude-opus-4-8"
    assert resolve_model("study") == "claude-opus-4-8"
    assert resolve_model("sceptic") == "claude-fable-5"
    for var in ("ANTHROPIC_MODEL", "ANTHROPIC_MODEL_STUDY"):
        os.environ.pop(var, None)


def test_the_sceptic_is_adversarial_and_grounded() -> None:
    # the second pass must attack on the four grounds and stay inside the readout
    assert "KILL the nuance" in REFUTE_SYSTEM
    for ground in ("FACT CHECK", "CONTRADICTION", "ARTIFACT", "TRIVIALITY"):
        assert ground in REFUTE_SYSTEM
    c = parse_critique('{"nuance": "the claim", "cite": ["WELL-IN at 8.5"], '
                       '"what_i_missed": "x"}')
    p = build_refute_prompt("THE-READOUT", c)
    assert "the claim" in p and "WELL-IN at 8.5" in p and "THE-READOUT" in p


def test_parse_refutation_reads_the_verdict_and_survives_prose() -> None:
    r = parse_refutation('Verdict: {"refuted": true, "ground": "Fact", '
                         '"reason": "its own marks show +3lb, not well-in"}')
    assert r.refuted and r.ground == "fact" and "+3lb" in r.reason
    ok = parse_refutation('{"refuted": false, "ground": "none", "reason": "holds up"}')
    assert not ok.refuted and ok.answered
    bad = parse_refutation("no json at all")
    assert not bad.refuted and not bad.answered      # no verdict -> caller banks + flags


def test_parse_critique_survives_a_non_json_reply() -> None:
    c = parse_critique("the model rambled with no json")
    assert not c.ok
    assert c.raw == "the model rambled with no json"
    assert "no reasoning available" in render_critique(c, "x", "y")


def test_nuance_rows_carry_an_id_for_the_ruling_cli() -> None:
    """--promote N / --bin N address nuances by id — the rows must expose it."""
    with tempfile.TemporaryDirectory() as d:
        log = NuanceLog(Path(d) / "n.db")
        log.record(day=date(2026, 7, 1), race_id="r1", course="Epsom", winner="W",
                   blind_pick="", nuance="n1", what_missed="", cite="", owed="",
                   confidence="low")
        row = log.all()[0]
        assert isinstance(row["id"], int)
        log.set_status(row["id"], "rejected")           # the master bins it
        assert log.all()[0]["status"] == "rejected"
        log.close()


def test_critique_carries_rule_evidence_and_the_system_verdict() -> None:
    """The improved detective: marks the system's own read + tests the notebook."""
    c = parse_critique(
        '{"nuance": "n", "what_i_missed": "m", '
        '"system_verdict": "the manner lens found the winner; the mark lens flagged it", '
        '"rule_evidence": [{"rule": "#1", "verdict": "Supports", "note": "asserted"}, '
        '{"rule": "#22", "verdict": "contradicts", "note": "raised horse won"}]}'
    )
    assert c.system_verdict.startswith("the manner lens")
    assert c.rule_evidence == (("#1", "supports", "asserted"),
                               ("#22", "contradicts", "raised horse won"))
    text = render_critique(c, "x", "y")
    assert "✓ #1 supports" in text and "✗ #22 contradicts" in text
    # prompt plumbing: the system read block appears only when supplied
    p = build_prompt("R", "W", None, system_read="Gem conv 3: well-in")
    assert "SYSTEM PRE-RACE READ" in p and "Gem conv 3" in p
    assert "SYSTEM PRE-RACE READ" not in build_prompt("R", "W", None)


def test_rule_evidence_tally_accumulates_per_rule() -> None:
    with tempfile.TemporaryDirectory() as d:
        log = NuanceLog(Path(d) / "n.db")
        for rid in ("r1", "r2"):
            log.record_evidence(day=date(2026, 7, 1), race_id=rid, rule="#1",
                                verdict="supports", note="finisher won")
        log.record_evidence(day=date(2026, 7, 1), race_id="r1", rule="#22",
                            verdict="contradicts", note="raised won")
        # same (date, race, rule, verdict) twice -> one row
        log.record_evidence(day=date(2026, 7, 1), race_id="r1", rule="#22",
                            verdict="contradicts", note="dup")
        tally = {t["rule"]: t for t in log.rule_tally()}
        assert tally["#1"]["supports"] == 2 and tally["#1"]["contradicts"] == 0
        assert tally["#22"]["contradicts"] == 1
        log.close()


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
