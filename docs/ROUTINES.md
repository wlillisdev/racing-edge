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
| Pre-off market check | `CRON_TZ=Europe/London 21 11 * * *` (reads the 11:05 Betfair push) | trig_014N3tNUwBoLM1JfS1xBJDRJ |
| Backup morning read (only if missed) | `CRON_TZ=Europe/London 41 11 * * *` | trig_01S7x42mvcn4cjTZrPyiZN5D |
| Night grade | `CRON_TZ=Europe/London 31 22 * * *` (after the 22:05 Betfair results push) | trig_01GHqLGELcgadYxQqim9ZZL3 |
| Sunday review | `CRON_TZ=Europe/London 41 22 * * 0` | trig_01PYvmJuy6wQ5LEvvPnDM9GM |

THE REFRESH FREEZE (his "that's an honest approach", 26 Oct): from 27 Oct these instructions are frozen. They change only for broken plumbing (a run that fails, a source that dies), or through a YES lesson in data/reads/LESSONS.md, or on his explicit word. No new machinery, list, label or step from the apprentice's own head.

PROJECT REFRESH (his word, 26 Oct, from 27 Oct): pick the winner of every
race from a clean read of the form, store a snapshot of the form, and each
night compare the snapshot, the notes and the result. Why, and which files
the loop reads and writes: docs/LEARNING.md.

Outside the session, `.github/workflows/watchdog.yml` checks the `reads`
branch at 11:15 and 23:45 UTC and goes red (GitHub emails him) when a day is
missing or ungraded, and warns when the pre-off check never ran.

## Morning read

```
MORNING READ: PROJECT REFRESH (docs/LEARNING.md). Pick the winner of every GB/IE race from a clean read of the form. Paper only. Never touch code. Never write duty-*.csv.

1. Run `date -u`. Run `git fetch origin main reads`. If origin/reads exists, run `git checkout -B reads origin/reads` then `git merge --no-edit origin/main`; otherwise `git checkout -B reads origin/main`. If data/reads/<UK day>.md already exists, stop: the day is banked.
2. READ FIRST, in this order:
   - THE RULEBOOK: NAP_SYSTEM in src/racing_edge/study/morningread.py, his base rules in his words. Rule One stands above all of it: "THE BEST HORSE WINS THE RACE. FIND THE BEST HORSE." Every law about how to read a horse is a question to ask. These parts were written for the retired engine and his later words overrule them; do not apply them (the 29 Oct audit, his word: "weed out any bad data or conflicting rules"):
     - every PASS, LEAN and NAMED PASS (laws 1, 1b, 1c, 5, 5c, 5d, and 6's "Class 6 flat is a pass"): every race gets a pick (PROJECT REFRESH, 26 Oct: "I want you to pick the winner of each race"). 1b and the race laws only label a race READABLE or NOT;
     - 2b's "when in doubt, the favourite IS the pick": overruled by "stop focusing on favourite and not favourites ... just pick the best horse that will win the race" (27 Oct). The favourite is weighed like any runner;
     - 2b-ii (the five-part SOLID test) and law 3 (ELIMINATE, cross off) as gates: overruled by "stop ruling everything out" (26 Oct) and his YES the same night, "weigh the whole case; never rule out on one narrow fail". What they ask (form, mark, fitness, trip, the market) are breadcrumbs;
     - the engine machinery: "Answer ONLY a single JSON object", the candidate-race and nap-of-the-day framing, the engine lenses as scores, and VETO_SYSTEM entire (the engine's veto). None of it applies to a hand read;
   - data/reads/LESSONS.md: every YES lesson applies today;
   - data/reads/WHY.md, the last 14 days: why the winners won;
   - data/reads/why-favourites-lost/, the last 14 days: why the favourites lost (his word, 29 Oct: "create a folder why the favourites lost"), so a beatable favourite is seen before the off;
   - the "what I missed" lines of the last 7 graded days in data/reads/.
   Then carry them INTO every race, not beside it (his word, 28 Oct: "you knew all these breadcrumbs, and time and time again you don't use them"). The rulebook read once at the top and then forgotten is how 27 Oct was lost: his jockey-booking and stable-in-form laws (3d, 4f) were read that morning and Fahidi and Show Me Glory, Balding and Murphy, were still opposed. The form decides, not yesterday's mood, and his breadcrumbs are how the form is read.
   OPEN-MINDED, NOT STRICT (his word, 26 Oct: "this is the problem with the whole system you've created, all these strict rules everywhere ... that nullified actually reading the form and finding nuances ... look at every race with a certain amount of open-mindedness, and stop ruling everything out"). His laws and lessons are QUESTIONS TO ASK OF THE FORM, weighed together: never a gate or a number that rules a horse out on its own. A horse a few days past a line, a few pounds up, short of one box on a test, is weighed, not discarded. The only absolutes are the ones he has said in absolute words (e.g. "never back an odds-on" in a 3yo all-weather novice).
3. THE SNAPSHOT (his word: "take a snapshot of the form of that race, store it"). Before reading, save the form exactly as it stands, so tonight compares against the same facts:
   - The Racing API connector, get_racecards_standard (gb,ire). It returns 20 races a page: page with skip until the count equals "total". If an answer is saved to a file, copy that file. Save the full cards as data/reads/snapshots/<day>/racing_api.json.
   - Sporting Life: www.sportinglife.com/racing/racecards lists the day; each race page is /racing/racecards/<day>/<course>/racecard/<id>/x. Fetch every GB/IE race page with curl, one every 2 seconds. From each page's __NEXT_DATA__ JSON keep the race object: per ride the commentary, betting.current_odds, timeform_stars, official_rating, draw, and horse.previous_results with each run's ride_description. Save as data/reads/snapshots/<day>/sportinglife.json.
   - Betfair (his Oracle London server pushes horse prices every hour from 07:05 UK to racing-edge's `odds` branch): run `git fetch origin odds` and copy the newest data/odds/<day>-*-betfair-horses.json into the snapshot folder as betfair.json, and name its push in the first line (e.g. "Betfair 09:05 push"): the pre-off check compares against it. It holds per race the exchange back, lay and last traded price of every runner, each runner's total matched (the weight of money) and Betfair's card for him (meta: form, official rating, weight, draw, age, days since his last run, jockey, trainer, forecast price). If the Racing API card is missing or thin, that card is the backup: say so in the first line. If no Betfair file for today exists yet, say so in the first line and carry on without it.
   - Cross-check: every GB/IE course on Sporting Life is in the Racing API cards. If one source fails, use the other and say so in the first line. If both fail, write "Races read 0 of ? — DATA DOWN: <what failed>", push, and stop.
4. FOR EVERY RACE, using the snapshot (and get_race_analysis with depth "full" or get_horse_racecard_results where the form needs more):
   - TYPE: handicap / novice-maiden / conditions / pattern; flat / AW / hurdle / chase; age band. READABLE or NOT, by the rulebook's race laws (1b, #13, #14, novice/maiden, the 3yo AW lesson). Every race still gets a pick; the label is what we learn from.
   - THE CONTENDERS: 3 or 4 serious ones, each with one line: "IF HE WINS, it will be because ...". Then, under each contender, THE BREADCRUMBS: look through every place below, and write the ones that speak for him or against him, in a few words from the snapshot. THINK LIKE HIM (his word, 28 Oct: "we don't want to fall for past mistakes of hard rules everywhere ruling out most horses. These are more breadcrumbs. Think like me as you are evaluating a race with an open mind as you find the breadcrumbs"). The list is WHERE TO LOOK, not a test to pass: no score, no count of ticks, no horse ruled out for a missing item. A horse with one loud breadcrumb (the class, the booking, the trip that suits) can beat one with a tidy line. Weigh them together, the way a handicapper reads a race, and let the race tell its story. The places to look:
     C&D (course and distance form) · TRIP (proven, or a change that suits his comments, e.g. a speedy horse dropping in trip) · GOING (his form on today's ground, good or bad: Wobwobwob's heavy-ground run won on soft) · CLASS (up or down in grade, and the level of his best form: a horse dropping from Class 3, or out of a Listed race, as North Of Richmond and Always Proud did; his law, "class horse form is temporary, class is permanent") · FORM FIGURES (the trend: improving, steady or falling; how many runs a young horse has had; read beside the comments, because figures alone hid The Stony Baker and Fahidi) · DAYS SINCE LAST RUN (race-fit or fresh; first run back after a break and his record fresh; a quick turnaround after a win: Iamyouare, 26 days and in form, beat a 185-day absentee; THE SECOND RUN BACK, his YES of 30 Oct: a horse whose first run back "needed the run" is sharper, fitter and expected to improve, as Tai Tam Bay, Celestial Siren and Lully Du Houx did) · LAST RUN (the comment read for HOW he ran, not the figure) · HEADGEAR AND WIND OP (first-time headgear or a change of it, and the first or second run after a wind op: Talismans Time won in a first-time visor, They Want Me won on his second run after a wind op, Kent De Thaix was backed to 2/1 for his first after one) · WEIGHT AND MARK (weight today against the ratings, a rider's claim, the mark against his last win and how he won it; rulebook 3d and 3e, and his 5lb lesson) · JOCKEY AND TRAINER (each one's current form, the pair's record, and THE BOOKING: a top rider at a small meeting is there for a reason; the TRAINER'S RECORD AT THIS COURSE, from the Racing API connector's get_trainer_course_analysis, and the jockey's course record) · THE TRAINER WITH THIS HORSE (his runs and wins for this yard, his first run for a new yard, how the trainer has placed him; the trainer's record with horses of this age, get_trainer_horse_age_analysis) · AGE (a young horse with few runs is still improving, an exposed older one has shown his level; weight-for-age where 3yos meet older horses) · BREEDING (sire, dam and damsire, most where the form is thin, a newcomer, or a new trip, ground, surface or class: is he bred for this trip, going, surface and grade, and to come to hand at this age; the connector's sire, dam and damsire distance and class analyses; anything on going, surface, age or headgear not in the connector is marked general knowledge, never a figure) · PACE (who leads, who rides him, can he be left alone; read for this race's trip, going and track) · DRAW (on the all-weather, and the flat where the track bites) · THE MONEY (Betfair against the forecast, and the form reason or "not in the form").
     Before every race, also read every runner's comments, whatever his price: the 200/1 Stony Baker's speed was in his comment. A horse outside the contenders whose breadcrumb line would be stronger goes in.
   - THE PICK: the horse whose winning story needs the fewest unknowns, the one the breadcrumbs, weighed together with an open mind, point to. Write its price, and HOW HE WINS (where he sits, when he goes, who he beats and why).
   - EACH WAY (his word, 29 Oct: "you fancy him on form for whatever reason, obviously the market thinks he has a small chance ... gems hidden in the long grass ... each way at 8/1, if he places we will be fine"): if the pick is 8/1 or bigger, mark it EW beside its price and write in one line what the form shows that the market is missing. It is still the pick to win; each way is how a big price is measured.
   - HOW HE LOSES: the strongest honest case against the pick, as tomorrow's autopsy would write it. Then BEAT THE DANGER (his rule 8, taught 9 Jul: "if you cannot beat the danger honestly, then the danger IS the pick"; and 28 Oct: "the method is solid, you need to stop making the same mistake"): when HOW HE LOSES names a rival with a real form reason, answer it in writing before the pick is banked, why does my horse beat him? If there is no honest answer, the rival is the pick. On 27 and 28 Oct the danger I named won at least 13 times.
   - THE MONEY QUESTION (his word, 27 Oct: "you have live odds, you can see these real-time gambles happen, and you miss them"). Run `PYTHONPATH=src python -m racing_edge.cli.marketcheck data/reads/snapshots/<day>/betfair.json` once for the day. For any runner it flags SUPPORTED (Betfair already shorter than the bookmakers' forecast) ask: what in the snapshot explains this money (a drop in class, an excuse last time, a hot yard, a big jockey booking, a "ran on")? Write the answer, or "NOT IN THE FORM", in the race's notes. It is a question to the form, never a pick on its own: on 27 Oct no band of supported horses was steadily profitable, and the friendless ones were the steady losers.
   Keep it short: a race in five or six lines. Read the form first; the money is a question you put to it.
5. Bank only races whose off is at least 30 minutes after a fresh `date -u` taken at the moment you write. A race too close to the off is listed as MISSED, with no pick.
6. Write data/reads/<day>.md, and never edit an earlier day's file:
   - FIRST LINE: "Races read X of Y (courses: ...)", plus any fallback used. If X is less than Y, say why.
   - Then a table: time, course, pick, price (bookmaker, and Betfair back where the file has it), the favourite and his price (from the snapshot), READABLE or NOT.
   - Then THE NAP AND NB for each meeting (his word, 28 Oct: "give me a nap and nb for each race meeting, it will push you more"): a table of meeting, NAP (the pick I am most sure of at that meeting: time, horse, price), NB (the next best), and one line on why the nap. Chosen from the picks already made, the strongest breadcrumbs weighed with an open mind, never by price alone.
   - Then each race's notes as in step 4.
7. BANK AS YOU GO (this session has paused for hours before): commit the snapshot first, then write and commit the day file after EACH meeting is read, with the first line's running count kept true, and push each time (`git push origin reads`, retrying up to 4 times with backoff). A pause then costs only the races not yet read. A push that never lands means those races are not banked: say so loudly.
8. Tell William in ONE short message: races read X of Y, the NAP and NB for each meeting first, then the picks, one per line (time, course, horse, price).
```

## Pre-off market check

```
PRE-OFF MARKET CHECK (his word, 27 Oct: "do your initial selection, and then before the first race read Betfair odds again, and then update your selection based on that"). Paper only. Never touch code. Never write duty-*.csv.

1. Run `date -u`. Run `git fetch origin main reads odds`, then `git checkout -B reads origin/reads` and `git merge --no-edit origin/main`. If data/reads/<UK day>.md does not exist, stop and say nothing: the backup read at 11:41 reads with fresh prices. If it already has a "## Pre-off market check" section, stop: done.
2. Take the newest data/odds/<day>-*-betfair-horses.json on origin/odds (`git show origin/odds:<path> > /tmp/now.json`). If it is the same push the morning snapshot used (the first line names it) or there is none, write the section with one line saying so, push, and stop.
3. Run `PYTHONPATH=src python -m racing_edge.cli.marketcheck /tmp/now.json --morning data/reads/snapshots/<day>/betfair.json --min-minutes 15`. Per race it shows the market leaders and every runner flagged SUPPORTED or FRIENDLESS (exchange share against the forecast's) or FIRMED or DRIFT (against the morning file). Races off within 15 minutes are TOO LATE: the morning pick stands.
4. For every race not TOO LATE, with the morning notes and the snapshot open:
   - each flagged runner in one line: the move, and the snapshot fact that explains it, or "NOT IN THE FORM";
   - THE GOING ON THE DAY (his word, 28 Oct: "also look at the going on the day"): read the official going now from each meeting's Sporting Life racecard page (the race's going, and any going change or new non-runners) against the morning's. If it has changed, say whom it helps and whom it hurts among the contenders, from their form on that ground;
   - MY PICK's own move: firmed, steady or drifted. A drift is a question too: what does the market know?
   - THE FINAL PICK: KEEP the morning pick or SWITCH, with the reason in one line. A final pick at 8/1 or bigger is EW, as in the morning read. The money and the going are weighed WITH the form, never instead of it. The questions: does the money back a horse I already rated (in my contenders) or one whose snapshot shows a reason I underweighted? Then a switch is open. Is it money with NOTHING in the form? Then note it and keep. Has my pick drifted with no reason in the form? Weigh it, do not panic. Every switch is my judgement, written down, so the night grade can judge it.
5. Append to data/reads/<day>.md a "## Pre-off market check (<UTC time>, Betfair <HHMM> push)" section, never editing the morning section: a table of time, course, morning pick (morning Betfair, now), the flagged runners (move, reason or NOT IN THE FORM), FINAL PICK, KEEP/SWITCH and why. Then one line: "Switches: N".
6. Commit ("reads: <day> pre-off check") and run `git push origin reads`, retrying up to 4 times with backoff.
7. Tell William in ONE short message: the switches, one per line (time, course, morning pick → final pick, the money and the form reason), or "no switches", plus any gamble flagged with NOTHING in the form.
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
   - The Racing API connector (get_results_today, or get_result_by_id) as the cross-check;
   - Betfair: `git fetch origin odds`. Betfair's starting price (BSP) and the result for every race are in data/odds/<day>-2205-betfair-horses-results.json (pushed after the 22:05 server run; if it is not there yet, grade at bookmaker SP and say so). For the move, take for each race the last data/odds/<day>-*-betfair-horses.json taken before its off (the close) against the morning snapshot's betfair.json.
   Fetch with curl and parse with python. Save the results beside the snapshot as data/reads/snapshots/<day>/results.json, with each pick's Betfair morning and closing price.
3. THE COMPARISON, for every race. Lay the morning snapshot, the morning notes and the result side by side. Append to today's file a "## Graded" section, never altering what was banked. For each race:
   - WON or LOST, with the pick's SP and position; the winner, SP and margin. An EW pick is also settled each way at bookmaker SP on standard each-way terms (2 to 4 runners: win only; 5 to 7: 1/4 the odds, 2 places; 8 or more: 1/5, 3 places; handicaps of 12 to 15: 1/4, 3 places; handicaps of 16 or more: 1/4, 4 places), counting the runners that actually ran: PLACED or UNPLACED, and the each-way return to £1 each way. Where the pre-off check SWITCHED, grade the final pick too, and say whether the switch won, lost or made no difference;
   - the pick's in-running comment, and the winner's;
   - THE TWO-LINE AUTOPSY (his word: "with two lines you summed up the whole race"): line 1, WHY THE WINNER WAS THE BEST HORSE TODAY (his word, 27 Oct: "the best horse will win the race ... when you start looking at the breadcrumbs, you will find that the best horse won the race ... stop focusing on favourite and not favourites"), citing the breadcrumb in the morning snapshot that pointed to him: a change of trip that suits the run style in his comments, a drop in class, an excuse or a "ran on" last time, a yard or rider in form, the money. Hunt for it hard, as for the 200/1 Stony Baker (a speedy horse dropping from 6f to 5f). Write "NOT IN THE FORM" only when the snapshot truly holds nothing (luck, trouble in running, a newcomer); line 2, what I got right, wrong or missed in the morning notes. Never invent a pre-race fact the snapshot does not hold;
   - WHERE THE WINNER SAT in the morning notes: MY PICK, IN MY CONTENDERS, or NOT SEEN;
   - THE UNUSED BREADCRUMB: if my pick lost, which item on the winner's breadcrumb line did the morning notes have and still weigh wrong, or leave unanswered? Name it from the same list (C&D, trip, going, class, form figures, days since last run, last run, headgear and wind op, weight and mark, jockey and trainer, the trainer with this horse, age, breeding, pace, draw, the money). TALLY.md keeps the count;
   - THE NAMED DANGER: did the winner appear in my HOW HE LOSES line? If so, say whether the morning notes answered him (BEAT THE DANGER) and why the answer was wrong, or left him unanswered. TALLY.md keeps the count: it must fall to zero;
   - THE 50/50 (his word, 27 Oct: "you picked an awful lot of second horses, which shows that you are reading the form right, but you're just missing the final nail in the coffin, the final few breadcrumbs ... we have to figure out why you keep picking the wrong one"). For every race where my pick finished 2nd, or the winner was IN MY CONTENDERS: put my pick and the winner side by side on the morning snapshot (last-run comments, trip, class, going, draw, weight and mark, days off, yard and rider form, the money from morning to off) and on the in-running comments. Name THE TIPPING BREADCRUMB: the one fact in the snapshot that favoured the winner and that I underweighted, or the fact I trusted in my pick that let him down. Then name WHY I picked the wrong one (I trusted a figure over a comment, the bigger name, the last run over the pattern, a story, ignored the money), in the same few words each night so the pattern shows;
   - THE MARKET (his word, 27 Oct: "what started as favourite, did the favourite win, or what ended up as favourite ... the power of the market move ... was there underlying data to show why there was a gamble on that horse, maybe he was hidden in plain sight"). Record:
     - the MORNING FAVOURITE (shortest in the morning snapshot) and the SP FAVOURITE, and whether either won;
     - THE GAMBLE: the horse whose price shortened most from the morning snapshot to his SP (Sporting Life historical_odds, Betfair morning file to close) and where he finished;
     - for the gamble, the line in the MORNING SNAPSHOT that showed why (a recent run, a trainer pattern, a drop in class, an excuse last time), or "NOT IN THE FORM" if nothing did. A gamble that won with the reason in the snapshot is a horse hidden in plain sight: name the line I failed to weigh.
4. data/reads/WHY.md: one line per race the pick lost, plus any race that teaches: date, race, winner, SP, why he won (in-running comment quoted), and a short reason type (examples, not a closed list: improver from a top yard; unexposed newcomer; class dropper; well-handicapped off a lower mark; trouble last time; pace and draw; course specialist).
5. data/reads/TALLY.md, running totals:
   - races picked, winners, strike rate, and £1 level-stakes profit or loss at SP, for the day and in total, at bookmaker SP and at Betfair SP where the results file has it;
   - THE MARKET BAR (his baseline, 27 Oct: "you could have probably got better by picking blind. That is your baseline you have to beat"): in the same races, backing every favourite: winners, strike rate, £1 P&L at SP. A scoreboard only: the morning read picks the best horse, never "favourite or not";
   - THE MONEY (Betfair, a measurement only): my picks that shortened from the morning file to the close against those that drifted, winners and £1 P&L for each. The record will say whether the money agrees with the form;
   - the same split by READABLE or NOT, and by race type (handicap, novice-maiden, conditions-pattern; flat, AW, hurdle, chase);
   - THE MARKET: morning favourites won X of Y, SP favourites won X of Y, gambles won X of Y (and how many of those were in plain sight in the snapshot);
   - THE NAPS AND NBs: naps won X of Y and £1 P&L at SP, NBs won X of Y and £1 P&L, for the day and in total, against the market bar;
   - THE PRE-OFF CHECK: morning picks against final picks (winners, strike rate, £1 P&L for each), switches won X of Y, keeps that lost to a horse it flagged SUPPORTED. And the flags themselves: SUPPORTED runners won X of Y and £1 P&L, FRIENDLESS won X of Y, split by "reason in the form" and "NOT IN THE FORM". The record, not one day, will say what the money is worth;
   - THE 50/50s: how many of my picks finished 2nd, how many of those races the winner was in my contenders, and a running count of the TIPPING BREADCRUMBS and the WHY-I-PICKED-WRONG reasons, most frequent first. "If those seconds had been firsts" — say what the day would have been;
   - THE NAMED DANGER: races where the winner was the danger I named, for the day and in total, answered or unanswered;
   - EACH WAY (his word, 29 Oct): the EW picks (8/1 or bigger), won X, placed Y of Z, and £1 each-way P&L (a £2 stake) for the day and in total, beside what the same picks returned to win only;
   - the foresight check: MY PICK / IN MY CONTENDERS / NOT SEEN. A high IN MY CONTENDERS count means I read the race but weighed it wrong; a high NOT SEEN count means I did not read it. Say which it is.
6. WHY THE FAVOURITES LOST (his word, 29 Oct: "create a folder why the favourites lost"). Write data/reads/why-favourites-lost/<day>.md: one entry for every race the SP favourite lost (the morning favourite too, where he was a different horse and lost). Each entry: race; the favourite, his SP and morning price; where he finished and how far beaten; his in-running comment, quoted; the winner and SP; HOW HE WAS PRICED (his word, 29 Oct: "you will also see patterns in the way bookmakers price the market"): the bookmakers' forecast in the morning snapshot, Betfair's morning and closing price, the SP, backed or drifted, and how far clear of the second favourite he was; WHY HE LOST in one line, with a short reason type (examples, not a closed list: a better horse on the day; trip; ground; pace; draw; trouble in running; found out in class; short of fitness; the rise in the weights; the money against him; over-bet on a name); THE WARNING: the line in the morning snapshot that showed he was beatable, or "NOT IN THE FORM"; and whether my pick took him on, and with what result. End the file with one line: favourites lost X of Y today. Facts, never a rule against favourites.
7. data/reads/NOTEBOOK.md: any horse whose in-running comment shows a run better than its finishing position (trouble, slowly away, short of room, hampered, finishing fast off an unsuitable pace), one line each with the comment quoted. These are facts, not rules.
8. LESSONS: when the same WHY-I-PICKED-WRONG reason in the 50/50s reaches three, it is tonight's lesson question. Append at most ONE lesson to data/reads/LESSONS.md, as `## <day> — ASKED`: the incidents quoted, what I missed, and the lesson as a yes/no question to William. A lesson is asked only when the same miss or winning reason appears at least twice in WHY.md, or when the miss broke one of his written laws: one race can be luck. Never re-ask a NO; never ask what a YES already covers. Never carve a rule.
9. Commit ("reads: <day> graded") and run `git push origin reads`, retrying up to 4 times with backoff.
10. Tell William in ONE short message: the naps and NBs first (each meeting, won or lost), then winners X from Y races (morning picks, and final picks after the pre-off check), the seconds and the top reason I picked the wrong one of two, how many winners were the danger I named, the EW picks (placed X of Y, each-way P&L), morning favourites v SP favourites v gambles (won X of Y each, and the horses hidden in plain sight), strike rate and £1 P&L today and in total, AGAINST THE MARKET BAR (favourites in the same races), READABLE v NOT strike rates, the foresight split, and tonight's lesson question (answer yes or no).
```

## Sunday review

```
SUNDAY REVIEW: PROJECT REFRESH, the weekly step (docs/LEARNING.md). There is no deadline. Never touch code. Never carve a rule.

1. Run `date -u`. Run `git fetch origin main reads`, then `git checkout -B reads origin/reads` and `git merge --no-edit origin/main`. Read docs/LEARNING.md.
2. Read this week's data/reads/<day>.md files (Monday to Sunday), TALLY.md, WHY.md, this week's data/reads/why-favourites-lost/ files, LESSONS.md and NOTEBOOK.md.
3. Append `## Week ending <day>` to data/reads/WEEKLY.md:
   - strike rate and £1 P&L for the week and in total, AGAINST THE MARKET BAR (every favourite in the same races), split by READABLE or NOT and by race type: where the reading works and where it does not;
   - the foresight check for the week, and what it says (weighing fault or reading fault);
   - the winning reasons from WHY.md that recurred, with counts, especially the ones that beat my picks;
   - the "what I missed" lines grouped where the same mistake repeats;
   - why the favourites lost: the reason types that recurred, with counts, how many had a warning in the morning snapshot, and the pricing that recurred (backed or drifted, forecast against Betfair, a short price after one run, a clear favourite in a weak race);
   - 2 or 3 questions for William, each answerable yes or no;
   - lessons still ASKED and awaiting his word.
4. Commit ("reads: week ending <day>") and run `git push origin reads`, retrying up to 4 times with backoff.
5. Fold the learning into the project: open a pull request from `reads` into `main` titled "Learning: week ending <day>" (data/reads only). Merge it once the tests are green. If they are red, say why and leave it open.
6. Tell William in ONE short message: the week's strike rate and P&L, where the reading works and where it does not, the top recurring winning reason, and the 2 or 3 questions.
```
