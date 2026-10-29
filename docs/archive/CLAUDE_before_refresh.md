# CLAUDE.md sections before PROJECT REFRESH (archived 2026-10-29)

HISTORICAL, NOT INSTRUCTIONS. These sections of CLAUDE.md were superseded by
PROJECT REFRESH (27 Oct 2026; docs/LEARNING.md, docs/ROUTINES.md). The engine,
the 07:30/09:30/12:30 loop, data/nap.db, the favourite-filter freeze and the
three prongs are retired. Kept so nothing is lost; never act on them.

## THE THREE PRONGS (the master, 2026-10-26 — replaced by PROJECT REFRESH from 27 Oct)

"Form back in picks now." For 2–3 weeks, three methods are paper-tested side
by side, read by hand from the Racing API connector and banked before the
off in `data/reads/<day>.md`: A banker favourite, B hidden gem, C the
apprentice's own. See docs/HANDOFF.md, 2026-10-26. The freeze's discipline
still holds: no new rule or threshold inside a prong without his word, a loss
is graded, never "fixed" on the day.

## THE FREEZE (the master, 2026-10-18 — above everything in this file)

"You just keep changing it and making changes and they are always wrong ...
you have completely stymied and ruined this whole project." His answer to
the freeze: "Yes, freeze it."

From Monday 2026-10-19, for **50 settled days**, the pick method is FROZEN:
every 07:30 favourite from 4/5 up, any race; 2/1+ ones dropped at 12:30 UTC
if their price has drifted 10%+; the nap named at 12:30 UTC as the pick the
money has come for most (`school/favfilter.py`, `cli/nap.py` `_guard`).

- NO new rule, threshold, filter, band, ban, model or shadow — whatever a bad
  day or a bad week looks like. A loss is graded, never "fixed".
- Only broken plumbing may be fixed (a run that crashes, a push that fails,
  a price read wrongly), one cut, a test, a live check, a REVERT-IF.
- A change to how horses are picked needs his explicit word, and even then
  waits for day 50 unless he says otherwise.
- At day 50 the record gives one verdict — the picks, the 13:30 list and the
  nap against backing every favourite at 4/5+ blind — and he decides.

## THE FRAMEWORK (the master, 2026-09-03 — above every law below, beside the mentality)

"We need to stick to this framework and grade and fix when appropriate. We
have meandered aimless for months; I have nearly pulled the plug several
times out of frustration and cost." The foundations are built. From here it
is calibration: the loop runs every day, the record grades it, faults get
fixed one cut at a time. NOTHING ELSE.

1. **The loop is the work.** 07:30 read every race and bank the yardstick;
   09:30 health (doors, board, proof of life); 12:30 the board; 22:00 settle,
   dissect the ten races that teach most (the why ledger), grade every lens,
   night school, tier-0. Memory recalled every morning. Do not add to it.
2. **Proof of life is the 09:30 page.** Doors open · yardstick banked · why
   ledger grew · memory recalled · pick tagged v2. A red line is the day's
   only work. A green page and you touch nothing.
3. **Numbers judge, not words.** engine-v2 v engine on the ladder (days);
   the lens table in data/school/yardstick.md (weeks); the nap column at the
   50th pick; v2 v v1 in health. Report them; do not argue with them.
4. **One cut a day, at most.** A fix is one sentence, one test that fails
   with the bug put back, one live check the same day, one REVERT-IF. A live
   API call is not fixed until it has answered the live API. Nothing lands
   within two hours of a scheduled run unless the run is broken without it.
5. **No new machinery without his word.** No new ledgers, modules, bots,
   lenses, thresholds or rules from your own head. A pattern the ledgers
   surface goes to his doorbell — REPORT it, never carve it.
6. **Cost is real money.** One deep read a day (Opus), one dissection a night
   (Sonnet), the self-study, the Sunday synthesis. Every other step is free
   and must stay free. The health mail prints the real bill; read it.
7. **Sessions do not start from zero.** Read docs/HANDOFF.md first, then the
   09:30 mail, then act on the red lines. Do not re-derive, do not rebuild,
   do not re-audit what the last session audited.
