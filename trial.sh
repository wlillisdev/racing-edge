#!/usr/bin/env bash
#
# racing-edge — FORM TRIAL runner (PythonAnywhere)
#
#   ./trial.sh nap       MORNING: nominate + BANK today's pick (the new rules on real data)
#   ./trial.sh dissect   read the whole card's REAL market moves (backed/drifted)
#   ./trial.sh settle    AFTER RACING: settle the banked pick, update the strike rate
#   ./trial.sh restudy   THE LEARNING LOOP (read): re-study finished races off the FULL
#                        form (mark, figures, each horse's last runs WITH comments) — what
#                        did we miss? focus one race with RESTUDY_TIME=16:10
#   ./trial.sh learn     THE LEARNING LOOP (think): self-interrogate the result — why did
#                        we pick / miss? — and BANK the nuance. Needs ANTHROPIC_API_KEY set
#                        (uses the direct-HTTP reasoner, not the crashing SDK). LEARN_TIME=..
#   ./trial.sh all       nap + dissect in one go
#
# Every run also EMAILS its output if the SMTP env vars are set (EMAIL_SENDER /
# EMAIL_PASSWORD / EMAIL_RECIPIENT); if they're not, it just prints here and says so.
# Picks are banked BEFORE the off and settled AFTER — checkable in data/nap.db.
# No cheating, no hindsight, no tipster: the new rules read the real card, and the
# record decides.
#
set -euo pipefail
cd "$(dirname "$0")"

# FLIGHT RECORDER (2026-07-21): the scheduled task kept silently not-running and the
# only evidence lived on the Tasks webpage. Now every run — scheduled or manual —
# logs its start, its FULL output and its exit code to data/task_runs.log, readable
# from the console:  tail -80 data/task_runs.log
mkdir -p data
LOGF="data/task_runs.log"
echo "=== $(date -u '+%F %T') UTC :: trial.sh ${1:-nap} START" >> "$LOGF"
# NOTE the st=$? FIRST: $(date) inside the echo resets $?, so the old trap logged
# EXIT 0 on crashed runs — three starved nights (07-22..24) hid behind that zero.
# THE SHELL-LEVEL CRASH NET (audit 2026-09-02): run_guarded only wraps main() —
# an import-time crash, a venv/pull failure or a signal dies BEFORE it and the
# only trace was this log. Now any non-zero exit mails the master one line
# (best-effort; mail failure never masks the exit code).
_crash_mail() {
  "${PY:-venv/bin/python}" - "$1" "$2" <<'PYEOF' 2>/dev/null || true
import sys
from racing_edge.report.mail import send, configured
task, st = sys.argv[1], sys.argv[2]
if configured():
    send(f"⚠ trial.sh {task} EXIT {st} — needs a look",
         f"trial.sh {task} exited {st} on the box. Full story: "
         "tail -120 data/task_runs.log (grep 'trial.sh' for the run's section).")
PYEOF
}
trap 'st=$?; { echo "=== $(date -u "+%F %T") UTC :: trial.sh '"${1:-nap}"' EXIT $st" >> "$LOGF"; } || true; if [ "$st" != "0" ]; then PYTHONPATH=src _crash_mail "'"${1:-nap}"'" "$st"; fi' EXIT
exec > >(tee -a "$LOGF") 2>&1

export PYTHONPATH=src
PY="venv/bin/python"
# SDK_OFF = "make NO model calls for this task" — a COST/SCOPE switch, nothing else.
# (2026-07-25 reliability audit: the old comment claimed an SDK/httpx clash; the SDK
# was deleted long ago — everything uses the direct-HTTP reasoner. DO NOT "fix" the
# nap or learn cases by adding this prefix: nap MUST keep the key for the morning
# deep read, learn MUST keep it for the night study. Blanking either would silently
# lobotomise the scheduled runs while manual runs kept working.)
SDK_OFF=(env ANTHROPIC_API_KEY=)

# ONE BRAIN (PR #56, 2026-08-18, the master: 'is the system fixed now one
# brain, one goal') — the trial lives on main. Override with TRIAL_BRANCH=...
BRANCH="${TRIAL_BRANCH:-main}"
# the school ladder's champion policy: the engine's own whole-card reading
export SCHOOL_CHAMPION="${SCHOOL_CHAMPION:-engine}"
echo ">> updating to the latest trial branch ($BRANCH)..."
# BEST-EFFORT update (2026-07-21): under set -e a git/network hiccup at 08:30 killed
# the entire run before it banked anything. Stale code running beats no run.
if ! ( git fetch origin --quiet \
       && ( git checkout "$BRANCH" --quiet 2>/dev/null \
            || git checkout -b "$BRANCH" "origin/$BRANCH" ) \
       && git pull origin "$BRANCH" --quiet ); then
  echo ">> WARNING: git update failed — running with the code already on disk"
fi
echo

case "${1:-nap}" in
  nap)     "$PY" -m racing_edge.cli.nap     --day today --both --email ;;   # keeps the key: the DEEP READ needs it (SDK-free)
  dissect) "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.dissect --day today        --email ;;
  settle)  "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.nap     --settle today      --email ;;
  restudy) "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.restudy --day today ${RESTUDY_TIME:+--time "$RESTUDY_TIME"} --email ;;
  learn)   "$PY" -m racing_edge.cli.learn   --day today ${LEARN_TIME:+--time "$LEARN_TIME"} --email ;;
  synth)   "$PY" -m racing_edge.cli.learn   --synthesise --email ;;
  guard)   "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.nap --guard ;;
  health)  "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.health --email ;;
  night)   # settle is best-effort: a settle crash must never cancel the self-study
           # (07-22..24: one NameError in settle starved the nuance ledger 3 nights)
           if ! "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.nap --settle today --email; then
             echo "WARNING: settle FAILED — continuing to the self-study regardless"
             PYTHONPATH=src _crash_mail "night:settle" 1   # a swallowed failure still mails (bot C)
           fi
           echo
           "$PY" -m racing_edge.cli.learn   --day today --email
           # THE NIGHT SCHOOL (2026-08-18, the master: 'study the form of every
           # race each day, then look at the winners in the evening, this is
           # the test'): grow the corpus with today's results (free on the API
           # sub), grade every policy on every race, ladder verdict for health.
           # Best-effort: a school crash must never cancel the self-study chain.
           if ! "${SDK_OFF[@]}" "$PY" -m racing_edge.school.night --day "$(date +%F)" --champion "$SCHOOL_CHAMPION"; then
             echo "WARNING: night school FAILED — the grind misses a day, nothing else"
             PYTHONPATH=src _crash_mail "night:school" 1   # a swallowed failure still mails (bot C)
           fi
           # TIER-0 (audit 2026-09-02, the master: 'learn from every race, every
           # placing'): every runner in every resulted race v the market, yesterday
           # beside the trailing 14 days. Free, scripted, best-effort.
           if ! "${SDK_OFF[@]}" "$PY" -m racing_edge.school.tier0 --day "$(date +%F)"; then
             echo "WARNING: tier-0 pass FAILED — health goes red on a stale report"
             PYTHONPATH=src _crash_mail "night:tier0" 1   # a swallowed failure still mails (bot C)
           fi
           # Sunday: the weekly synthesis rides in the same slot (no weekly task needed)
           if [ "$(date +%u)" = "7" ]; then echo; "$PY" -m racing_edge.cli.learn --synthesise --email; fi ;;
  all)     "$PY" -m racing_edge.cli.nap     --day today --both --email
           echo
           "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.dissect --day today         --email ;;
  read)    # ON-DEMAND READ (2026-07-25): ./trial.sh read "Salisbury 7:15" prints the
           # full pre-race form readout for one race — paste it to the reader in chat
           "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.brief --race "${2:?usage: ./trial.sh read \"Course H:MM\"}" ;;
  *) echo "usage: ./trial.sh [nap|dissect|settle|restudy|learn|synth|night|guard|health|read|all]"; exit 1 ;;
esac
