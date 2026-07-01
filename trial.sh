#!/usr/bin/env bash
#
# racing-edge — FORM TRIAL runner (PythonAnywhere)
#
#   ./trial.sh nap       MORNING: nominate + BANK today's pick (the new rules on real data)
#   ./trial.sh dissect   read the whole card's REAL market moves (backed/drifted)
#   ./trial.sh settle    AFTER RACING: settle the banked pick, update the strike rate
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
export ANTHROPIC_API_KEY=""      # skip the optional AI narrative (the SDK/httpx clash workaround)
PY="venv/bin/python"

echo ">> updating to the latest trial branch (claude/form-trial)..."
git fetch origin --quiet
git checkout claude/form-trial --quiet 2>/dev/null \
  || git checkout -b claude/form-trial origin/claude/form-trial
git pull origin claude/form-trial --quiet
echo

case "${1:-nap}" in
  nap)     "$PY" -m racing_edge.cli.nap     --day today --both --email ;;
  dissect) "$PY" -m racing_edge.cli.dissect --day today        --email ;;
  settle)  "$PY" -m racing_edge.cli.nap     --settle today      --email ;;
  all)     "$PY" -m racing_edge.cli.nap     --day today --both --email
           echo
           "$PY" -m racing_edge.cli.dissect --day today         --email ;;
  *) echo "usage: ./trial.sh [nap|dissect|settle|all]"; exit 1 ;;
esac
