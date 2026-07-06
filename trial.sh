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

export PYTHONPATH=src
PY="venv/bin/python"
# The SDK/httpx clash only bites the paths that import the anthropic SDK (nap/dissect/
# settle's optional narrative). Blank the key for THOSE with this prefix — but NOT for
# `learn`, which uses the SDK-free direct-HTTP reasoner and NEEDS the real key (from .env
# or the task env) to think. `env ANTHROPIC_API_KEY=` blanks it for one command only.
SDK_OFF=(env ANTHROPIC_API_KEY=)

echo ">> updating to the latest trial branch (claude/form-trial)..."
git fetch origin --quiet
git checkout claude/form-trial --quiet 2>/dev/null \
  || git checkout -b claude/form-trial origin/claude/form-trial
git pull origin claude/form-trial --quiet
echo

case "${1:-nap}" in
  nap)     "$PY" -m racing_edge.cli.nap     --day today --both --email ;;   # keeps the key: the DEEP READ needs it (SDK-free)
  dissect) "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.dissect --day today        --email ;;
  settle)  "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.nap     --settle today      --email ;;
  restudy) "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.restudy --day today ${RESTUDY_TIME:+--time "$RESTUDY_TIME"} --email ;;
  learn)   "$PY" -m racing_edge.cli.learn   --day today ${LEARN_TIME:+--time "$LEARN_TIME"} --email ;;
  synth)   "$PY" -m racing_edge.cli.learn   --synthesise --email ;;
  guard)   "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.nap --guard ;;
  night)   "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.nap --settle today --email
           echo
           "$PY" -m racing_edge.cli.learn   --day today --email ;;
  all)     "$PY" -m racing_edge.cli.nap     --day today --both --email
           echo
           "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.dissect --day today         --email ;;
  *) echo "usage: ./trial.sh [nap|dissect|settle|restudy|learn|synth|night|all]"; exit 1 ;;
esac
