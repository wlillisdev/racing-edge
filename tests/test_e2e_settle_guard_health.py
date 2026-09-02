"""END TO END, OFFLINE: the NIGHT SETTLE, the 12:30 GUARD and the 09:30 HEALTH
entry points — the real `main()` of cli/nap.py and cli/health.py, with
`sys.argv` monkeypatched and only the network edge (get_client) faked. The
Racing API's raw dict shapes go through the REAL normaliser
(data.normalise.results_from_raw / racecards_from_raw) so a drift there would
be caught here too.

Everything lives under pytest's tmp_path (PROJECT_DIR env var + chdir) — never
under the real repo's data/. src/ and docs/ are not touched; failures are
reported with file:line instead.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import pytest

from racing_edge.cli import health as health_cli
from racing_edge.cli import nap as nap_cli
from racing_edge.cli._common import open_nap_log
from racing_edge.config import get_config
from racing_edge.study.naplog import NapLog


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def project(tmp_path, monkeypatch):
    """A throwaway PROJECT_DIR, cwd'd into, with dummy API creds and mail left
    UNCONFIGURED (no EMAIL_* vars) so nothing tries to actually send. Config is
    `lru_cache`d process-wide (racing_edge.config.get_config) so the cache is
    cleared before AND after — otherwise a stale Config (pointing at the real
    repo, or at a previous test's tmp_path) leaks across tests."""
    monkeypatch.setenv("RACING_API_USERNAME", "dummyuser")
    monkeypatch.setenv("RACING_API_PASSWORD", "dummypass")
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    for k in ("EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECIPIENT", "SCHOOL_CHAMPION"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    get_config.cache_clear()
    # health takes the 09:30 board snapshot through the client door (2026-09-02):
    # an empty card here, so the entry point never touches the network
    monkeypatch.setattr("racing_edge.data.client.get_client",
                        lambda: type("_C", (), {"racecards": lambda self, d="today":
                                                 {"racecards": []}})())
    yield tmp_path
    get_config.cache_clear()


class FakeClient:
    """Stands in for racing_edge.data.client.RacingAPIClient — the only network
    edge in these entry points. Returns RAW dicts, exactly as the real client
    would, so the real normaliser does the parsing."""

    def __init__(self, results=None, cards=None, raise_results=False):
        self._results = results or {}
        self._cards = cards or {}
        self._raise_results = raise_results

    def results_by_date(self, date_str: str) -> dict:
        if self._raise_results:
            raise RuntimeError("simulated Racing API outage")
        return self._results.get(date_str, {"results": []})

    def racecards(self, day: str) -> dict:
        return self._cards.get(day, {"racecards": []})


def _runner_result(horse_id, horse, position=None, sp_dec=None):
    row = {"horse_id": horse_id, "horse": horse, "position": position}
    if sp_dec is not None:
        row["sp_dec"] = sp_dec
    return row


def _results_doc(race_id, race_date, runners):
    return {"results": [{"race_id": race_id, "date": race_date.isoformat(),
                          "runners": runners}]}


# --------------------------------------------------------------------------- #
# 1. SETTLE happy path
# --------------------------------------------------------------------------- #
def test_settle_happy_path_grades_the_read_and_writes_the_csv(project, monkeypatch, capsys):
    today = date.today()
    race_id = "race-happy"

    log = open_nap_log()
    log.record(day=today, race_id=race_id, course="Ascot", horse="Our Horse",
               horse_id="h1", price=4.0, score=5, confident=True,
               case="the case for Our Horse",
               danger="Danger Horse", crossed="Crossed Horse — no chance",
               my_price=3.5)
    log.record_shadow(day=today, race_id=race_id, course="Ascot", horse="Danger Horse",
                      horse_id="h2", price=3.0, score=4)
    log.record_favline(day=today, race_id=race_id, course="Ascot",
                       horse="Crossed Horse", horse_id="h3", price=8.0)
    log.close()

    raw_results = _results_doc(race_id, today, [
        _runner_result("h1", "Our Horse", position="1", sp_dec=4.0),   # our horse WON
        _runner_result("h2", "Danger Horse", position="2", sp_dec=3.0),  # danger 2nd
        _runner_result("h3", "Crossed Horse", position="5", sp_dec=8.0),  # crossed off, 5th
    ])
    fake = FakeClient(results={today.isoformat(): raw_results})
    monkeypatch.setattr(nap_cli, "get_client", lambda: fake)
    monkeypatch.setattr(sys, "argv", ["nap", "--settle", "today"])

    rc = nap_cli.main()
    out = capsys.readouterr().out

    assert rc == 0
    log2 = open_nap_log()
    row = log2.existing(today)
    shadow_rows = log2._conn.execute(
        "SELECT * FROM shadow WHERE date = ?", (today.isoformat(),)).fetchone()
    favline_rows = log2._conn.execute(
        "SELECT * FROM favline WHERE date = ?", (today.isoformat(),)).fetchone()
    log2.close()

    assert row["won"] == 1
    assert row["sp_dec"] == 4.0
    assert "danger behind us" in row["read_grade"]
    assert shadow_rows["won"] == 0          # danger ran 2nd -> unplaced
    assert favline_rows["won"] == 0         # crossed-off horse ran 5th -> unplaced
    assert (project / "data" / "nap_record.csv").exists()
    # WHAT WE MEASURE (2026-09-02): the settled nap rides into the policy ledger
    _pol = (project / "data" / "school" / "daily_policy.csv").read_text()
    assert f"{today.isoformat()},nap,1,1," in _pol
    assert f"{today} nap:" in out


# --------------------------------------------------------------------------- #
# 2. SETTLE non-runner via the REAL normaliser
# --------------------------------------------------------------------------- #
def test_settle_null_position_no_status_voids_as_non_runner(project, monkeypatch):
    """A raw `"position": None` with no separate status string is exactly how a
    feed marks a withdrawn horse (data/normalise._position -> (None, "")).
    NapLog._settle_tables must VOID this, never invent a loss."""
    today = date.today()
    race_id = "race-nr"
    log = open_nap_log()
    log.record(day=today, race_id=race_id, course="York", horse="Ghost Horse",
               horse_id="hg", price=5.0, score=3, confident=False)
    log.close()

    raw_results = _results_doc(race_id, today, [
        _runner_result("hg", "Ghost Horse", position=None),
        _runner_result("hx", "Other Horse", position="1", sp_dec=2.0),
    ])
    fake = FakeClient(results={today.isoformat(): raw_results})
    monkeypatch.setattr(nap_cli, "get_client", lambda: fake)
    monkeypatch.setattr(sys, "argv", ["nap", "--settle", "today"])

    rc = nap_cli.main()
    assert rc == 0

    log2 = open_nap_log()
    row = log2.existing(today)
    log2.close()
    assert row["won"] == NapLog.VOID
    assert "non-runner" in row["void_reason"]


def test_settle_faller_status_is_a_real_loss(project, monkeypatch):
    """A faller ("F") RAN and lost — never a void. data.normalise._position
    parses a non-digit position into (None, "F")."""
    today = date.today()
    race_id = "race-faller"
    log = open_nap_log()
    log.record(day=today, race_id=race_id, course="Cheltenham", horse="Faller Horse",
               horse_id="hf", price=6.0, score=3, confident=False)
    log.close()

    raw_results = _results_doc(race_id, today, [
        _runner_result("hf", "Faller Horse", position="F"),
        _runner_result("hx", "Winner Horse", position="1", sp_dec=3.0),
    ])
    fake = FakeClient(results={today.isoformat(): raw_results})
    monkeypatch.setattr(nap_cli, "get_client", lambda: fake)
    monkeypatch.setattr(sys, "argv", ["nap", "--settle", "today"])

    rc = nap_cli.main()
    assert rc == 0

    log2 = open_nap_log()
    row = log2.existing(today)
    log2.close()
    assert row["won"] == 0                 # a real loss, not VOID
    assert row["void_reason"] in ("", None)


# --------------------------------------------------------------------------- #
# 3. SETTLE backlog sweep
# --------------------------------------------------------------------------- #
def test_settle_backlog_sweep_settles_recent_and_voids_stale(project, monkeypatch):
    today = date.today()
    d3 = today - timedelta(days=3)
    d9 = today - timedelta(days=9)

    log = open_nap_log()
    log.record(day=d3, race_id="race-d3", course="Bath", horse="Three Day Horse",
               horse_id="h3d", price=4.0, score=4, confident=True)
    log.record(day=d9, race_id="race-d9", course="Ripon", horse="Nine Day Horse",
               horse_id="h9d", price=5.0, score=4, confident=True)
    log.close()

    raw_results_d3 = _results_doc("race-d3", d3, [
        _runner_result("h3d", "Three Day Horse", position="1", sp_dec=4.0),
    ])
    fake = FakeClient(results={
        today.isoformat(): {"results": []},   # nothing banked today itself
        d3.isoformat(): raw_results_d3,
        # d9 deliberately absent from the map -> FakeClient returns {"results": []}
    })
    monkeypatch.setattr(nap_cli, "get_client", lambda: fake)
    monkeypatch.setattr(sys, "argv", ["nap", "--settle", "today"])

    rc = nap_cli.main()
    assert rc == 0

    log2 = open_nap_log()
    row3 = log2.existing(d3)
    row9 = log2.existing(d9)
    log2.close()

    assert row3["won"] == 1
    assert row9["won"] == NapLog.VOID
    assert f"--settle {d9.isoformat()}" in row9["void_reason"]


# --------------------------------------------------------------------------- #
# 4. SETTLE results-fetch failure
# --------------------------------------------------------------------------- #
def test_settle_results_fetch_failure_fails_loud_but_clean(project, monkeypatch, capsys):
    today = date.today()
    log = open_nap_log()
    log.record(day=today, race_id="race-fail", course="Fail Course", horse="Some Horse",
               horse_id="hs", price=4.0, score=4, confident=True)
    log.close()

    fake = FakeClient(raise_results=True)
    monkeypatch.setattr(nap_cli, "get_client", lambda: fake)
    monkeypatch.setattr(sys, "argv", ["nap", "--settle", "today"])

    rc = nap_cli.main()
    out = capsys.readouterr().out

    assert rc == 1
    assert "results fetch failed" in out
    assert "Traceback" not in out          # no traceback escapes to stdout

    log2 = open_nap_log()
    row = log2.existing(today)
    log2.close()
    assert row["won"] is None              # nothing changed


# --------------------------------------------------------------------------- #
# 5. GUARD — the 12:30 board read + drift check
# --------------------------------------------------------------------------- #
def test_guard_writes_1230_snapshot_and_reads_the_board(project, monkeypatch, capsys):
    today = date.today()
    race_id = "race-guard"

    log = open_nap_log()
    log.record(day=today, race_id=race_id, course="Kempton", horse="Nap Horse",
               horse_id="h1", price=5.0, score=4, confident=True)
    log.close()

    morning_prices = {
        race_id: {
            "course": "Kempton", "off": "14:00",
            "runners": {
                "h1": ["Nap Horse", 5.0],
                "h2": ["Steamer Horse", 10.0],
                "h3": ["Drifter Horse", 4.0],
            },
        }
    }
    nap_cli._board_snapshot(today, "0730", morning_prices)

    raw_cards = {"racecards": [{
        "race_id": race_id, "course": "Kempton", "off_time": "14:00",
        "date": today.isoformat(), "type": "Hurdle",
        "runners": [
            {"horse_id": "h1", "horse": "Nap Horse", "odds": [5.0]},
            {"horse_id": "h2", "horse": "Steamer Horse", "odds": [6.0]},   # 10.0 -> 6.0 = STEAMER
            {"horse_id": "h3", "horse": "Drifter Horse", "odds": [6.0]},   # 4.0 -> 6.0 = DRIFTER
        ],
    }]}
    fake = FakeClient(cards={"today": raw_cards})
    monkeypatch.setattr(nap_cli, "get_client", lambda: fake)
    monkeypatch.setattr(sys, "argv", ["nap", "--guard"])

    from racing_edge.report import mail as mail_mod
    assert mail_mod.configured() is False   # mail must be unconfigured for this test

    rc = nap_cli.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "STEAMER" in out
    assert "DRIFTER" in out
    assert "THE NAP'S RACE" in out
    snap_1230 = project / "data" / "market_snapshots" / f"{today.isoformat()}-1230.json"
    assert snap_1230.exists()


# --------------------------------------------------------------------------- #
# 6. HEALTH — the 09:30 red/green report
# --------------------------------------------------------------------------- #
def test_health_reds_a_stale_unsettled_nap(project, monkeypatch, capsys):
    today = date.today()
    d3 = today - timedelta(days=3)

    log = open_nap_log()
    log.record(day=today, race_id="race-h-today", course="Ayr", horse="Today Horse",
               horse_id="ht", price=4.0, score=4, confident=True, case="today's case")
    log.record(day=d3, race_id="race-h-stale", course="Cork", horse="Stale Horse",
               horse_id="hstale", price=5.0, score=4, confident=True, case="stale case")
    log.close()

    monkeypatch.setattr(sys, "argv", ["health"])
    rc = health_cli.main()
    out = capsys.readouterr().out

    # the third price point of the day is written by health (the flip-flop's data)
    assert (project / "data" / "market_snapshots" / f"{today.isoformat()}-0930.json").exists()
    assert "09:30 snapshot written" in out
    assert rc == 1
    assert "RED" in out
    assert d3.isoformat() in out
    assert "--settle" in out               # the named console command rides with the alarm


def test_health_settled_nap_and_fresh_tier0_do_not_crash(project, monkeypatch, capsys):
    """No task_runs.log / model_usage.csv anywhere the health check can see them
    (see report notes on health.py's path resolution) — must survive their
    absence, never crash, and still print the scoreboard/rulings section."""
    today = date.today()
    log = open_nap_log()
    log.record(day=today, race_id="race-h-settled", course="Newbury",
               horse="Settled Horse", horse_id="hset", price=3.0, score=5,
               confident=True, case="settled case")
    log.settle(today, won=True, sp_dec=3.0)
    log.close()

    tier0_dir = project / "data" / "school"
    tier0_dir.mkdir(parents=True, exist_ok=True)
    (tier0_dir / "tier0.md").write_text("# tier0 pass\nfresh\n")

    monkeypatch.setattr(sys, "argv", ["health"])
    rc = health_cli.main()
    out = capsys.readouterr().out

    assert rc in (0, 1)                    # must not raise; either verdict is legal here
    assert "Traceback" not in out
    assert ("read scoreboard" in out) or ("rulings:" in out)
    assert "tier-0 pass fresh" in out
