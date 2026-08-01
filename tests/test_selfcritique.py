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
    # Rule One frames the school (the master, 2026-07-26): was the winner the best
    # horse, why was he best, and never learn a way-of-finding from a fluke
    assert "THE BEST HORSE WINS THE RACE" in SYSTEM
    assert "WHY was he the best" in SYSTEM and "fluke" in SYSTEM


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
    """Per-task model selection — economy tiers (2026-07-08, the burn): only THE pick
    keeps the flagship; nothing defaults to Haiku; and the TABLE now beats a global
    ANTHROPIC_MODEL (a stray global =fable in .env silently forced every nightly call
    onto the most expensive model — the trap that caused the huge daily bill)."""
    import os

    from racing_edge.ai.reason import resolve_model
    for var in ("ANTHROPIC_MODEL", "ANTHROPIC_MODEL_STUDY", "ANTHROPIC_MODEL_SCEPTIC"):
        os.environ.pop(var, None)
    assert resolve_model("study") == "claude-sonnet-5"
    assert resolve_model("sceptic") == "claude-sonnet-5"
    assert resolve_model("synthesis") == "claude-sonnet-5"
    assert resolve_model("nap") == "claude-opus-5"        # the one flagship call a day
    # (2026-08-01 cost pass: Opus 5 — flagship reasoning at half the premium price)
    for task in ("study", "sceptic", "synthesis", "nap"):
        assert "haiku" not in resolve_model(task)
    # THE TRAP IS DEAD: a global override no longer hijacks known tasks...
    os.environ["ANTHROPIC_MODEL"] = "claude-fable-5"
    assert resolve_model("study") == "claude-sonnet-5"
    assert resolve_model("unknown-task") == "claude-fable-5"   # ...only unknown ones
    # ...but an explicit per-task env still wins (deliberate beats accidental)
    os.environ["ANTHROPIC_MODEL_STUDY"] = "claude-opus-4-8"
    assert resolve_model("study") == "claude-opus-4-8"
    for var in ("ANTHROPIC_MODEL", "ANTHROPIC_MODEL_STUDY"):
        os.environ.pop(var, None)


def test_the_sceptic_is_adversarial_and_grounded() -> None:
    # the second pass attacks — but under FAIR rules of evidence (coroner 2026-07-21:
    # 104 refuted / 0 validated because the court was rigged): lookup-cited facts are
    # admissible, triviality files as support instead of killing, and the sceptic can
    # see the apprentice's tool trail
    assert "KILL the nuance" in REFUTE_SYSTEM
    for ground in ("CONTRADICTION", "ARTIFACT", "TRIVIALITY"):
        assert ground in REFUTE_SYSTEM
    assert "ADMISSIBLE" in REFUTE_SYSTEM              # lookups can't be killed on sight
    assert "TRIVIALITY is NOT a kill" in REFUTE_SYSTEM
    c = parse_critique('{"nuance": "the claim", "cite": ["WELL-IN at 8.5"], '
                       '"what_i_missed": "x"}')
    p = build_refute_prompt("THE-READOUT", c)
    assert "the claim" in p and "WELL-IN at 8.5" in p and "THE-READOUT" in p
    assert "TOOL LOOKUPS" not in p                    # no trail given -> no block
    p2 = build_refute_prompt("THE-READOUT", c, trail=["horse_runs(X) -> 4 runs"])
    assert "TOOL LOOKUPS" in p2 and "horse_runs(X)" in p2


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


def test_critique_mines_forward_clues_and_the_tracker_stores_them() -> None:
    """#27 forward mining: beaten horses with excuses/eye-catches become tracked
    follow/oppose clues that surface when the horse next runs."""
    assert "DISSECT EVERY HORSE" in SYSTEM and "FOLLOW" in SYSTEM
    c = parse_critique(
        '{"nuance": "n", "what_i_missed": "m", "to_follow": ['
        '{"horse": "Crackerjack Queen", "angle": "Follow", '
        '"note": "pressed the winner after making up ground from 12th", '
        '"conditions": "similar class, decent pace"}, '
        '{"horse": "Phantom Gold", "angle": "oppose", "note": "eye-catcher overbet", '
        '"conditions": "short price only"}]}'
    )
    assert c.to_follow[0] == ("Crackerjack Queen", "follow",
                              "pressed the winner after making up ground from 12th",
                              "similar class, decent pace", "")
    text = render_critique(c, "x", "y")
    assert "→ FOLLOW Crackerjack Queen" in text and "→ OPPOSE Phantom Gold" in text
    with tempfile.TemporaryDirectory() as d:
        from datetime import timedelta
        log = NuanceLog(Path(d) / "n.db")
        for _ in range(2):     # idempotent on (date, horse, angle)
            # relative date: a fixed 2026-07-01 aged past the 28-day window and the
            # test started failing by calendar alone (caught 2026-07-31)
            log.track(day=date.today() - timedelta(days=3), race_id="r1",
                      horse="Crackerjack Queen",
                      horse_id="H9", angle="follow", note="pressed the winner",
                      conditions="decent pace")
        rows = log.tracked_active()
        assert len(rows) == 1 and rows[0]["horse_id"] == "H9"
        assert rows[0]["status"] == "active"
        log.close()


def test_tracked_clues_settle_and_expire() -> None:
    """Coroner 2026-07-21: 872 tracked clues, none ever settled — an intake with no
    outflow. Clues now settle 'done' when the horse runs, and expire from the active
    list at 28 days (the clue was about the NEXT run; a month on it's stale)."""
    from datetime import timedelta
    with tempfile.TemporaryDirectory() as d:
        log = NuanceLog(Path(d) / "n.db")
        log.track(day=date.today() - timedelta(days=3), race_id="r1", horse="Fresh",
                  horse_id="F1", angle="follow", note="eye-catcher", conditions="")
        log.track(day=date.today() - timedelta(days=40), race_id="r0", horse="Stale",
                  horse_id="S1", angle="oppose", note="ancient clue", conditions="")
        active = log.tracked_active()
        assert [t["horse"] for t in active] == ["Fresh"]      # the 40-day row expired
        assert log.settle_tracked("F1", outcome="ran 2026-07-21, WON") == 1
        assert log.tracked_active() == []                     # settled = done
        done = log._conn.execute(
            "SELECT note, status FROM tracked WHERE horse_id = 'F1'").fetchone()
        assert done["status"] == "done" and "settled: ran 2026-07-21, WON" in done["note"]
        log.close()


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


def test_repetition_becomes_votes_and_the_record_promotes_themes() -> None:
    """2026-07-25 value audit: the loop re-proposed the same lesson nightly with no
    memory of itself (#190 = the Hoodie Hoo nuance), and nothing could reach any
    promoted status without the master. Now: a near-duplicate becomes a VOTE
    (seen_count), and a theme whose settled clues prove out is promoted to
    'field-tested' BY THE RECORD — 'validated' stays master-only."""
    with tempfile.TemporaryDirectory() as d:
        log = NuanceLog(Path(d) / "n.db")
        first = ("When a beaten horse's in-running comment shows a genuine "
                 "trouble-in-running excuse in a race later franked by the winner "
                 "going in again, upgrade that horse over the raw market position")
        assert log.record(day=date(2026, 7, 21), race_id="r1", course="Nottingham",
                          winner="Hoodie Hoo", blind_pick="", nuance=first,
                          what_missed="", cite="", owed="", confidence="medium",
                          theme="trouble-in-running-upgrade") is None
        rewrite = ("When a beaten horse's in-running comment shows genuine "
                   "trouble-in-running (short of room, checked, blocked) in a race "
                   "franked by the winner going in again, upgrade that horse over "
                   "the field's raw mark/market position")
        merged = log.record(day=date(2026, 7, 25), race_id="r9", course="York",
                            winner="X", blind_pick="", nuance=rewrite,
                            what_missed="", cite="", owed="", confidence="medium",
                            theme="trouble-in-running-upgrade")
        rows = log.all()
        assert merged == rows[0]["id"] and len(rows) == 1     # a vote, not a new row
        assert rows[0]["seen_count"] == 2
        # the record promotes: 5 settled clues of the theme, 4 held
        for i in range(5):
            log.track(day=date(2026, 7, 1 + i), race_id=f"t{i}", horse=f"H{i}",
                      horse_id=f"h{i}", angle="follow", note="quoted comment",
                      conditions="similar class, clean run needed",
                      theme="trouble-in-running-upgrade")
            log.settle_tracked(f"h{i}", outcome=f"ran 2026-07-2{i}, WON",
                               held=(i != 0))
        promoted = log.field_test_themes()
        assert promoted and "trouble-in-running-upgrade" in promoted[0]
        assert log.all()[0]["status"] == "field-tested"       # never 'validated'
        cs = log.clue_scoreboard(since="2026-07-01")
        assert cs["follow"]["n"] == 5 and cs["follow"]["hits"] == 4
        log.close()


def test_run_guarded_crash_names_itself_and_exits_1(capsys) -> None:
    """2026-08-01 architecture pass: a scheduled task's unhandled crash must
    return 1 (honest exit for the flight recorder), print the full traceback,
    and ATTEMPT the crash email — never invent success, never die silently."""
    from racing_edge.cli._common import run_guarded

    def _boom() -> int:
        raise RuntimeError("HTTP 401 Pro Plan required")

    assert run_guarded("night", _boom) == 1
    outp = capsys.readouterr().out
    assert "RuntimeError" in outp and "Pro Plan required" in outp   # named, loud
    assert "crash email" in outp                                    # tried to tell

    # a clean exit passes through untouched — the net never rewrites success
    assert run_guarded("night", lambda: 0) == 0
