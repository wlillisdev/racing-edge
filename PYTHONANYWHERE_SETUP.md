# PythonAnywhere Deployment Guide

Racing Intelligence System — v3
Target path: `/home/v5racing/racing_model`

---

## 1. Initial Setup

```bash
# Clone or upload project files
cd /home/v5racing
git clone https://github.com/wlillisdev/racing-edge.git racing_model
cd racing_model

# Create virtual environment
python3.10 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

---

## 2. Configure Environment

```bash
cp .env.example .env
nano .env   # fill in all real credentials
```

Required values in `.env`:
| Variable | Where to find it |
|---|---|
| `RACING_API_KEY` | The Racing API Pro dashboard |
| `DB_HOST` | PythonAnywhere Databases tab |
| `DB_NAME` | PythonAnywhere Databases tab (format: username$racing_model) |
| `DB_USER` | Your PythonAnywhere username |
| `DB_PASS` | Set in PythonAnywhere Databases tab |
| `EMAIL_SENDER` | Gmail address |
| `EMAIL_PASSWORD` | Gmail App Password (not your login password) |
| `EMAIL_RECIPIENT` | Where to receive reports |
| `PROJECT_DIR` | `/home/v5racing/racing_model` |

---

## 3. Create MySQL Database

In PythonAnywhere dashboard → Databases tab:
1. Create a new MySQL database named `racing_model`
2. Note the full database name shown (e.g. `v5racing$racing_model`)
3. Set a password and save it in `.env`

Then run the database foundation script:
```bash
venv/bin/python database_foundation.py
```

Verify with:
```bash
venv/bin/python database_config_check.py
```

Expected output: `OVERALL: PASS — all 11 tables present`

---

## 4. System Integrity Check

Before scheduling tasks, verify everything is working:
```bash
venv/bin/python system_integrity_check.py
```

Expected final line:
```
SYSTEM_STATUS: PASS - SAFE TO CONTINUE
```

---

## 5. Scheduled Tasks

In PythonAnywhere dashboard → Tasks tab, create these scheduled tasks.
All use the full venv Python path.

### Morning Pipeline (07:00 daily)
```
/home/v5racing/racing_model/venv/bin/python /home/v5racing/racing_model/daily_pipeline.py
```

### Market Update Pipeline (13:00 daily)
```
/home/v5racing/racing_model/venv/bin/python /home/v5racing/racing_model/market_update_pipeline.py
```

### Evening Audit Pipeline (20:00 daily)
```
/home/v5racing/racing_model/venv/bin/python /home/v5racing/racing_model/evening_audit_pipeline.py
```

### Weekly Learning (Sunday only — guard built into script)
```
/home/v5racing/racing_model/venv/bin/python /home/v5racing/racing_model/weekly_learning_task.py
```

### Database Import (run after each pipeline, or schedule at 21:00)
```
/home/v5racing/racing_model/venv/bin/python /home/v5racing/racing_model/db_import_racecards.py && /home/v5racing/racing_model/venv/bin/python /home/v5racing/racing_model/db_import_model_candidates.py && /home/v5racing/racing_model/venv/bin/python /home/v5racing/racing_model/db_import_market_moves.py && /home/v5racing/racing_model/venv/bin/python /home/v5racing/racing_model/db_import_results.py
```

---

## 6. Gmail App Password Setup

To send emails from Gmail:
1. Go to myaccount.google.com → Security → 2-Step Verification (must be enabled)
2. Search for "App passwords" → Create new app password
3. Select "Mail" and "Other (custom name)" → type "Racing Edge"
4. Copy the 16-character password into `.env` as `EMAIL_PASSWORD`

---

## 7. Pipeline Schedule Timeline

```
07:00  Morning pipeline runs
       → Fetches racecards from Racing API
       → Takes morning odds snapshot
       → Runs signposts, shortlist, race reader, form reader
       → Selects NAP via nap_selector_v3.py
       → Generates morning briefing
       → Sends morning email
       
13:00  Market update pipeline runs  
       → Refreshes racecards
       → Takes late odds snapshot
       → Classifies market movers (steamers/drifters)
       → Scans for non-runners
       → Generates final decision (CONFIRMED / BLOCKED / NO BET)
       → Guards output for safety
       → Sends market update email

20:00  Evening audit pipeline runs
       → Pulls race results from API (retries if not available)
       → Audits all selections (NAP, watchlist, shadow)
       → Updates performance_log.csv
       → Generates P/L report
       → Sends evening audit email

Sunday Weekly learning task
       → Weekly P/L summary
       → Horse tracker review
       → Promotion review (angle validation)
       → Database catch-up imports
```

---

## 8. Backup and Recovery

Create a backup at any time:
```bash
venv/bin/python create_full_backup.py
```

This creates a dated `.tar.gz` in `archive/external_exports/` with all code,
data, reports and the performance log (excludes `.env` and `venv/`).

For disaster recovery:
1. Upload the `.tar.gz` to a new PythonAnywhere account
2. Extract into `/home/v5racing/racing_model`
3. Re-create venv and install requirements
4. Copy `.env.example` to `.env` and fill in credentials
5. Run `system_integrity_check.py`

---

## 9. Troubleshooting

### Email not arriving
- Check `data/email_morning_failed_YYYY-MM-DD.flag` exists → SMTP error
- Check Gmail App Password is set correctly
- Check Less Secure App access or App Password in Gmail settings
- Run `email_report.py` manually to see error output

### Morning pipeline failed
- Check `reports/pipeline_morning_YYYY-MM-DD.txt` for step-by-step status
- Check `data/racecards_YYYY-MM-DD.json` exists → API call issue
- Verify `RACING_API_KEY` in `.env` is valid

### No NAP selected
- Normal behaviour when no clear standout or field is clustered
- Check `reports/nap_candidates_YYYY-MM-DD.txt` for day verdict
- Check `reports/cluster_review_YYYY-MM-DD.txt` for cluster details

### Database connection failed
- Verify `DB_HOST` format: `username.mysql.pythonanywhere-services.com`
- Check database password in PythonAnywhere Databases tab
- PythonAnywhere MySQL is only accessible from within PythonAnywhere

### Results not available at 20:00
- The evening pipeline retries up to 3 times with 15-minute gaps
- Racing API results endpoint can take 30-60 minutes post-race
- If still failing, run `results_auditor.py` manually later

---

## 10. Key Files Reference

| File | Purpose |
|---|---|
| `run_daily.py` | Fetch racecards from Racing API |
| `nap_selector_v3.py` | Core NAP selection (100-point scoring) |
| `final_nap_decision.py` | Final decision with safe-block protection |
| `system_integrity_check.py` | QA gate — run before any live operation |
| `database_foundation.py` | One-time DB setup |
| `create_full_backup.py` | Disaster recovery backup |
| `performance_log.csv` | Permanent P/L tracking record |
| `src/api_client.py` | Racing API Pro client |
| `src/db.py` | MySQL connection layer |
| `sql/schema.sql` | Full database schema |
