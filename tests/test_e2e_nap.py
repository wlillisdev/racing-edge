"""END TO END, OFFLINE: the MORNING NAP PIPELINE — `racing_edge.cli.nap.main()`
exactly as the box runs it at 07:30 (`--day today --both --email`, NAP_MODE
unset -> engine mode), against a FAKE racing-data client and a FAKE deep
reader, in a throwaway `tmp_path` working directory.

Nothing under src/ or docs/ is touched. The only network edges
(`racing_edge.cli.nap.get_client` and, for the second test,
`racing_edge.ai.reason.get_investigator`) are monkeypatched; everything else
(evaluate_field, conviction, mark_read, frank_form, the shape book, the
scorecard, the ledger) runs for real against the fixture data, through the
REAL normaliser (data.normalise) exactly as test_e2e_settle_guard_health.py
does for --settle/--guard.

Covers:
  1. test_engine_mode_end_to_end_deep_read_off  - the exact 07:30 box command,
     no ANTHROPIC_API_KEY (deep read OFF) -> engine-only bank.
  2. test_engine_mode_with_canned_deep_read     - same command, with
     racing_edge.ai.reason.get_investigator monkeypatched to a canned JSON
     pick (the mp / deep-case path).
  3. test_force_rebank_on_settled_day_refuses_cleanly - --force-rebank
     against an already-SETTLED day: must say "NOT banked" and exit 1,
     never crash.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from racing_edge.cli import nap as nap_cli
from racing_edge.cli._common import open_nap_log, resolve_date
from racing_edge.config import get_config

UK = ZoneInfo("Europe/London")


# --------------------------------------------------------------------------- #
# fixtures / env
# --------------------------------------------------------------------------- #
@pytest.fixture
def project(tmp_path, monkeypatch):
    """A throwaway PROJECT_DIR, cwd'd into it, dummy Racing API creds, mail
    left UNCONFIGURED (no EMAIL_* vars -> --email is a safe no-op) and
    ANTHROPIC_API_KEY unset (deep read OFF by default). get_config() is
    lru_cache'd process-wide, so the cache is cleared before AND after —
    otherwise a stale Config (the real repo, or a previous test's tmp_path)
    leaks across tests."""
    monkeypatch.setenv("RACING_API_USERNAME", "dummyuser")
    monkeypatch.setenv("RACING_API_PASSWORD", "dummypass")
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    for k in ("EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECIPIENT",
              "ANTHROPIC_API_KEY", "NAP_MODE", "SCHOOL_CHAMPION"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    get_config.cache_clear()
    yield tmp_path
    get_config.cache_clear()


def _future_off_time(minutes: int = 180) -> str:
    """An off_time string, in the card's own 'H:MM, no am/pm' convention,
    safely in the future of the REAL UK wall clock (the live-day time guard
    in pipeline.nap.evaluate_field uses real time for day='today', not an
    injectable clock) — and never crossing midnight, which the guard's
    'hours 1-9 read as PM' hack would otherwise misread as being in the past.
    """
    now = datetime.now(UK)
    for m in (minutes, 60, 30, 15, 10):
        target = now + timedelta(minutes=m)
        if target.date() == now.date():
            return f"{target.hour}:{target.minute:02d}"
    # last-resort (test running in the last few minutes of the UK day)
    return f"{now.hour}:{min(now.minute + 1, 59):02d}"


# --------------------------------------------------------------------------- #
# fixture racecard: one Class 4 turf handicap (8 priced runners), one Class 6
# handicap (bottom-grade, dreck column), one novice race (unreadable -> must
# never reach the field at all).
# --------------------------------------------------------------------------- #
COURSE_A = "Newbury"
COURSE_B = "Wolverhampton"
TARGET_HORSE = "Handy Copper"        # the designed engine survivor: well-in,
TARGET_ID = "H2"                     # 2nd favourite, course-proven -> confident
FAV_HORSE = "Market Leader"
FAV_ID = "H1"


def _hist_race(date_s: str, course: str, rtype: str, rclass: str,
               horse_id: str, position: str, orr: str | None = None,
               comment: str = "") -> dict:
    """One past-race row, shaped exactly as data.normalise.past_runs_from_raw
    expects (a RACE object with a nested runners list keyed by horse_id) —
    race_id left BLANK on purpose: study.frank.frank_form only walks a race
    with a race_id, so this keeps the frank a clean, deterministic
    'too soon to frank' rather than needing a working results_by_date."""
    runner = {"horse_id": horse_id, "position": position, "comment": comment}
    if orr is not None:
        runner["or"] = orr
    return {"date": date_s, "course": course, "type": rtype, "class": rclass,
            "going": "Good", "dist_f": "16f", "race_id": "", "ran": "8",
            "runners": [runner]}


def _runner(horse_id: str, horse: str, price: float, ofr: int, age: int = 8,
           trainer_id: str = "T", jockey_id: str = "J") -> dict:
    return {"horse_id": horse_id, "horse": horse, "trainer_id": trainer_id,
            "jockey_id": jockey_id, "age": str(age), "ofr": str(ofr),
            "odds": [{"decimal": str(price)}]}


def build_card() -> dict:
    off_a = _future_off_time()
    off_b = _future_off_time(200)
    today = resolve_date("today").isoformat()

    # ---- Race A: Class 4 turf handicap, 8 priced runners, anchored market
    # (top-3 concentration > 0.75) so it clears the betting-race bar.
    runners_a = [
        _runner(FAV_ID, FAV_HORSE, 2.5, 78, age=9),
        _runner(TARGET_ID, TARGET_HORSE, 4.0, 86, age=8),
        _runner("H3", "Third String", 5.0, 74, age=7),
        _runner("H4", "Fourth Estate", 6.0, 70, age=9),
        _runner("H5", "Fifth Element", 8.0, 68, age=8),
        _runner("H6", "Sixth Sense", 10.0, 65, age=7),
        _runner("H7", "Seventh Heaven", 12.0, 60, age=10),
        _runner("H8", "Eighth Wonder", 20.0, 55, age=9),
    ]
    race_a = {
        "race_id": "RACE-A", "course": COURSE_A, "off_time": off_a,
        "date": today, "race_name": "Class 4 Handicap", "type": "Flat",
        "class": "4", "going": "Good", "distance_f": "16", "region": "GB",
        "runners": runners_a,
    }

    # ---- Race B: Class 6 handicap (bottom-grade, dreck column) — same
    # anchored-market shape, weaker horses, no wins in sight (mark unread).
    runners_b = [
        _runner("B1", "Bottom Grader", 3.0, 55, age=8),
        _runner("B2", "Class Six Colt", 4.5, 52, age=7),
        _runner("B3", "Handicap Filler", 6.0, 50, age=9),
        _runner("B4", "Also Ran", 9.0, 48, age=8),
        _runner("B5", "Long Shot", 15.0, 45, age=10),
        _runner("B6", "Rank Outsider", 25.0, 40, age=9),
    ]
    race_b = {
        "race_id": "RACE-B", "course": COURSE_B, "off_time": off_b,
        "date": today, "race_name": "Class 6 Handicap", "type": "Flat",
        "class": "6", "going": "Standard", "distance_f": "10", "region": "GB",
        "runners": runners_b,
    }

    # ---- Race C: a novice race — must never reach evaluate_field's output
    # at all (is_novice and not is_handicap -> not is_readable).
    runners_c = [_runner(f"N{i}", f"Novice{i}", p, 60)
                for i, p in enumerate((3.0, 4.0, 5.0, 6.0), start=1)]
    race_c = {
        "race_id": "RACE-C", "course": "Southwell", "off_time": _future_off_time(220),
        "date": today, "race_name": "Novice Stakes", "type": "Flat",
        "going": "Standard", "distance_f": "6", "region": "GB",
        "runners": runners_c,
    }

    return {"racecards": [race_a, race_b, race_c]}


def build_histories() -> dict[str, list[dict]]:
    """3-5 past runs per Race-A/B contender: real positions, real comments
    ('led, ridden out' / 'hampered'), real ofr — everyone Flat-coded so
    conviction's SAME-CODE filter never empties a history out from under it.
    """
    hist: dict[str, list[dict]] = {}

    # the favourite: 5 runs, no recent win, no flags-worthy shortcuts (5 runs
    # skips the len<=4 'improver-favourite' gate; 5 < 6 skips the 'no win in
    # N runs' gate too) — a plain, unconvincing profile.
    hist[FAV_ID] = [
        _hist_race("2026-08-20", COURSE_A, "Flat", "4", FAV_ID, "2", "78",
                  "every chance, found little"),
        _hist_race("2026-08-01", COURSE_A, "Flat", "4", FAV_ID, "4", "78",
                  "held up, no impression"),
        _hist_race("2026-07-15", COURSE_B, "Flat", "5", FAV_ID, "3", "76",
                  "stayed on same pace"),
        _hist_race("2026-06-28", COURSE_B, "Flat", "5", FAV_ID, "5", "75",
                  "hampered start, never a factor"),
        _hist_race("2026-06-10", COURSE_A, "Flat", "4", FAV_ID, "2", "74",
                  "led, headed close home"),
    ]

    # THE TARGET: two course wins at-or-above today's mark (86) -> WELL-IN,
    # both wins recent -> RED-HOT / won-last-two, market rank 2 -> sweet
    # spot. Mirrors the exact recipe pinned by
    # tests/test_nap.py::test_conviction_rewards_the_well_in_proven_horse.
    hist[TARGET_ID] = [
        _hist_race("2026-08-22", COURSE_A, "Flat", "4", TARGET_ID, "1", "86",
                  "led, ridden out"),
        _hist_race("2026-08-05", COURSE_A, "Flat", "4", TARGET_ID, "1", "82",
                  "quickened clear, readily"),
        _hist_race("2026-07-18", COURSE_B, "Flat", "5", TARGET_ID, "3", "80",
                  "one paced final furlong"),
    ]

    generic = {
        "H3": (68, "3", "every chance, found little"),
        "H4": (64, "5", "hampered, no room"),
        "H5": (62, "2", "stayed on well"),
        "H6": (60, "4", "always behind"),
        "H7": (55, "6", "hampered early, never dangerous"),
        "H8": (50, "3", "led, headed inside final furlong"),
        "B1": (50, "4", "held up, no impression"),
        "B2": (48, "5", "hampered, lost place"),
        "B3": (45, "3", "stayed on same pace"),
        "B4": (43, "6", "never a factor"),
        "B5": (40, "2", "led, ridden out"),
        "B6": (35, "4", "always behind, eased"),
    }
    for hid, (orr, pos, comment) in generic.items():
        course = COURSE_A if hid.startswith("H") else COURSE_B
        rclass = "4" if hid.startswith("H") else "6"
        hist[hid] = [
            _hist_race("2026-08-18", course, "Flat", rclass, hid, pos, str(orr), comment),
            _hist_race("2026-07-28", course, "Flat", rclass, hid, "5", str(orr - 2),
                      "no extra"),
            _hist_race("2026-07-05", course, "Flat", rclass, hid, "4", str(orr - 4),
                      "hampered start"),
        ]
    for hid in ("N1", "N2", "N3", "N4"):
        hist[hid] = []      # the novice race is never read — histories moot
    return hist


class FakeClient:
    """Stands in for racing_edge.data.client.RacingAPIClient — the only
    network edge in evaluate_field/build_evidence/frank_form. Returns RAW
    dicts, exactly as the real client would, so the real normaliser
    (data.normalise) does the parsing — same discipline as
    test_e2e_settle_guard_health.py."""

    def __init__(self, card: dict, histories: dict[str, list[dict]]):
        self._card = card
        self._hist = histories

    def racecards(self, day: str = "today") -> dict:
        return self._card

    def horse_results(self, horse_id: str, limit: int = 12) -> list[dict]:
        return self._hist.get(horse_id, [])

    def trainer_jockeys(self, trainer_id: str) -> list[dict]:
        return []

    def trainer_course(self, trainer_id: str, course_id: str = "") -> list[dict]:
        return []

    def jockey_course(self, jockey_id: str) -> list[dict]:
        return []

    def horse_distance_times(self, horse_id: str) -> list[dict]:
        return []

    def trainer_ages(self, trainer_id: str) -> list[dict]:
        return []

    def results_by_date(self, date_str: str) -> dict:
        return {"results": []}

    def result_by_id(self, race_id: str) -> dict | None:
        return None


# --------------------------------------------------------------------------- #
# 1. the exact 07:30 box command, deep read OFF (no ANTHROPIC_API_KEY)
# --------------------------------------------------------------------------- #
def test_engine_mode_end_to_end_deep_read_off(project, monkeypatch, capsys):
    card = build_card()
    client = FakeClient(card, build_histories())
    monkeypatch.setattr(nap_cli, "get_client", lambda: client)
    monkeypatch.setattr(sys, "argv",
                        ["nap", "--day", "today", "--both", "--email"])

    rc = nap_cli.main()
    out = capsys.readouterr().out

    # (a) does not crash
    assert rc == 0
    assert "Traceback" not in out
    assert "(deep read OFF" in out            # confirms the intended code path

    today = resolve_date("today")

    # (b) banks a row (or a named pass) in data/nap.db
    log = open_nap_log()
    row = log.existing(today)
    log.close()
    assert row is not None, "no row banked for today at all"
    assert (project / "data" / "nap.db").exists()

    # (c) the day's files
    assert (project / "data" / "nap_record.csv").exists()
    assert (project / "data" / "school" / "opinions"
            / f"{today.isoformat()}.csv").exists()
    assert (project / "data" / "market_snapshots"
            / f"{today.isoformat()}-0730.json").exists()

    # (d) ENGINE'S YARDSTICK is built into every candidate-race readout
    # regardless of whether the deep reader is on (it's assembled BEFORE the
    # ANTHROPIC_API_KEY check) — proved directly on the pure builder rather
    # than by scraping stdout, since with the deep read OFF that readout is
    # never printed (it only ever feeds the model prompt). FAV LINE (or an
    # explicit pass reason) DOES print to stdout every real-bank run.
    assert row["race_id"] != "PASS", (
        "expected a full bank given the fixture's well-in target horse; "
        f"got a PASS instead: {row['case_text']!r}")
    assert row["horse"] == TARGET_HORSE
    assert "FAV LINE" in out

    # sanity: the row's own reasoning shows the engine-mode mechanical case,
    # not an empty claim
    assert "engine pick" in row["case_text"] or "conviction" in row["case_text"]


# --------------------------------------------------------------------------- #
# 2. same command, with a canned deep-read JSON pick (the mp path)
# --------------------------------------------------------------------------- #
def test_engine_mode_with_canned_deep_read(project, monkeypatch, capsys):
    card = build_card()
    client = FakeClient(card, build_histories())
    monkeypatch.setattr(nap_cli, "get_client", lambda: client)

    captured_prompts: list[str] = []

    def fake_get_investigator(task, tools, executor, max_steps=6, max_tokens=16000):
        def complete(system: str, prompt: str) -> tuple[str, list[str]]:
            captured_prompts.append(prompt)
            payload = {
                "race": f"{COURSE_A} {card['racecards'][0]['off_time']}",
                "horse": TARGET_HORSE,
                "case": ("Handy Copper is well-in off two course wins at today's "
                        "mark, sits 2nd favourite in an anchored market, and the "
                        "yardstick shows nothing else in the race with a live claim."),
                "my_price": 4.0,
                "race_readable_because": ("an honest Class 4 handicap with an "
                                          "anchored market and exposed form"),
                "crossed_off": [f"{FAV_HORSE} — no recent win, found little each time"],
                "cite": ["well-in mark (86 v last win 86)", "2nd favourite",
                        "two course wins"],
                "owed": "",
                "danger": {"horse": FAV_HORSE,
                          "its_case": "sits at the top of the market",
                          "beaten_because": "no win in five runs, found little each time"},
                "profile_match": {"well_in": True, "class_ok": True,
                                  "market_anchor": True,
                                  "note": "fits the winning profile squarely"},
                "confidence": "confident",
                "pass": False,
                "pass_reason": "",
            }
            return json.dumps(payload), ["horse_runs(H2)"]
        return complete

    monkeypatch.setattr("racing_edge.ai.reason.get_investigator",
                        fake_get_investigator)
    monkeypatch.setattr(sys, "argv",
                        ["nap", "--day", "today", "--both", "--email"])

    rc = nap_cli.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "Traceback" not in out
    assert "(deep read OFF" not in out        # the canned investigator was used
    assert captured_prompts, "the fake investigator was never called"

    # (d) the candidate-race readout that was actually SENT to the deep
    # reader carries the engine's yardstick, exactly as cli/nap.py builds it
    assert any("ENGINE'S YARDSTICK" in p for p in captured_prompts)
    assert "FAV LINE" in out

    today = resolve_date("today")
    log = open_nap_log()
    row = log.existing(today)
    log.close()
    assert row is not None and row["race_id"] != "PASS"
    assert row["horse"] == TARGET_HORSE
    assert row["confident"] == 1
    assert "DEEP READ" in row["case_text"]
    assert "THE DANGER" in row["case_text"]


# --------------------------------------------------------------------------- #
# 3. --force-rebank against an ALREADY-SETTLED day: must refuse cleanly
# --------------------------------------------------------------------------- #
def test_force_rebank_on_settled_day_refuses_cleanly(project, monkeypatch, capsys):
    card = build_card()
    client = FakeClient(card, build_histories())
    monkeypatch.setattr(nap_cli, "get_client", lambda: client)
    monkeypatch.setattr(sys, "argv",
                        ["nap", "--day", "today", "--both", "--email"])

    rc1 = nap_cli.main()
    assert rc1 == 0
    capsys.readouterr()          # discard the first run's output

    today = resolve_date("today")
    log = open_nap_log()
    row = log.existing(today)
    assert row is not None and row["race_id"] != "PASS", (
        "test setup requires a real bank to settle and re-bank against")
    log.settle(today, won=True, sp_dec=row["price"] or 4.0)
    log.close()

    # confirm the settle really stuck before testing the refusal
    log2 = open_nap_log()
    assert log2.existing(today)["won"] == 1
    log2.close()

    monkeypatch.setattr(sys, "argv",
                        ["nap", "--day", "today", "--both", "--email",
                         "--force-rebank"])
    rc2 = nap_cli.main()
    out2 = capsys.readouterr().out

    # (e) NOT banked, exit 1, never a crash
    assert rc2 == 1
    assert "NOT banked" in out2
    assert "Traceback" not in out2

    # the settled row must be untouched (law 1: the record is never edited)
    log3 = open_nap_log()
    row3 = log3.existing(today)
    log3.close()
    assert row3["won"] == 1
    assert row3["horse"] == TARGET_HORSE
