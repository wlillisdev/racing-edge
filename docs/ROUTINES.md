# ROUTINES — the daily scheduled tasks, word for word

His question, 26 Oct: "how are you going to make sure this one's like
clockwork? ... I'm not going to be here prompting you all day."

Each scheduled task on his account carries only a pointer: "read
docs/ROUTINES.md on origin/main and carry out section X". The sections below
ARE the instructions, so a change merged here changes tomorrow's run. Keep
them right; a broken section breaks the day. If the tasks ever stop (the
session they fire into was archived or lost), open a session on this repo
and say: **"restart the daily tasks from docs/ROUTINES.md"**. The session
recreates each task below with the schedule shown, bound to itself, with the
one-line pointer prompt, and updates the ids here and in docs/HANDOFF.md.

| Task | Schedule (UK time) | Id |
|---|---|---|
| Morning read | `CRON_TZ=Europe/London 41 9 * * *` | trig_01G38hu2dqN2NB1vAoAidPe3 |
| Backup morning read (only if missed) | `CRON_TZ=Europe/London 41 11 * * *` | trig_01S7x42mvcn4cjTZrPyiZN5D |
| Night grade | `CRON_TZ=Europe/London 30 21 * * *` | trig_01GHqLGELcgadYxQqim9ZZL3 |
| Sunday review | `CRON_TZ=Europe/London 41 22 * * 0` | trig_01PYvmJuy6wQ5LEvvPnDM9GM |

PROJECT REFRESH (his word, 26 Oct, from 27 Oct): pick the winner of every
race from a clean read of the form, store a snapshot of the form, and each
night compare the snapshot, the notes and the result. Why, and which files
the loop reads and writes: docs/LEARNING.md.

Outside the session, `.github/workflows/watchdog.yml` checks the `reads`
branch at 11:15 and 23:45 UTC and goes red (GitHub emails him) when a day is
missing or ungraded.

## Morning read

```
MORNING READ: PROJECT REFRESH (docs/LEARNING.md). Pick the winner of every GB/IE race from a clean read of the form. Paper only. Never touch code. Never write duty-*.csv.

1. Run `date -u`. Run `git fetch origin main reads`. If origin/reads exists, run `git checkout -B reads origin/reads` then `git merge --no-edit origin/main`; otherwise `git checkout -B reads origin/main`. If data/reads/<UK day>.md already exists, stop: the day is banked.
2. READ FIRST, in this order:
   - THE RULEBOOK: NAP_SYSTEM and VETO_SYSTEM in src/racing_edge/study/morningread.py, his base rules in his words;
   - data/reads/LESSONS.md: every YES lesson applies today;
   - data/reads/WHY.md, the last 14 days: why the winners won;
   - the "what I missed" lines of the last 7 graded days in data/reads/.
   Then put them aside and read each race CLEAN: the form decides, not yesterday's mood.
3. THE SNAPSHOT (his word: "take a snapshot of the form of that race, store it"). Before reading, save the form exactly as it stands, so tonight compares against the same facts:
   - The Racing API connector, get_racecards_standard (gb,ire). It returns 20 races a page: page with skip until the count equals "total". If an answer is saved to a file, copy that file. Save the full cards as data/reads/snapshots/<day>/racing_api.json.
   - Sporting Life: www.sportinglife.com/racing/racecards lists the day; each race page is /racing/racecards/<day>/<course>/racecard/<id>/x. Fetch every GB/IE race page with curl, one every 2 seconds. From each page's __NEXT_DATA__ JSON keep the race object: per ride the commentary, betting.current_odds, timeform_stars, official_rating, draw, and horse.previous_results with each run's ride_description. Save as data/reads/snapshots/<day>/sportinglife.json.
   - Cross-check: every GB/IE course on Sporting Life is in the Racing API cards. If one source fails, use the other and say so in the first line. If both fail, write "Races read 0 of ? — DATA DOWN: <what failed>", push, and stop.
4. FOR EVERY RACE, using the snapshot (and get_race_analysis with depth "full" or get_horse_racecard_results where the form needs more):
   - TYPE: handicap / novice-maiden / conditions / pattern; flat / AW / hurdle / chase; age band. READABLE or NOT, by the rulebook's race laws (1b, #13, #14, novice/maiden, the 3yo AW lesson). Every race still gets a pick; the label is what we learn from.
   - THE CONTENDERS: 3 or 4 serious ones, each with one line: "IF HE WINS, it will be because ...". Check each against the rulebook, the YES lessons and WHY.md.
   - THE PICK: the horse whose winning story needs the fewest unknowns. Write its price, and HOW HE WINS (where he sits, when he goes, who he beats and why).
   - HOW HE LOSES: the strongest honest case against the pick, as tomorrow's autopsy would write it.
   Keep it short: a race in five or six lines. Read the form, not the betting.
5. Bank only races whose off is at least 30 minutes after a fresh `date -u` taken at the moment you write. A race too close to the off is listed as MISSED, with no pick.
6. Write data/reads/<day>.md, and never edit an earlier day's file:
   - FIRST LINE: "Races read X of Y (courses: ...)", plus any fallback used. If X is less than Y, say why.
   - Then a table: time, course, pick, price, READABLE or NOT.
   - Then each race's notes as in step 4.
7. Commit ("reads: <day> morning", the notes and the snapshot together) and run `git push origin reads`, retrying up to 4 times with backoff. A push that never lands means the day is not banked: say so loudly.
8. Tell William in ONE short message: races read X of Y, then the picks, one per line (time, course, horse, price).
```

## Backup morning read (only if missed)

```
BACKUP MORNING READ. Run `git fetch origin reads`, then check whether data/reads/<today's UK date>.md exists on origin/reads (`git cat-file -e origin/reads:data/reads/<day>.md`). If it exists, the 09:41 read banked the day: do nothing and say nothing. If it is missing, the 09:41 morning read did not run. Run it now, following the "Morning read" section of docs/ROUTINES.md exactly, banking only races still 30 or more minutes from the off. End its first line ("Races read X of Y ...") with " — BACKUP READ at <UTC time>".
```

## Night grade

```
NIGHT GRADE: PROJECT REFRESH (docs/LEARNING.md). There is no deadline: if you resume hours late, finish the work anyway. Never touch code. Never write duty-*.csv.

1. Run `date -u`. Run `git fetch origin main reads`, then `git checkout -B reads origin/reads` and `git merge --no-edit origin/main`. Today's notes are data/reads/<UK day>.md; the snapshot is data/reads/snapshots/<day>/. Read docs/LEARNING.md.
2. RESULTS for every race:
   - Sporting Life: www.sportinglife.com/racing/results lists the day; each result page is /racing/results/<day>/<course>/<id>/x. Its __NEXT_DATA__ JSON gives per ride finish_position, ride_description (the in-running comment), the SP and betting.historical_odds;
   - The Racing API connector (get_results_today, or get_result_by_id) as the cross-check.
   Fetch with curl and parse with python. Save the results beside the snapshot as data/reads/snapshots/<day>/results.json.
3. THE COMPARISON, for every race. Lay the morning snapshot, the morning notes and the result side by side. Append to today's file a "## Graded" section, never altering what was banked. For each race:
   - WON or LOST, with the pick's SP and position; the winner, SP and margin;
   - the pick's in-running comment, and the winner's;
   - THE TWO-LINE AUTOPSY (his word: "with two lines you summed up the whole race"): line 1, why the winner won, with the fact in the morning snapshot that showed it; line 2, what I got right, wrong or missed in the morning notes;
   - WHERE THE WINNER SAT in the morning notes: MY PICK, IN MY CONTENDERS, or NOT SEEN.
4. data/reads/WHY.md: one line per race the pick lost, plus any race that teaches: date, race, winner, SP, why he won (in-running comment quoted), and a short reason type (examples, not a closed list: improver from a top yard; unexposed newcomer; class dropper; well-handicapped off a lower mark; trouble last time; pace and draw; course specialist).
5. data/reads/TALLY.md, running totals:
   - races picked, winners, strike rate, and £1 level-stakes profit or loss at SP, for the day and in total;
   - the same split by READABLE or NOT, and by race type (handicap, novice-maiden, conditions-pattern; flat, AW, hurdle, chase);
   - the foresight check: MY PICK / IN MY CONTENDERS / NOT SEEN. A high IN MY CONTENDERS count means I read the race but weighed it wrong; a high NOT SEEN count means I did not read it. Say which it is.
6. data/reads/NOTEBOOK.md: any horse whose in-running comment shows a run better than its finishing position (trouble, slowly away, short of room, hampered, finishing fast off an unsuitable pace), one line each with the comment quoted. These are facts, not rules.
7. LESSONS: append at most ONE lesson to data/reads/LESSONS.md, as `## <day> — ASKED`: the incident quoted, what I missed, and the lesson as a yes/no question to William. Never re-ask a NO; never ask what a YES already covers. Never carve a rule.
8. Commit ("reads: <day> graded") and run `git push origin reads`, retrying up to 4 times with backoff.
9. Tell William in ONE short message: winners X from Y races, strike rate and £1 P&L today and in total, READABLE v NOT strike rates, the foresight split, and tonight's lesson question (answer yes or no).
```

## Sunday review

```
SUNDAY REVIEW: PROJECT REFRESH, the weekly step (docs/LEARNING.md). There is no deadline. Never touch code. Never carve a rule.

1. Run `date -u`. Run `git fetch origin main reads`, then `git checkout -B reads origin/reads` and `git merge --no-edit origin/main`. Read docs/LEARNING.md.
2. Read this week's data/reads/<day>.md files (Monday to Sunday), TALLY.md, WHY.md, LESSONS.md and NOTEBOOK.md.
3. Append `## Week ending <day>` to data/reads/WEEKLY.md:
   - strike rate and £1 P&L for the week and in total, split by READABLE or NOT and by race type: where the reading works and where it does not;
   - the foresight check for the week, and what it says (weighing fault or reading fault);
   - the winning reasons from WHY.md that recurred, with counts, especially the ones that beat my picks;
   - the "what I missed" lines grouped where the same mistake repeats;
   - 2 or 3 questions for William, each answerable yes or no;
   - lessons still ASKED and awaiting his word.
4. Commit ("reads: week ending <day>") and run `git push origin reads`, retrying up to 4 times with backoff.
5. Fold the learning into the project: open a pull request from `reads` into `main` titled "Learning: week ending <day>" (data/reads only). Merge it once the tests are green. If they are red, say why and leave it open.
6. Tell William in ONE short message: the week's strike rate and P&L, where the reading works and where it does not, the top recurring winning reason, and the 2 or 3 questions.
```
