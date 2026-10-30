# LEARNING — PROJECT REFRESH: back to school

His words, 26 Oct: "we're now going to call this project refresh. We're going
to go back to school again ... we're not going to overcomplicate it. We're
going to learn from our mistakes and we're going to build from the ground
up ... I want you to pick the winner of each race ... take a snapshot of the
form of that race, store it, and then that evening when the results come in,
look at that snapshot and the results and compare them with your notes ...
work out what was right, what was wrong, what did you miss ... You need to be
able to look at the race, read the form, and pick the winner ... by using
these snapshots and actually comparing them with the results ... you'll be
able to reverse it."

## Why it works this way

The crux (his words): "When you look at the race in hindsight, you know
exactly why they lost and why the other horse won." After the race, the
result shows where to look. Before the race, the read argued for a horse and
never against it. Refresh closes that gap by doing the same comparison every
night against a frozen copy of the morning's facts, until the hindsight
becomes foresight.

The model does not learn between sessions. Nothing in it updates from the
conversations. The only learning that survives is what is WRITTEN in this
repo and READ BACK every morning. So the learning is a loop on paper, and
the scheduled tasks (docs/ROUTINES.md) run it every day.

## The day

1. **Morning, every race.** Read his words (docs/HIS_WORDS.md), the YES lessons and the last
   14 days of WHY.md, then read each race clean. Store the SNAPSHOT of the
   form before reading. For each race: the type, READABLE or NOT, 3 or 4
   contenders each with "IF HE WINS, it will be because ...", THE PICK (the
   story with the fewest unknowns) with HOW HE WINS, and HOW HE LOSES.
2. **Night, every race.** Lay the snapshot, the notes and the result side by
   side. Write THE TWO-LINE AUTOPSY: why the winner won (and which fact in
   the morning snapshot showed it), and what the notes got right, wrong or
   missed. Record WHERE THE WINNER SAT: MY PICK, IN MY CONTENDERS, or NOT
   SEEN.
3. **One lesson a night, as a question.** At most one, written to
   LESSONS.md as ASKED. It enters the read only when he says yes.
4. **Sunday.** Where the reading works and where it does not (READABLE v
   NOT, race types), the recurring winning reasons, the repeated misses, and
   2 or 3 questions for him. The `reads` branch is folded into main.

## The files (branch `reads`, folded into main every Sunday)

| File | Written | Read | What it holds |
|---|---|---|---|
| `data/reads/snapshots/<day>/` | morning (racing_api.json, sportinglife.json); night (results.json) | the night grade | the form exactly as it stood at the pick, and the result |
| `data/reads/<day>.md` | morning (picks and notes); night (graded, appended) | the night grade; the last 7 days by every morning read | every race: type, contenders, pick, how he wins and loses; then the two-line autopsy |
| `data/reads/WHY.md` | night | every morning read (last 14 days) | why each winner won, with a reason type: the hindsight, kept so it becomes foresight |
| `data/reads/why-favourites-lost/<day>.md` | night | every morning read (last 14 days); Sunday review | every beaten favourite: why he lost, his comment quoted, and the warning in the morning snapshot or NOT IN THE FORM (his word, 29 Oct) |
| `data/reads/LESSONS.md` | night (one at most, as a question); his answers when he gives them | every morning read | the lesson ledger: ASKED, then YES or NO in his words |
| `data/reads/TALLY.md` | night | Sunday review | strike rate and £1 P&L, by READABLE or NOT and race type; the foresight split |
| `data/reads/NOTEBOOK.md` | night | the morning read, as facts | horses that ran better than their finishing position, comment quoted |
| `data/reads/WEEKLY.md` | Sunday | every morning read (latest week) | the week's verdict and questions |

## The foresight check

For every race, where did the winner sit in the morning notes?
- MY PICK: the read was right.
- IN MY CONTENDERS: the read saw him and weighed him wrong. That is a
  weighing fault.
- NOT SEEN: the read missed him. That is a reading fault.

The counts say which fault to fix first.

## How his answer is recorded

When William answers a lesson question in the session, the session writes
his answer, in his words and dated, into LESSONS.md on `reads` (status YES
or NO) and pushes it the same turn.
