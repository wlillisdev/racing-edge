> **ARCHIVED (audit 2026-09-02):** this page describes a retired generation of the system (old CLI names, old branches, old cron rows). The live contract is docs/ARCHITECTURE.md; the live scheduler is trial.sh on `main`. Kept for history only.

# Deploy — racing_edge v4 (the clean rebuild)

This replaces the old 97-script sprawl with one installable package and three
commands. It needs **only your Racing API login** — the ledger is SQLite
(`data/ledger.db`), so there is no database to set up.

## 1. Get the code on the machine

```bash
cd ~/racing_edge                 # your existing checkout
git fetch origin
git checkout claude/rebuild-v4
git pull origin claude/rebuild-v4
```

## 2. Install (one venv, one command)

```bash
python3.11 -m venv venv
venv/bin/pip install -e .
```

## 3. Configure — just the API login

Create `.env` in the project root:

```
RACING_API_USERNAME=your_racing_api_username
RACING_API_PASSWORD=your_racing_api_password
# optional:
# REGIONS=gb,ire
# PROJECT_DIR=/home/v5racing/racing_edge
```

That's it — no DB host, no DB password. (Standard tier is enough; Pro only adds
deeper history.)

## 4. Run it

```bash
# morning — today's jumps card, picks with reasons, banked to the CLV ledger
venv/bin/python -m racing_edge.cli.daily

# evening — settle today's picks against results, print the honest scoreboard
venv/bin/python -m racing_edge.cli.settle --day today

# any time — the CLV ledger (no API call)
venv/bin/python -m racing_edge.cli.report
```

Flags: `--flat` (flat instead of jumps), `--both` (jumps AND flat handicaps in one
run, banked per code), `--day tomorrow|YYYY-MM-DD`, `--bank 500` (stake sizing),
`--no-record` (print without banking).

## 5. Schedule it (PythonAnywhere → Tasks)

Each Task runs one command line; the task log captures the output. (These use
`PYTHONPATH=src` so they work whether or not the package is `pip install -e .`'d.)

| Time | Command |
|---|---|
| 07:00 | `cd ~/racing_edge && PYTHONPATH=src venv/bin/python -m racing_edge.cli.daily --day today --both` |
| 07:05 | `cd ~/racing_edge && PYTHONPATH=src venv/bin/python -m racing_edge.cli.nap --day today --both` |
| 20:00 | `cd ~/racing_edge && PYTHONPATH=src venv/bin/python -m racing_edge.cli.settle --day today` |
| 20:05 | `cd ~/racing_edge && PYTHONPATH=src venv/bin/python -m racing_edge.cli.nap --settle today` |
| 21:00 | `cd ~/racing_edge && PYTHONPATH=src venv/bin/python -m racing_edge.cli.study --day today --frank` |

- **07:00 — the card.** `--both` covers jumps AND flat handicaps; the franking
  tiebreaker is on by default. This is the live, blind morning run (real prices).
- **20:00 — settle.** Marks the day's picks against results; updates the CLV ledger.
- **21:00 — study.** Post-mortems the readable handicaps and banks the lessons.

To deploy new code, `git pull origin claude/rebuild-v5` by hand (the Tasks do NOT
auto-pull, so an untested push never goes live on its own).

(Email is an easy add-on — say the word and it sends the card to your inbox; for
now it prints to the task log.)

## 6. Sanity check

```bash
venv/bin/python -m pytest          # 55 tests should pass
```

## What it does NOT do (by design)

- No black-box score, no auto-betting, no daily LLM cost. The human picks; this
  fetches, applies your transparent method, recommends a single value bet, and
  keeps the honest CLV ledger.
- The old `racing_model` / 97-script pipelines, the MySQL warehouse, and the
  daily Haiku calls are all retired. Point your scheduled tasks at the commands
  above and the old sprawl can be archived.
