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
# nap case by adding this prefix: nap MUST keep the key for the morning deep read.
# The learn/why/synth steps no longer run in `night` by default — see the night
# case — so the nightly bill is now the 07:30 deep read and nothing else.)
SDK_OFF=(env ANTHROPIC_API_KEY=)

# ONE BRAIN (PR #56, 2026-08-18, the master: 'is the system fixed now one
# brain, one goal') — the trial lives on main. Override with TRIAL_BRANCH=...
BRANCH="${TRIAL_BRANCH:-main}"
# the school ladder's champion: THE NAP COLUMN (the master, 2026-09-02: "best
# horse wins; we read the form; we pick winners — that is what we measure")
export SCHOOL_CHAMPION="${SCHOOL_CHAMPION:-nap}"
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
  nap)     "$PY" -m racing_edge.cli.nap     --day today --both --email       # keeps the key: the DEEP READ needs it (SDK-free)
           # THE FAVOURITE FILTER (taught 2026-09-20, his words: "look at all
           # the favourites every day, rule out the bad ones and dial in the
           # ones that are left"). Runs AFTER the engine so it can never delay
           # or break the bank, and best-effort so a bad morning for it is a
           # missing list, never a missing pick. Paper, graded nightly.
           echo
           "${SDK_OFF[@]}" "$PY" -m racing_edge.school.favfilter --day today || true ;;
  dissect) "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.dissect --day today        --email ;;
  # THE RECORD, MADE READABLE (audit 2026-09-20). Law 1 says nap.db is the
  # record, and .gitignore correctly keeps it off the repo — so the session
  # that grades the work could not read the thing that judges it, and every
  # strike rate quoted came from a summary or from memory. The settle now
  # exports OUR OWN picks and their SPs (never a card, never a runner we did
  # not back) to data/record.csv + docs/THE_RECORD.md. Derived and rewritten
  # each run: nap.db stays the source of truth, this is only a readable copy.
  # It runs AFTER the settle so it sees tonight's result, and `|| true` keeps
  # a broken export from ever failing the settle that matters.
  settle)  "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.nap     --settle today      --email
           "${SDK_OFF[@]}" "$PY" -m racing_edge.school.record_export || true ;;
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
           # THE HINDSIGHT STEPS ARE OFF (his word, 2026-09-21: "learning loop
           # needs also to change as i feel its just wasteing credits and
           # acheiving nothing"). He is right, and the record says so.
           #
           # self-study (cli.learn) and the why ledger (school.why) are the only
           # paid steps at night. Both read races AFTER the result is known and
           # write down why the winner won. On 2026-09-20 the lens that came out
           # of that synthesis -- "back the favourite whose last run says it
           # stayed on" -- was tested properly for the first time: +13.4% over
           # 414 bets on the half it was fitted to, -10.0% over 450 bets on the
           # half it had never seen. The lesson register they feed carried five
           # lessons at TESTING for a fortnight and not one reported.
           #
           # Every FREE step below is kept, because those are the ones that
           # MEASURE rather than narrate: the night school grades policies,
           # tier-0 scores every runner against the market, the yardstick scores
           # every lens, and the record export sends the strike rate upstream.
           #
           # TO TURN THEM BACK ON: LEARN=1 ./trial.sh night  (or set it in the
           # scheduled task). Nothing is deleted; this is a switch, not a burial.
           if [ "${LEARN:-0}" = "1" ]; then
             "$PY" -m racing_edge.cli.learn   --day today --email
             if ! "$PY" -m racing_edge.school.why --day "$(date +%F)"; then
               echo "WARNING: why ledger FAILED — the card goes unlearned tonight"
               PYTHONPATH=src _crash_mail "night:why" 1
             fi
           else
             echo "hindsight steps OFF (his word 2026-09-21) — LEARN=1 restores them"
           fi
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
           # THE YARDSTICK LEDGER (the master, 2026-09-03: "the stored races as
           # learning data... the calibration of the system"): every runner's
           # morning read, settled tonight, scored lens by lens against the market.
           if ! "${SDK_OFF[@]}" "$PY" -m racing_edge.school.yardstick --day "$(date +%F)"; then
             echo "WARNING: yardstick scoreboard FAILED — the ledger keeps banking; the board is stale"
             PYTHONPATH=src _crash_mail "night:yardstick" 1
           fi
           # THE RECORD, MADE READABLE (audit 2026-09-20) — LAST, so it sees
           # tonight's settle. It also has to be HERE and not only in the
           # `settle)` case: the box's 22:00 task is `night`, which runs its own
           # inline settle and never touches that case, so wiring the export
           # there alone would have meant it never ran on the box at all.
           if ! "${SDK_OFF[@]}" "$PY" -m racing_edge.school.record_export; then
             echo "WARNING: record export FAILED — the repo copy of the record is stale"
             PYTHONPATH=src _crash_mail "night:record_export" 1
           fi
           # AND SEND IT (2026-09-21, once the box got an SSH deploy key). The
           # export is worthless if it only ever lands here: law 1 says the
           # record judges everything, and until it is pushed it can be read
           # from nowhere but this machine.
           #
           # IT MUST FAIL LOUDLY (2026-09-22). The first version printed
           # "harmless" on every failure path and mailed nobody, so a full day
           # passed with an empty record and neither of us knew until he asked
           # about a pick I could not see. A silent non-push is the exact fault
           # the whole export exists to cure. Each case now says which it is,
           # and a real failure mails.
           _rec_push() {
             git add data/record.csv docs/THE_RECORD.md 2>/dev/null || {
               echo "RECORD: git add failed"; return 1; }
             if git diff --cached --quiet; then
               # not an error, but NOT silent: an unchanged record after a
               # settle means nap.db gave the export nothing, which is itself
               # worth knowing and is the likeliest reason it stays empty.
               echo "RECORD: nothing changed — the export found no rows in nap.db"
               return 2
             fi
             git -c user.name="racing-edge box" \
                 -c user.email="box@racing-edge.local" \
                 commit -q -m "record: $(date -u +%F) settle" || {
               echo "RECORD: commit failed"; return 1; }
             git pull --rebase -q origin main || {
               echo "RECORD: pull --rebase failed (diverged?)"; return 1; }
             git push -q origin main || {
               echo "RECORD: PUSH REFUSED — check the deploy key has write access"
               return 1; }
             echo "record pushed to main"
             return 0
           }
           _rec_push; _rc=$?
           if [ "$_rc" = "1" ]; then
             PYTHONPATH=src _crash_mail "night:record_push" 1
           elif [ "$_rc" = "2" ]; then
             PYTHONPATH=src _crash_mail "night:record_EMPTY" 2
           fi
           # Sunday: the weekly synthesis rode in this slot. It is the third and
           # last paid hindsight step and it is off with the other two — it is
           # the step that actually produced the reversing lens. Same switch.
           if [ "$(date +%u)" = "7" ] && [ "${LEARN:-0}" = "1" ]; then
             echo; "$PY" -m racing_edge.cli.learn --synthesise --email
           fi ;;
  all)     "$PY" -m racing_edge.cli.nap     --day today --both --email
           echo
           "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.dissect --day today         --email ;;
  doors)   # THE LIVE DOOR CHECK (2026-09-03, after the 22:00 crash a fake-client
           # suite could not see): every API door the tasks use, opened once for real.
           # Run it after ANY merge that touches data/client.py — before the next task.
           "${SDK_OFF[@]}" "$PY" -m racing_edge.data.doors ;;
  read)    # ON-DEMAND READ (2026-07-25): ./trial.sh read "Salisbury 7:15" prints the
           # full pre-race form readout for one race — paste it to the reader in chat
           "${SDK_OFF[@]}" "$PY" -m racing_edge.cli.brief --race "${2:?usage: ./trial.sh read \"Course H:MM\"}" ;;
  *) echo "usage: ./trial.sh [nap|dissect|settle|restudy|learn|synth|night|guard|health|doors|read|all]"; exit 1 ;;
esac
