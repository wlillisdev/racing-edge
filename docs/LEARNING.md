# LEARNING — how the apprentice gets better, written down

His words, 26 Oct: "get back to a system that will keep learning and getting
better. That is the bottom line ... We need to be able to be saving this back
into the project itself, into learning files, so we draw upon it every day
and don't lose the information we gained."

The model does not learn between sessions. Nothing in it updates from the
conversations. The only learning that survives is what is WRITTEN in this
repo and READ BACK every morning. So the learning is a loop on paper, and
the scheduled tasks (docs/ROUTINES.md) run it every day.

## The files (branch `reads`, folded into main every Sunday)

| File | Written | Read | What it holds |
|---|---|---|---|
| `data/reads/<day>.md` | morning (banked), night (graded, appended) | the night grade; the last 7 days by every morning read | the picks, each with HOW HE WINS; the signposts page; the favourite verdicts; then the grade |
| `data/reads/LESSONS.md` | night (one lesson at most, as a question); his answer is recorded when he gives it | every morning read | the lesson ledger: ASKED, then YES or NO in his words |
| `data/reads/NOTEBOOK.md` | night | every morning read | horses that ran better than their finishing position, comment quoted |
| `data/reads/TALLY.md` | night | Sunday review | per prong strike rate and £1 P&L; story accuracy; signposts table |
| `data/reads/WEEKLY.md` | Sunday review | every morning read (latest week) | the week's numbers, what went wrong, 2–3 questions for him |

## The loop

1. **Predict how, not only who.** Every pick carries one line, HOW HE WINS:
   the race shape the form says he gets (where he sits, when he goes, which
   rival he beats and why).
2. **Compare against what happened.** At night the pick's in-running comment
   (Sporting Life `ride_description`) is set beside HOW HE WINS. Each pick
   is graded on two counts, horse right or wrong and story right or wrong,
   giving one of four outcomes: right horse right story (skill), right horse
   wrong story (lucky, called lucky), wrong horse right story (beaten by a
   better horse: Rule One says who), wrong horse wrong story (misread: name
   the line misread).
3. **One lesson a night, as a question.** At most one, written to
   LESSONS.md as ASKED, with the incident quoted. A lesson never enters the
   read until he says yes. A YES lesson joins the morning checklist with
   his words beside it. A NO is kept, so it is never asked again.
4. **The Sunday review.** The week's numbers per prong, story accuracy,
   which signposts found winners, which favourite verdicts were wrong and
   why, then 2–3 questions for him. The `reads` branch is folded into main
   by pull request, so the project itself holds the learning.
5. **The numbers decide at 2–3 weeks.** He keeps what wins and drops what
   does not.

## What the morning read must draw on, every day

- every YES lesson in LESSONS.md, applied, and named where it bites;
- the "my error" lines of the last 7 graded days, so the same mistake is not
  made twice;
- the NOTEBOOK, and the latest WEEKLY questions and answers.

## How his answer is recorded

When William answers a lesson question in the session, the session writes
his answer, in his words and dated, into LESSONS.md on `reads` (status YES
or NO) and pushes it the same turn.
