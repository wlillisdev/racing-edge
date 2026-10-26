#!/usr/bin/env bash
# THE BOX ON CLAUDE (his word, 2026-10-26: "move this all on claude ... i want
# to get rid of pythony anywhere ... get rid of api" -> "Yes, build it").
#
# Each Claude routine starts in a fresh container with a fresh clone of main,
# so the day's files cannot live on disk between the 07:30, 12:30 and 22:00
# runs. They live on the git branch `box-state`: every run restores them,
# runs one step of the frozen method on FREE Betfair data, and saves them back.
# main stays code-only.
#
#   bash box.sh nap     07:30 — the list (every favourite 4/5+), recorded
#   bash box.sh guard   12:30 — 2/1+ drifters dropped, the nap named and banked
#   bash box.sh night   22:00 — settle at Betfair SP, export the record
#
# Needs BETFAIR_USERNAME, BETFAIR_PASSWORD, BETFAIR_APP_KEY (in the environment
# or a .env file beside this script). Betfair blocks connections from outside
# the UK and Ireland — Claude's cloud included (403, 26 Oct) — so it runs on
# his own PC (his word, 2026-10-26: "My own PC, free"), from Windows Task
# Scheduler through Git Bash. EMAIL_* in .env turns the mails on.
set -u
STEP="${1:-nap}"
cd "$(dirname "$0")"
export PYTHONPATH=src DATA_SOURCE=betfair ANTHROPIC_API_KEY=
# the interpreter: python3 on Linux, python or py on Windows (Git Bash)
if [ -z "${PY:-}" ]; then
  for c in python3 python py; do
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
fi
PY="${PY:-python3}"
STATE=box-state
FILES="data/nap.db data/filter_record.csv data/record.csv docs/THE_RECORD.md data/market_snapshots"

"$PY" -m pip install -q -r requirements.txt >/dev/null 2>&1 || true

# on a home PC the logins live in .env beside this script (Betfair, and
# EMAIL_* for the mails); a Claude environment passes them in directly
if [ -f .env ]; then
  eval "$("$PY" -c 'import shlex; from dotenv import dotenv_values
for k, v in dotenv_values(".env").items():
    if v: print("export " + k + "=" + shlex.quote(v))')"
fi
UKDAY="$("$PY" -c 'from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo("Europe/London")).date())')"

echo ">> restoring the day's files from $STATE"
if git fetch -q origin "$STATE" 2>/dev/null; then
  for f in $FILES; do git checkout "origin/$STATE" -- "$f" 2>/dev/null || true; done
  git reset -q 2>/dev/null || true          # keep them out of main's index
else
  echo ">> no $STATE branch yet — first run starts the record fresh"
fi

rc=0
case "$STEP" in
  nap)   "$PY" -m racing_edge.school.favfilter --day today --bank --email || rc=$? ;;
  guard) "$PY" -m racing_edge.cli.nap --guard || rc=$? ;;
  night) "$PY" -m racing_edge.cli.nap --settle today --email || rc=$?
         "$PY" -m racing_edge.school.favfilter --settle "$UKDAY" || rc=$?
         "$PY" -m racing_edge.school.record_export || true ;;
  *)     echo "unknown step: $STEP"; exit 2 ;;
esac

echo ">> saving the day's files to $STATE"
W="$(mktemp -d)"
if git rev-parse -q --verify "origin/$STATE" >/dev/null; then
  git worktree add -q --detach "$W" "origin/$STATE"
else
  git worktree add -q --detach "$W" HEAD
  git -C "$W" checkout -q --orphan "$STATE"
  git -C "$W" rm -rq --cached . && find "$W" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
fi
for f in $FILES; do
  if [ -e "$f" ]; then mkdir -p "$W/$(dirname "$f")"; rm -rf "$W/$f"; cp -R "$f" "$W/$f"; fi
done
git -C "$W" add -f -A
if ! git -C "$W" diff --cached --quiet; then
  git -C "$W" -c user.name="racing-edge box" -c user.email="box@racing-edge" \
    commit -q -m "box: $STEP $UKDAY $(date -u '+%H:%M') UTC"
fi
pushed=1
for i in 1 2 3 4; do
  if git -C "$W" push -q origin "HEAD:refs/heads/$STATE"; then pushed=0; break; fi
  sleep $((2 ** i))
done
git worktree remove --force "$W" 2>/dev/null || true
[ "$pushed" = 0 ] || { echo "!! PUSH TO $STATE FAILED — the day's files are not saved"; exit 1; }
echo ">> saved"
exit "$rc"
