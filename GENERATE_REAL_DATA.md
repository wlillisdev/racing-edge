# Generating the REAL Historical Dataset

This is the **prerequisite for validating any model recalibration**. Until the
real backtest CSV and the MySQL evidence warehouse are populated from live
Racing API data, the forensic / score-attribution / winner-DNA analyses are
running on nothing and their conclusions are meaningless.

Everything here **MUST run on PythonAnywhere** (or any host with Racing API
credentials and the MySQL database). The local dev environment has neither, so
it cannot generate this data.

---

## 1. Prerequisites

1. **Code deployed** under `PROJECT_DIR` (e.g. `/home/v5racing/racing_model`)
   with the virtualenv installed — see `PYTHONANYWHERE_SETUP.md`.

2. **`.env` fully populated.** The generator's steps need both the Racing API
   credentials and the database credentials:

   | Variable | Used for |
   |---|---|
   | `RACING_API_USERNAME` / `RACING_API_PASSWORD` | Fetching historical racecards + results |
   | `RACING_API_BASE` | Optional; defaults to `https://api.theracingapi.com/v1` |
   | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` | MySQL evidence warehouse |
   | `PROJECT_DIR` | Where `data/` and `reports/` are written |
   | `REGIONS` | Optional; defaults to `gb,ire` |

   Confirm with:
   ```bash
   venv/bin/python database_config_check.py
   ```

3. **MySQL database created** in the PythonAnywhere Databases tab. The
   generator runs `database_foundation.py` for you, but the empty database must
   already exist.

---

## 2. The one command

From `PROJECT_DIR`:

```bash
venv/bin/python generate_historical_dataset.py
```

That single command, in order:

1. **Ensures the schema** — runs `database_foundation.py` (creates all 11
   tables; `CREATE TABLE IF NOT EXISTS`, safe to re-run).
2. **Runs the historical backtest** — `historical_backtest.py` over the last
   **6 months** (the Racing API's practical maximum). It fetches real
   racecards and per-race results, replays the `nap_selector_v3` scoring, and
   writes:
   - `data/backtest_<from>_to_<to>.csv`  ← **the forensic-analysis input**
   - `data/backtest_cache/racecards/<date>.json` and
     `data/backtest_cache/race_results/<race_id>.json` ← cached API data
     (re-runs are free for already-fetched dates)
   - `reports/backtest_<from>_to_<to>.txt` ← human-readable summary
3. **Populates the 11 tables** — runs the DB importers in dependency order:
   `db_import_racecards.py` → `db_import_results.py` →
   `db_import_market_moves.py` → `db_import_model_candidates.py`.
4. Writes a run summary to `reports/historical_dataset_<today>.txt` and
   `data/historical_dataset_<today>.json`.

### Common variants

```bash
# Longer lookback (only as far back as the API allows)
venv/bin/python generate_historical_dataset.py --months 12

# Explicit date range
venv/bin/python generate_historical_dataset.py --from 2025-06-01 --to 2026-06-07

# Lower the NAP score threshold passed to the backtest
venv/bin/python generate_historical_dataset.py --min-score 55

# Backtest / CSV only — skip all DB writes
venv/bin/python generate_historical_dataset.py --skip-imports

# Schema already built — skip that step
venv/bin/python generate_historical_dataset.py --skip-schema

# Choose the date the db_import_* steps read (they consume the daily-pipeline
# JSON files for that single date; default is today)
venv/bin/python generate_historical_dataset.py --import-date 2026-06-08
```

### Idempotency

Re-running is safe. The backtest caches every fetched day, the schema step uses
`IF NOT EXISTS`, and every importer uses `INSERT IGNORE` / `ON DUPLICATE KEY
UPDATE`. A second run will not double-count or re-spend API calls on cached
days.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | The backtest produced a CSV with data rows — the foundation exists |
| `1` | No CSV / empty CSV was produced, or the pipeline could not start |

---

## 3. Expected runtime and cost

The backtest is the expensive part. With a `~0.6s` delay between API calls and
roughly one racecard call per day plus one results call per race:

- **~6 months ≈ 180 days.** On busy GB/IRE days that is many races/day, so the
  first run makes **thousands of API calls** and can take **45–120+ minutes**
  depending on field counts and API latency.
- This will consume a meaningful slice of your Racing API Pro request quota —
  run it once, deliberately, ideally off-peak.
- **Subsequent runs are cheap**: every fetched day/race is cached under
  `data/backtest_cache/`, so re-runs skip the API entirely for cached dates.

Because of the long runtime, the generator sets a generous **6-hour per-step
timeout** by default. Run it inside a PythonAnywhere **console** (or an
**Always-on task** / scheduled task) so it is not killed by a web-request
timeout. To run unattended:

```bash
nohup venv/bin/python generate_historical_dataset.py > generate_real_data.log 2>&1 &
tail -f generate_real_data.log
```

---

## 4. Verify the data populated

### 4a. The forensic CSV (what the analysis scripts actually read)

```bash
ls -lh data/backtest_*.csv
wc -l  data/backtest_*.csv      # header + one row per top-scored runner per race
```

A healthy 6-month GB/IRE run yields **thousands** of rows. If this file is
missing or only has a header, the generator exits `1` and the analysis below
will have nothing to work on.

### 4b. The MySQL tables

Connect (PythonAnywhere Databases tab gives the MySQL console command) and run:

```sql
SELECT 'system_runs'             AS tbl, COUNT(*) FROM system_runs
UNION ALL SELECT 'races',                  COUNT(*) FROM races
UNION ALL SELECT 'runners',                COUNT(*) FROM runners
UNION ALL SELECT 'model_candidates',       COUNT(*) FROM model_candidates
UNION ALL SELECT 'odds_snapshots',         COUNT(*) FROM odds_snapshots
UNION ALL SELECT 'market_moves',           COUNT(*) FROM market_moves
UNION ALL SELECT 'results',                COUNT(*) FROM results
UNION ALL SELECT 'trainer_market_profiles',COUNT(*) FROM trainer_market_profiles
UNION ALL SELECT 'form_strength_records',  COUNT(*) FROM form_strength_records
UNION ALL SELECT 'horse_tracker_records',  COUNT(*) FROM horse_tracker_records
UNION ALL SELECT 'angle_performance',      COUNT(*) FROM angle_performance;
```

Or from the shell:

```bash
venv/bin/python database_config_check.py
```

**What to expect:** `races` / `runners` / `results` populate from whatever
daily-pipeline JSON files exist on disk for the `--import-date` (default today).
The number of rows therefore reflects the daily pipeline's coverage, not the
full backtest window — the backtest's full history lives in the **CSV**, which
is what the recalibration analyses consume. The audit trail of every import run
is in `system_runs`.

> Note: `form_strength_records`, `horse_tracker_records`, and
> `angle_performance` are populated by their own modules (form analyser, horse
> tracker, weekly learning task), not by this generator — they may be empty
> immediately after a first run and fill in as the daily pipeline runs.

---

## 5. Run the forensic analyses against the now-real data

Once `data/backtest_*.csv` exists, run the three analysis scripts. Each one
auto-discovers the **most recent** `data/backtest_*.csv` (or pass `--csv`
explicitly):

```bash
venv/bin/python forensic_backtest_analysis.py        # multi-dimensional strike/ROI forensics
venv/bin/python score_attribution_analysis.py        # which score components predict winners
venv/bin/python winner_dna_analysis.py               # shared traits of actual winners
```

To pin a specific CSV:

```bash
venv/bin/python forensic_backtest_analysis.py --csv data/backtest_2025-12-09_to_2026-06-08.csv
```

Outputs land in `data/` (e.g. `forensic_analysis_<date>.json`,
`score_attribution_<date>.json`, `winner_dna_<date>.json`) and corresponding
reports under `reports/`.

These three reports are the evidence base for **model recalibration**: do not
adjust scoring weights, thresholds, or filters in the live model until they have
been produced from this real dataset.

---

## 6. Where the data lives (quick reference)

| Path | Produced by | Consumed by |
|---|---|---|
| `data/backtest_<range>.csv` | `historical_backtest.py` | the 3 forensic analysis scripts |
| `data/backtest_cache/racecards/<date>.json` | `historical_backtest.py` | backtest re-runs (cache) + optional analysis enrichment |
| `data/backtest_cache/race_results/<race_id>.json` | `historical_backtest.py` | backtest re-runs (cache) |
| 11 MySQL tables | `database_foundation.py` + `db_import_*.py` | DB-backed reporting / tracking modules |
| `reports/historical_dataset_<date>.txt` | `generate_historical_dataset.py` | operator (this run's summary) |
