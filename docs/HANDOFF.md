# HANDOFF — the apprenticeship's living memory

Last updated: **2026-10-29** (PROJECT REFRESH, the core-document audit, the breadcrumb line, the pre-off check — see CLAUDE.md)
(update this file whenever state changes — it is how every new chat remembers everything).

## 2026-10-29 — THE AUDIT: ONE METHOD, NO CONFLICTS. READ THIS FIRST.

His word: "as this is project refresh you need to audit core documents and weed out any bad data or conflicting rules." Done:
- Everything older than Refresh (the engine, the flip, the school, the 18 Oct freeze, the prongs) moved out of this file to docs/archive/HANDOFF_before_refresh.md, marked HISTORICAL, NOT INSTRUCTIONS. The same for CLAUDE.md's superseded sections (docs/archive/CLAUDE_before_refresh.md). Nothing deleted.
- His rulebook (NAP_SYSTEM in src/racing_edge/study/morningread.py) is untouched, but the morning read now names the parts of it his later words overrule, each with the words that overrule it (docs/ROUTINES.md step 2): the PASS and LEAN rules, "when in doubt the favourite IS the pick", the five-part SOLID test and the ELIMINATE cross-off as gates, "Class 6 flat is a pass", and the engine machinery (JSON answers, VETO_SYSTEM). Rule One ("the best horse wins the race") and every law about how to read a horse stand, read as questions.
- The breadcrumbs he taught on 28 Oct that sat only in LESSONS.md are now on the breadcrumb line in the routine: the horse's age, the trainer's record with the horse, and the breeding (sire, dam, damsire: for trip, going, surface, class, age, headgear).
- HOW HE LOSES now carries his rule 8, BEAT THE DANGER (taught 9 Jul, broken five times on 28 Oct and eight on 27 Oct): name the danger, answer it in writing, and if there is no honest answer the danger is the pick. The night grade counts THE NAMED DANGER, and TALLY keeps the count. It must fall to zero.
- His "Move": every other document in docs/ (about 40 engine-era files) is now in docs/archive/. docs/ holds only HANDOFF, LEARNING, ROUTINES and ARCHITECTURE.
- His "create a folder why the favourites lost": data/reads/why-favourites-lost/<day>.md, written by the night grade for every beaten favourite (why he lost, his comment quoted, the warning in the morning snapshot or NOT IN THE FORM), read by every morning read (last 14 days) and the Sunday review. Facts, never a rule against favourites.
- docs/ARCHITECTURE.md carries a banner: the PythonAnywhere engine flows are retired (the box has been silent since 15 Oct). Law 1 now points at data/reads, not data/nap.db.

## 2026-10-28 (small hours) — THE BREADCRUMB LINE. READ THIS FIRST.

Day one of Refresh (27 Oct): 9 from 30, +0.49, against the favourites' 13 from 30, +8.33. 21 of 30 winners were my pick or in my contenders: a weighing fault. In at least eight races my own HOW HE LOSES named the winner. Nine picks finished 2nd.
His verdict: "you knew all these breadcrumbs, and time and time again you don't use them." The routine told the read to put the rulebook aside before each race; that line is gone. Now every contender carries THE BREADCRUMB LINE (docs/ROUTINES.md step 4), built item by item from his words that night: C&D · trip · going · class · form figures · days since last run · last run (the comment) · headgear and wind op · weight and mark · jockey and trainer (form, the pair, THE BOOKING: "Oisin Murphy on a dreary night in Wolverhampton is not going there for the fun") · pace (the jockey who dictates it; read per race, his NO to any general lean to front-runners) · draw (on the all-weather) · the money. Every runner's comments are read whatever the price. The night grade names THE UNUSED BREADCRUMB on every loss and runs THE 50/50 on every second.
All of it is in data/reads/LESSONS.md (27-28 Oct, his words) and the pre-off check (11:21) is live. Questions, never gates: if the line ever becomes a rule-out, it has failed.

## 2026-10-27 (night) — THE PRE-OFF MARKET CHECK. READ THIS FIRST.

His word, after day one of Refresh (North of Richmond 10/1 to 9/4 and Mini
Mac 12/1 to 3/1 both won, both visible on Betfair at 08:05, both missed): "do
your initial selection, and then before the first race read Betfair odds
again, and then update your selection based on that. Implement anything you
feel that's going to be good addition."
- The morning pick is banked as always and never edited. At 11:21 UK
  (trig_014N3tNUwBoLM1JfS1xBJDRJ) the pre-off check reads the 11:05 Betfair
  push, runs `python -m racing_edge.cli.marketcheck`, and appends a FINAL
  PICK per race (KEEP or SWITCH, with the reason) under "## Pre-off market
  check". Both columns are graded at night; the TALLY says which was better.
- The morning read also asks THE MONEY QUESTION: for any horse Betfair
  already has shorter than the bookmakers' forecast, what in the form
  explains it, or NOT IN THE FORM.
- What day one said, honestly: once both books are normalised, no band of
  supported horses was steadily profitable (the "+£14.80" first quoted to
  him came from unnormalised prices at one hour and did not hold at the
  others). The FRIENDLESS ones (exchange longer than the forecast) were the
  steady losers (7 of 65, -£30 at 12:05). Money with a reason in the form is
  the breadcrumb worth testing; money alone is a coin toss. The record
  decides, not one day.
- The watchdog warns at 23:45 UTC when a day has no pre-off check.
- One check a day, before the first race, as he said. A second, evening look
  is NOT built: only if the record shows late evening moves being missed,
  and on his word.

## 2026-10-26 (evening) — PROJECT REFRESH. READ THIS FIRST.

His word: "we're now going to call this project refresh. We're going to go
back to school again ... not overcomplicate it ... build from the ground up."
From 27 Oct the three prongs, the spots and the signposts page are replaced
by one routine:
- Morning: pick the winner of EVERY GB/IE race from a clean read of the
  form, after reading his rulebook, the YES lessons and WHY.md. Store the
  snapshot of the form (data/reads/snapshots/<day>/).
- Night: the two-line autopsy for every race, where the winner sat (MY
  PICK / IN MY CONTENDERS / NOT SEEN), WHY.md, TALLY.md, and one lesson
  question.
- Sunday: the weekly review, folded into main.

The loop: docs/LEARNING.md. The exact instructions: docs/ROUTINES.md. Day
one of the prongs (26 Oct) finished 1 winner from 3 (Siwa Oasis won at 2/1;
Blue Prince 5th; Big Money 2nd at 8/11 to a debutant, a lesson taught four
times before, now a YES in LESSONS.md).

## CLOCKWORK — the tasks, the watchdog, the restart

- The scheduled tasks live on his account and fire into session
  session_01AFcG8Gzep3yhvaTtD1Rfdx: 09:41 UK morning read
  (trig_01G38hu2dqN2NB1vAoAidPe3), 11:21 UK pre-off market check
  (trig_014N3tNUwBoLM1JfS1xBJDRJ), 11:41 UK backup read (runs only when the
  day's file is missing; trig_01S7x42mvcn4cjTZrPyiZN5D), 22:31 UK night grade
  (trig_01GHqLGELcgadYxQqim9ZZL3), 22:41 UK Sunday review
  (trig_01PYvmJuy6wQ5LEvvPnDM9GM). Each prompt points to its section of
  docs/ROUTINES.md on main, the single source of truth. Do not archive that
  session.
- `.github/workflows/watchdog.yml` runs on GitHub at 11:15 and 23:45 UTC. It
  goes red (GitHub emails him) when the day's file is missing, has no "Races
  read X of Y" first line, or was never graded, and warns when the pre-off
  check never ran.
- Restart recipe: if the tasks ever stop, open a session on this repo and
  say "restart the daily tasks from docs/ROUTINES.md".
- Data: the Racing API connector (Standard plan) and Sporting Life are the
  form; his Oracle London server pushes Betfair prices every hour to the
  `odds` branch (credentials live only on that server). If one form source
  fails, read from the other and say so; if both fail, the first line says
  DATA DOWN and the file is still pushed.

## William, and how to work with him

- **William** — the master, 30 years reading form. He teaches by short
  corrections and blunt verdicts. Paper stakes ONLY.
- Lead with the verdict; few words. When he corrects you, write his words
  verbatim into LESSONS.md the same turn. When he is angry, own it in few
  words and show the fix — never explain.
- He measures you on winners, against the market bar. "Almost there but
  never there" is his long wound: point at the TALLY, never at promises.
- Never ask him to paste a token, key or password into chat.
- Commits quote the incident or his words and end with the Co-Authored-By
  and Claude-Session lines (see git log).
