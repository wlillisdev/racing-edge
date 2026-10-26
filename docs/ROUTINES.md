# ROUTINES — the daily scheduled tasks, word for word

His question, 26 Oct: "how are you going to make sure this one's like
clockwork? ... I'm not going to be here prompting you all day."

Each scheduled task on his account carries only a pointer: "read
docs/ROUTINES.md on origin/main and carry out section X". The sections below
ARE the instructions, so a change merged here changes tomorrow's run. Keep
them right; a broken section breaks the day. If the
tasks ever stop (the session they fire into was archived or lost), open a
session on this repo and say: **"restart the daily tasks from
docs/ROUTINES.md"**. The session recreates each task below with the schedule
shown, bound to itself, with the one-line pointer prompt, and updates the
ids here and in docs/HANDOFF.md. When a prompt
changes, change it here in the same breath.

| Task | Schedule (UK time) | Id (26 Oct) |
|---|---|---|
| Morning read: three prongs | `CRON_TZ=Europe/London 41 9 * * *` | trig_01G38hu2dqN2NB1vAoAidPe3 |
| Backup morning read (only if missed) | `CRON_TZ=Europe/London 41 11 * * *` | trig_01S7x42mvcn4cjTZrPyiZN5D |
| Night grade: three prongs | `CRON_TZ=Europe/London 30 21 * * *` | trig_01GHqLGELcgadYxQqim9ZZL3 |
| Sunday review | `CRON_TZ=Europe/London 41 22 * * 0` | trig_01PYvmJuy6wQ5LEvvPnDM9GM |

How the loop learns, and which files it reads and writes: docs/LEARNING.md.

Outside the session, `.github/workflows/watchdog.yml` checks the `reads`
branch at 11:15 and 23:45 UTC and goes red (GitHub emails him) when a day is
missing or ungraded.

## Morning read: three prongs

```
MORNING READ: William's three-prong paper test (docs/HANDOFF.md, 2026-10-26). Paper stakes only. Never touch code. Never write duty-*.csv.

1. Run `date -u`. Run `git fetch origin main reads`. If origin/reads exists, run `git checkout -B reads origin/reads` then `git merge --no-edit origin/main` (to pick up the latest docs); otherwise `git checkout -B reads origin/main`. If data/reads/<UK day>.md already exists there, stop: the day is banked.
   Then read, in this order (docs/LEARNING.md explains why):
   - the 2026-10-26 section of docs/HANDOFF.md, including the missed-races SCAR;
   - data/reads/LESSONS.md: every YES lesson joins today's checklist;
   - the "my error" lines of the last 7 graded days in data/reads/;
   - data/reads/NOTEBOOK.md;
   - the latest week in data/reads/WEEKLY.md.
2. Data comes from two sources only:
   - The Racing API connector:
     - get_racecards_standard (gb,ire). It returns 20 races a page: page with skip until the count equals "total". Cross-check the course list against the Sporting Life racecards page; every GB/IE course must be present. If an answer is saved to a file, read it with jq or python;
     - get_race_analysis with depth "full" on shortlisted races;
     - get_horse_racecard_results for the past-run comments of serious contenders;
     - get_jockey_course_analysis with start_date 14 days ago, for the jockeys of shortlisted horses only.
   - Sporting Life race pages, as the supplement:
     - www.sportinglife.com/racing/racecards lists the day; each race page is /racing/racecards/<day>/<course>/racecard/<id>/x;
     - the __NEXT_DATA__ JSON in each page gives per ride: the commentary, betting.current_odds, timeform_stars, and horse.previous_results, each past run with its ride_description (the in-running comment);
     - Fetch with curl and parse with python; one page per shortlisted race, no more.
   FALLBACKS:
   - If the Racing API plan has dropped below Standard, use what it gives plus Sporting Life.
   - If the Racing API fails outright, read from Sporting Life alone (it has every card, comment and price).
   - If both fail, write the first line as "Races read 0 of ? — DATA DOWN: <what failed>", push the file, and stop.
   Say in the first line which fallback was used.
3. THE SIGNPOSTS PAGE (his gg.co.uk list, 26 Oct). Build it from the day's full card with python, listing facts only, no thresholds of your own:
   - Hot trainers: the 5 trainers with runners today with the best last-14-days win %, listing their runners;
   - C&D winners: runners with the CD flag;
   - First time: headgear_run "1" with the headgear code, and wind ops as wind_surgery with its wind_surgery_run;
   - Longest travellers: from trainer_location against the course, for shortlisted horses, with miles estimated;
   - Hot jockeys: the 14-day record for the jockeys of shortlisted horses.
   (First time gelded is not in the API: leave it out rather than guess.)
4. Read EVERY GB/IE race, and every favourite, using ONLY the fixed checklist. Invent no rule or threshold (his warning: "you have too much information ... you end up making up rules yourself").
   - His five-part solid test: short price; in form (consistently placing over five runs and improving, e.g. 5423); has actually won; race-fit (60 days or less unless a class horse from a big yard); proven at today's mark (has won off it or higher).
   - The comments, line by line: trouble, slow start, draw, pace, manner, genuine excuses.
   - Pound-a-length against rivals met before (1 length = 1lb).
   - Class up or down; ground, trip and course proven.
   - Signposts as facts: the signposts page, plus RPR, Topspeed, Timeform stars, a new yard, and a runner in the NOTEBOOK (quote its note).
   - Every YES lesson in LESSONS.md, quoted where it bites.
5. EXACTLY ONE pick per prong, every day. NO BET is not allowed. His word: "you're going to pick a horse ... be accountable for why you picked that horse."
   - A. Banker favourite: the favourite that best passes the five parts, with no excuse made for him and no rival the weights favour. If none passes all five, pick the best one anyway and write down which parts he fails.
   - B. Hidden gem: the best horse that isn't the favourite, at 4/1 or bigger, whose form stacks up to win.
   - C. Form plus money: the form passes (has won, race-fit, within 3lb of a winning mark, no unexplained bad run) and his best price now is shorter than the card's betting forecast; price 6/4 to 8/1. If none fits fully, pick the closest and write down which part is missing.
6. Bank only races whose off is at least 30 minutes after a fresh `date -u` taken at the moment you write. Write data/reads/<day>.md, and never edit an earlier day's file.
   - FIRST LINE: "Races read X of Y (courses: ...)", plus any fallback used. If X is less than Y, say why.
   - Each prong's pick: race, horse, price, banked UTC time, the why in three lines, the danger, and HOW HE WINS: one line on the race shape the form says he gets (where he sits, when he goes, which rival he beats and why).
     Also THE GAP: how clear he is over the next best on the form, as CLEAR, NARROW or COIN-FLIP, naming the next best. This is a measurement, not a filter: every prong still picks.
   - The signposts page.
   - A table of every favourite: SOLID or NOT SOLID, with a one-line why.
7. Commit ("reads: <day> morning") and run `git push origin reads`, retrying up to 4 times with backoff. A push that never lands means the day is not banked: say so loudly.
8. Tell William in ONE short message: races read X of Y, then each prong's pick with price and off time.
```

## Backup morning read (only if missed)

```
BACKUP MORNING READ. Run `git fetch origin reads`, then check whether data/reads/<today's UK date>.md exists on origin/reads (`git cat-file -e origin/reads:data/reads/<day>.md`). If it exists, the 09:41 read banked the day: do nothing and say nothing. If it is missing, the 09:41 morning read did not run. Run it now, following the morning read's instructions in docs/ROUTINES.md exactly, banking only races still 30 or more minutes from the off. End its first line ("Races read X of Y ...") with " — BACKUP READ at <UTC time>".
```

## Night grade: three prongs

```
NIGHT GRADE: William's three-prong paper test (docs/HANDOFF.md, 2026-10-26). There is no deadline: if you resume hours late, finish the work anyway. Never touch code. Never write duty-*.csv.

1. Run `date -u`. Run `git fetch origin main reads`, then `git checkout -B reads origin/reads` and `git merge --no-edit origin/main`. If origin/reads does not exist yet, use `git checkout -B reads origin/main`. Today's file is data/reads/<UK day>.md. Read docs/LEARNING.md.
2. Results:
   - from The Racing API connector (get_results_today, or get_result_by_id per race);
   - and from Sporting Life: www.sportinglife.com/racing/results lists the day; each result page is /racing/results/<day>/<course>/<id>/x. Its __NEXT_DATA__ JSON gives per ride: finish_position, ride_description (the in-running comment), betting.historical_odds (the market move) and horse.previous_results.
   Fetch with curl and parse with python.
3. Append a "## Graded" section to today's file, never altering what was banked:
   - each prong's pick: WON or LOST, with SP, the winner and the margin, and the pick's in-running comment;
   - THE MOVE: the pick's price at bank against its SP, with the Sporting Life betting.historical_odds path. Mark it BACKED (shorter at the off), STEADY, or DRIFTED;
   - STORY: set HOW HE WINS beside the in-running comment and grade it as one of: right horse right story (skill), right horse wrong story (lucky, called lucky), wrong horse right story (beaten by a better horse: say who), wrong horse wrong story (misread: name the line misread);
   - each favourite verdict: right or wrong (a SOLID that lost; a NOT SOLID that won);
   - every losing pick: Rule One ("why was the winner the best horse"), then my error in ONE sentence;
   - a winning pick: which lines carried it, and a lucky win called lucky.
4. Update data/reads/TALLY.md:
   - per prong: picks, winners, strike rate, and £1 level-stakes profit or loss at SP;
   - the SOLID-favourite strike rate;
   - STORY accuracy: per prong, the count of each of the four story grades;
   - THE GAP and THE MOVE: picks, winners and £1 P&L for CLEAR, NARROW and COIN-FLIP, and for BACKED, STEADY and DRIFTED. These come from the GitHub reading list, 26 Oct: results improved on clear-gap races, and the market move before the off carries information. The record will say whether either holds here;
   - a SIGNPOSTS table: for each list on the morning signposts page (hot trainers, C&D winners, first-time headgear, wind op, long travellers, hot jockeys, notebook horses), the running totals of runners, winners and £1 level-stakes profit or loss at SP. The record judges which nuggets matter.
5. THE NOTEBOOK (his word, 26 Oct: "a hive of information on this website that you could mine every day ... to fill in some of the gaps"). Read every GB/IE ride_description from today's Sporting Life results with a python extract (horse, course, position, comment only). Add to data/reads/NOTEBOOK.md any horse whose comment shows a run better than its finishing position: trouble in running, slowly away, short of room, hampered, or finishing fast after an unsuitable pace. Write one line each: date, course, horse, position, the comment quoted. These are facts for tomorrow's read, not a rule.
6. LESSONS: append at most ONE lesson to data/reads/LESSONS.md, as `## <day> — ASKED`, then:
   - the incident, quoted;
   - the gap between story and race;
   - the lesson, phrased as a yes/no question to William.
   Before asking, check the ledger: never re-ask a NO, and never ask what a YES already covers. A pattern goes to him as a question. Never carve a rule.
7. Commit ("reads: <day> graded") and run `git push origin reads`, retrying up to 4 times with backoff.
8. Tell William in ONE short message: each prong's result and story grade, the running tally, how the signposts did today, how many notebook horses were added, and tonight's lesson question (answer yes or no).
```

## Sunday review

```
SUNDAY REVIEW: the weekly step of the learning loop (docs/LEARNING.md). There is no deadline. Never touch code. Never carve a rule.

1. Run `date -u`. Run `git fetch origin main reads`, then `git checkout -B reads origin/reads` and `git merge --no-edit origin/main`. Read docs/LEARNING.md.
2. Read this week's data/reads/<day>.md files (Monday to Sunday), TALLY.md, LESSONS.md and NOTEBOOK.md.
3. Append `## Week ending <day>` to data/reads/WEEKLY.md:
   - per prong: picks, winners, strike rate, £1 P&L, against the running total;
   - story accuracy: the four story grades per prong, and what they say (skill, luck, beaten by better, misread);
   - signposts: which lists found winners this week and in total, with numbers only;
   - favourite verdicts: how many SOLID won; every NOT SOLID that won, with the line that was misjudged;
   - notebook: how many notebook horses ran, won, at what prices;
   - the misreads: the "my error" lines of the week, grouped where the same mistake repeats;
   - 2 or 3 questions for William, each answerable yes or no;
   - lessons still ASKED and awaiting his word.
4. Commit ("reads: week ending <day>") and run `git push origin reads`, retrying up to 4 times with backoff.
5. Fold the learning into the project: open a pull request from `reads` into `main` titled "Learning: week ending <day>" (data/reads only). Merge it once the tests are green. If they are red, say why and leave it open.
6. Tell William in ONE short message: the week per prong, story accuracy in one line, the best and worst signpost, and the 2 or 3 questions.
```
