"""Tests for the narrative reader — grounding/hallucination control (pure)."""

from __future__ import annotations

import sys

from racing_edge.ai.narrative import parse_reads, read_narrative
from racing_edge.domain.models import Runner

SRC = "Hampered two out and stayed on well when no chance; remains well handicapped."


def test_parse_grounded_reads() -> None:
    items = [
        {"tag": "trouble_in_running", "note": "hampered late", "citation": "Hampered two out"},
        {"tag": "finished_well", "note": "kept going", "citation": "stayed on well"},
        {"tag": "well_handicapped", "note": "good mark", "citation": "remains well handicapped"},
    ]
    reads = parse_reads(items, SRC)
    assert len(reads) == 3
    assert {r.tag for r in reads} == {"trouble_in_running", "finished_well", "well_handicapped"}


def test_drops_ungrounded_citation() -> None:
    # citation not present in the source text -> hallucination, dropped
    items = [{"tag": "target_race", "note": "aimed at Cheltenham",
              "citation": "being aimed at the Cheltenham Festival"}]
    assert parse_reads(items, SRC) == []


def test_drops_unknown_tag() -> None:
    items = [{"tag": "will_win", "note": "nailed on", "citation": "stayed on well"}]
    assert parse_reads(items, SRC) == []


def test_drops_incomplete() -> None:
    assert parse_reads([{"tag": "finished_well", "note": "", "citation": "stayed on well"}], SRC) == []
    assert parse_reads("not a list", SRC) == []


def test_read_narrative_no_llm_or_empty() -> None:
    assert read_narrative(Runner(horse_id="H", horse="X", spotlight=SRC), None) == []
    assert read_narrative(Runner(horse_id="H", horse="X", spotlight=""), lambda p: "[]") == []


def test_read_narrative_with_stub_completer() -> None:
    r = Runner(horse_id="H", horse="X", spotlight=SRC)
    def stub(_prompt: str) -> str:
        return '[{"tag":"finished_well","note":"kept going","citation":"stayed on well"}]'
    reads = read_narrative(r, stub)
    assert len(reads) == 1 and reads[0].tag == "finished_well"


def test_read_narrative_swallows_bad_json() -> None:
    r = Runner(horse_id="H", horse="X", spotlight=SRC)
    assert read_narrative(r, lambda p: "not json at all") == []


def _main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\nTOTAL {len(fns)}/{len(fns)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
