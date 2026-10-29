> **ARCHIVED (audit 2026-09-02):** this page describes a retired generation of the system (old CLI names, old branches, old cron rows). The live contract is docs/ARCHITECTURE.md; the live scheduler is trial.sh on `main`. Kept for history only.

# Going live — shadow mode (safe, alongside the old system)

This runs the new `racing_edge` engine **next to** the existing V3/V4 system. It
records its own picks, settles them, and studies the whole card every night into
its own databases. **It touches nothing the live engine does, and it never places
a bet.** Worst case it runs quietly and we learn. (Blueprint rule: shadow first.)

## What it does and does NOT do yet

- ✅ **Records** the method's picks + the favourite benchmark each morning (CLV ledger).
- ✅ **Settles** them against results each evening.
- ✅ **Studies** every race on the card and banks the lessons (study DB) — the
  detective loop's evening half, with the in-running comments now captured.
- ❌ **Does NOT yet change the selection on the new findings.** The manner-downgrade
  isn't wired into the pick yet — that waits for a paper-test (see charter). So the
  *picks* are not smarter than the old system yet; what goes live now is the
  **record + study** that gives us the real data to make them smarter.

## One-time setup (on the deployment)

```bash
cd ~/racing_edge
git fetch origin && git checkout claude/rebuild-v5 && git pull origin claude/rebuild-v5
pip install -e .
# .env must already hold RACING_API_USERNAME / RACING_API_PASSWORD (Basic Auth) —
# it does, since the backtest ran. Nothing else to configure.
```

The new DBs land in `data/ledger.db` and `data/study.db` — separate files, nothing
the old system reads or writes.

## The daily commands

```bash
# Morning — record today's method picks (no bet, just banked to the ledger):
python -m racing_edge.cli.daily

# Evening (after racing) — settle, then study the whole card:
python -m racing_edge.cli.settle --day today
python -m racing_edge.cli.study  --day today
```

`cli.study` prints what the card taught (e.g. "rule #2 in the wild: 2nd/3rd fav won
N/M") and stores every race so it compounds.

## Cron (set and forget)

```cron
# morning record — 07:15
15 7 * * *  cd ~/racing_edge && /usr/bin/python -m racing_edge.cli.daily   >> ~/racing_edge/logs/daily.log  2>&1
# evening settle + study — 22:30 (after results are in)
30 22 * * * cd ~/racing_edge && /usr/bin/python -m racing_edge.cli.settle --day today >> ~/racing_edge/logs/settle.log 2>&1
35 22 * * * cd ~/racing_edge && /usr/bin/python -m racing_edge.cli.study  --day today >> ~/racing_edge/logs/study.log  2>&1
```

(`mkdir -p ~/racing_edge/logs` first. Adjust the python path / times for the box.)

## What to watch

- `data/study.db` filling night by night — that's the detective work compounding.
- The `cli.study` output — the rules being tested against real cards.
- Nothing breaking in the old system — because we never touched it.

## When you're ready for the next step

Once a couple of weeks of real studies are in the DB, we **paper-test** the manner
read against them (does it flag the nearly-types right?), and only then wire the
downgrade into the live selection. That's the order in `docs/charter.md`: record &
study live now → prove the brain on real data → then let it change the picks.
