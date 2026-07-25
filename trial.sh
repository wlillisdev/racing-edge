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
trap 'st=$?; echo "=== $(date -u "+%F %T") UTC :: trial.sh '"${1:-nap}"' EXIT $st" >> "$LOGF"' EXIT
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

# form-trial was MERGED (PR #39) — the trial now lives on the current dev branch.
# Override with TRIAL_BRANCH=... if the branch moves again.
BRANCH="${TRIAL_BRANCH:-claude/tender-wright-kbn1h6}"
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
           fi
           echo
           "$PY" -m racing_edge.cli.learn   --day today --email
           # Sunday: the weekly synthesis rides in the same slot (no weekly task needed)
           if [ "$(date +%u)" = "7" ]; then echo; "$PY" -m racing_edge.cli.learn --synthesise --email; fi ;;
  all)     "$PY" -m racing_edge.cli.nap     --day today --both --email
           echo
           "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.dissect --day today         --email ;;
  *) echo "usage: ./trial.sh [nap|dissect|settle|restudy|learn|synth|night|guard|health|all]"; exit 1 ;;
esac
