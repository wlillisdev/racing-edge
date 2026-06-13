# Reliability layer

This system runs unattended on PythonAnywhere. Historically it failed
*silently* — the morning email just wouldn't arrive, with no clue why. The
reliability layer turns every silent failure into a loud, visible one.

There are three independent safety nets. Each catches a different class of
failure, so a hole in one is covered by another.

---

## 1. Preflight self-check (`preflight.py`)

Runs as the **first thing** in both pipelines, before any real work. It verifies
the environment is sane and, on a critical problem, **emails a loud alert and
aborts** instead of building a briefing on a broken setup.

Checks, most-fundamental first:

| Check | Severity | Why |
|-------|----------|-----|
| Can import `dotenv`, `requests`, `mysql.connector`, `anthropic`, `tabulate` | **CRITICAL** | The exact failure that broke production (cron used a venv missing `python-dotenv`) |
| Config loads + all mandatory env vars present | **CRITICAL** | A missing key = `KeyError` at import = silent non-start |
| Database reachable (`SELECT 1`) | **CRITICAL** | No DB, no real briefing |
| Racing API host reachable + creds present | WARN | Pipeline degrades; don't block |
| SMTP login works (no send) | WARN | So briefings/alerts can actually send |
| `ANTHROPIC_API_KEY` present | WARN | Absence just disables the AI layer |

It's deliberately **self-contained** — it does not import anything that needs
`dotenv`, so it can still report a missing-`dotenv` failure instead of crashing
on it. The error message even prints the exact fix command for the running
interpreter.

Run it by hand any time:

```bash
python preflight.py
```

---

## 2. Heartbeat / dead-man's switch (`src/ops.py`)

Preflight can only fire if the run *starts*. The most dangerous failure is the
run that **never starts at all** (wrong interpreter, CPU quota, disabled/deleted
task) — total silence. The heartbeat catches that, because the monitor lives
**off** PythonAnywhere.

Each pipeline pings a URL **only on successful completion**. An external monitor
emails you if the ping doesn't arrive by its deadline.

### One-time setup (free)

1. Sign up at <https://healthchecks.io> (free tier is plenty).
2. Create two checks: "Racing — Morning" and "Racing — Evening".
   - Set each schedule to roughly when the task runs (e.g. morning daily ~09:00,
     with a grace period of an hour or two).
   - Set the notification to email you.
3. Copy each check's **ping URL** and add to `.env`:

   ```
   HEARTBEAT_URL_MORNING=https://hc-ping.com/<your-morning-uuid>
   HEARTBEAT_URL_EVENING=https://hc-ping.com/<your-evening-uuid>
   ```

If these are blank the ping is a no-op, so the system is safe to run without
them — you just don't get the dead-man's-switch protection.

---

## 3. Degraded-run email tagging

Both pipelines "continue past a failed step and always send the email." Good
intent, but a partially-broken run used to send a confident-looking briefing
with a normal subject.

Now, just before the email step, the pipeline records which steps failed to
`data/run_health_<stage>_<date>.json`. The email step reads it and, if anything
failed:

- tags the **subject** with `[DEGRADED: N failed]`, and
- prepends a loud `⚠ DEGRADED RUN` banner listing the failed steps to the body.

So a broken run is never mistaken for a clean one. (When an email script is run
by hand outside the pipeline, no health file exists and it behaves exactly as
before.)

---

## Scheduled-task commands (PythonAnywhere → Tasks)

Use the venv that has the dependencies installed, `cd` into the project, and
log everything. (If the venv lacks deps, preflight will now email you instead
of failing silently — but install them anyway:
`/home/v5racing/venv/bin/pip install -r requirements.txt`.)

**Morning** (e.g. 06:00 UTC):

```bash
cd /home/v5racing/racing_edge && /home/v5racing/.local/bin/python daily_pipeline.py >> /home/v5racing/racing_edge/logs/cron_morning.log 2>&1
```

**Evening** (e.g. 21:30 UTC):

```bash
cd /home/v5racing/racing_edge && /home/v5racing/.local/bin/python evening_audit_pipeline.py >> /home/v5racing/racing_edge/logs/cron_evening.log 2>&1
```

Make sure `logs/` exists: `mkdir -p /home/v5racing/racing_edge/logs`.
