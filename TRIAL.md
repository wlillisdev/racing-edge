# Form Trial — does applying the notebook rules actually pick winners?

The honest experiment. Not "trust the AI's picks" — a **verifiable, banked, settled
record** where the *results*, not anyone's word, deliver the verdict. Runs on the box
(PythonAnywhere) where the API data is real. Every pick is time-stamped and logged
BEFORE the race, then settled against the result, so there is no cheating and no
hindsight.

## What it does

Each morning the selector applies the notebook rules **that can be run off real data**
to every runner in every readable handicap, crosses off what can't win, and nominates
one pick — banked before the off.

Rules it applies now (from the form, on the box):
- **Race selection** (#3, #13, #21): readable handicaps only — no novice/maiden/bumper,
  no amateur races; all-weather flagged.
- **The mark** (#22-ish): well-in vs raised (the mark it last won off vs today's).
- **Course form** (#4, #10): course/distance winner, depth, local-master flag.
- **Elimination + fair field** (#24, #25, #26): score every contender, cross off on
  facts, zero in on survivors — never anchor on one.
- **Market rank** (#2, #19): the 2nd/3rd-fav sweet spot; don't fear a fair-priced fav.
- **Franking, tells** (#5, #15, #16): the earned patterns, flagged on the card.

## What it CANNOT do yet — OWED, and stated honestly

The two things that decided nearly every losing pick in testing:
- **The live market move** (#6, #17, #18, #22) — backed vs drifted. Needs a live-odds
  feed; the API gives one price, not the move. **The single biggest gap.**
- **Run-style / the running comments** (#1, #20, #27) — who leads, who's held up, how a
  horse finished. The API carries no comments. **The second biggest gap.**

So this trial tests the rules **minus those two lenses.** If it loses, that is a real
result, not an excuse — and it will tell us whether the data-driven rules alone have an
edge, or whether the edge lives entirely in the two OWED doors.

## The daily routine (on the box)

```bash
cd ~/racing_edge && git checkout claude/form-trial && git pull origin claude/form-trial
# morning — nominate + BANK the pick (time-stamped, before the off)
PYTHONPATH=src venv/bin/python -m racing_edge.cli.nap --day today --both
# evening — settle it against the result, update the strike rate
PYTHONPATH=src venv/bin/python -m racing_edge.cli.nap --settle today
# and read the whole card's real market moves for your own eye
PYTHONPATH=src venv/bin/python -m racing_edge.cli.dissect --day today
```

## How to check it (no trust required)

- Every pick + result is in `data/nap.db` — banked before the race, settled after.
- The strike rate prints on every `--settle`, split by CONFIDENT naps vs leans.
- Read every pick's reasoning on the card: which rules fired, what was OWED.
- The verdict is the **record after a few hundred picks**, not a good day or a bad one.
  Small samples lie (see the homework log). Judge it on the trial, not on tonight.

## The honest expectation

It may lose. The CLV work already showed the *numbers* have no selection edge, and the
two biggest lenses are OWED. This trial answers, verifiably: do the rules-off-real-data
do any better than the favourite — and is it worth opening the market-move and comments
doors to finish the job? The record will say. That's the whole point of trialling it
instead of arguing about it.
