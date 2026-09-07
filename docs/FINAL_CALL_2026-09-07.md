# THE FINAL CALL — what the record says, counted not argued

The master, 2026-09-07: "there has to be a better way of making the final
call, surely you can get it right if you think hard enough" — and, the same
night, "learn and improve".

Thinking hard produced three tie-breaks in a fortnight (most reasons, then
the class line, then the mark) and all three were wrong. This is the count
instead. 396 corpus races where the two shortest in the market held the
winner and both horses had prior form; every feature computed from runs
STRICTLY BEFORE the race day.

## THE ANSWER IN THREE LINES

1. **When the market separates the two, take the market's first.** With the
   second 25-75% longer the market's first wins 61.4% of the pair; every
   lens we can compute is 46-56%. Deviating there costs about fifteen points.
2. **When the market cannot separate them, the market is a coin flip** —
   49.3% — and that is the only place a lens has anything to add. Best of
   the computable ones: DIRECTION OF THE LAST THREE LINES, then the class
   line, at 52.7% on 112 races. Suggestive, NOT proven: 3.4 points on 112
   is inside the noise.
3. **No lens beats the market overall.** Across all 396, the market's first
   is 59.3% and the best rule is 54.8%. The universal tie-break we have been
   hunting for three weeks does not exist in these features.

## WHAT THIS CHANGES ABOUT THE QUESTION

We have been asking "which tie-break decides the final two". The count says
that is the wrong question, because it has a different answer depending on
what the market has already done. The right question is narrower and
cheaper: **is the market split on these two?** If it is not, the final call
is already made. If it is, we are in a coin flip and need a lens the market
has not priced.

## THE LENS THIS CANNOT SEE, AND WHY IT MATTERS

MANNER OF RUNNING is absent from every line above — the comments file lives
on the box, not in this repo. The six-week synthesis of 2026-09-07 names
manner as the one lens that has been winning consistently (rules #15, #17,
#20). So the study has ranked the whole rest of the menu and found it
wanting, while the item the record already likes was not on the table. That
is the case for the backward replay: the engine's real final two, with the
comments door open.

## HOW TO READ THE TABLES

- `decided` is the races where that rule had an opinion (a rule that cannot
  separate two horses is not charged for them).
- `strike` is comparable between rules; it answers "given the winner is one
  of these two, how often did this rule name it".
- `ROI at SP` is comparable BETWEEN rules on the same rows and is NOT an
  absolute return: every race here was selected because the pair held the
  winner. A rule that prefers the longer of the two is paid more when right.
- Nothing here is a rule (CLAUDE.md law 2). Judge nothing under 50.

corpus: 24011 runner rows, 2727 races, 396 races where the top two held the winner and both had form

Every feature is computed from that horse's runs STRICTLY BEFORE the race day. MANNER IS ABSENT (the comments file lives on the box) — the one lens the weekly synthesis says wins consistently is NOT tested here. Market rank is by SP, which makes the benchmark harder than a 07:30 read would face. Nothing below is a rule.


## ALL

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 396 | 59.3% | +60.2% | |
| better class line | 281 | 53.0% | +64.5% | |
| rising lines (law 3b) | 168 | 50.0% | +56.4% | |
| class line, direction within a rung | 278 | 50.4% | +56.4% | |
| direction, then class line | 331 | 52.3% | +64.2% | |
| won last time out | 125 | 52.8% | +58.9% | |
| hotter yard (30d) | 243 | 53.1% | +62.0% | |
| hotter yard, else market | 396 | 54.8% | +61.5% | |
| hotter jockey (30d) | 283 | 47.3% | +54.8% | |
| fresher (fewer days) | 356 | 51.1% | +69.6% | |
| beaten less last time | 345 | 51.3% | +63.8% | |

## market SPLIT (2nd within 25%)

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 134 | 49.3% | +71.0% | |
| better class line | 94 | 50.0% | +87.9% | |
| rising lines (law 3b) | 59 | 50.8% | +79.5% | |
| class line, direction within a rung | 97 | 43.3% | +62.6% | |
| direction, then class line | 112 | 52.7% | +94.9% | |
| won last time out | 32 | — | — | under 50, no verdict |
| hotter yard (30d) | 76 | 52.6% | +86.9% | |
| hotter yard, else market | 134 | 49.3% | +77.7% | |
| hotter jockey (30d) | 92 | 46.7% | +73.4% | |
| fresher (fewer days) | 118 | 47.5% | +75.4% | |
| beaten less last time | 120 | 47.5% | +82.8% | |

## market CLEAR (2nd 25-75% longer)

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 132 | 61.4% | +71.3% | |
| better class line | 88 | 46.6% | +49.1% | |
| rising lines (law 3b) | 58 | 48.3% | +43.0% | |
| class line, direction within a rung | 91 | 51.6% | +61.4% | |
| direction, then class line | 110 | 46.4% | +42.0% | |
| won last time out | 50 | 56.0% | +85.8% | |
| hotter yard (30d) | 79 | 51.9% | +70.4% | |
| hotter yard, else market | 132 | 56.1% | +71.6% | |
| hotter jockey (30d) | 97 | 49.5% | +69.7% | |
| fresher (fewer days) | 118 | 54.2% | +77.6% | |
| beaten less last time | 115 | 49.6% | +57.6% | |

## market DECIDED (2nd 75%+ longer)

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 130 | 67.7% | +37.9% | |
| better class line | 99 | 61.6% | +56.0% | |
| rising lines (law 3b) | 51 | 51.0% | +45.1% | |
| class line, direction within a rung | 90 | 56.7% | +44.7% | |
| direction, then class line | 109 | 57.8% | +55.1% | |
| won last time out | 43 | — | — | under 50, no verdict |
| hotter yard (30d) | 88 | 54.5% | +32.9% | |
| hotter yard, else market | 130 | 59.2% | +34.7% | |
| hotter jockey (30d) | 94 | 45.7% | +21.3% | |
| fresher (fewer days) | 120 | 51.7% | +55.9% | |
| beaten less last time | 110 | 57.3% | +49.6% | |

## Cl3-4

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 105 | 62.9% | +57.4% | |
| better class line | 74 | 55.4% | +56.9% | |
| rising lines (law 3b) | 37 | — | — | under 50, no verdict |
| class line, direction within a rung | 72 | 52.8% | +46.6% | |
| direction, then class line | 84 | 56.0% | +58.5% | |
| won last time out | 32 | — | — | under 50, no verdict |
| hotter yard (30d) | 77 | 55.8% | +51.5% | |
| hotter yard, else market | 105 | 57.1% | +50.1% | |
| hotter jockey (30d) | 89 | 50.6% | +54.3% | |
| fresher (fewer days) | 96 | 49.0% | +53.6% | |
| beaten less last time | 92 | 51.1% | +51.3% | |

## Cl5-7

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 223 | 58.3% | +55.6% | |
| better class line | 162 | 49.4% | +48.4% | |
| rising lines (law 3b) | 117 | 50.4% | +62.3% | |
| class line, direction within a rung | 170 | 47.6% | +44.7% | |
| direction, then class line | 197 | 49.2% | +53.7% | |
| won last time out | 74 | 48.6% | +33.9% | |
| hotter yard (30d) | 135 | 56.3% | +78.4% | |
| hotter yard, else market | 223 | 57.0% | +68.0% | |
| hotter jockey (30d) | 150 | 44.0% | +46.2% | |
| fresher (fewer days) | 202 | 51.0% | +64.5% | |
| beaten less last time | 197 | 48.7% | +51.6% | |

## unclassed

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 51 | 58.8% | +85.2% | |
| better class line | 32 | — | — | under 50, no verdict |
| rising lines (law 3b) | 13 | — | — | under 50, no verdict |
| class line, direction within a rung | 30 | — | — | under 50, no verdict |
| direction, then class line | 37 | — | — | under 50, no verdict |
| won last time out | 10 | — | — | under 50, no verdict |
| hotter yard (30d) | 17 | — | — | under 50, no verdict |
| hotter yard, else market | 51 | 47.1% | +58.3% | |
| hotter jockey (30d) | 29 | — | — | under 50, no verdict |
| fresher (fewer days) | 44 | — | — | under 50, no verdict |
| beaten less last time | 44 | — | — | under 50, no verdict |

## code F

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 220 | 59.5% | +63.5% | |
| better class line | 158 | 53.2% | +67.9% | |
| rising lines (law 3b) | 110 | 55.5% | +79.2% | |
| class line, direction within a rung | 164 | 53.0% | +65.0% | |
| direction, then class line | 190 | 54.7% | +75.9% | |
| won last time out | 68 | 52.9% | +56.1% | |
| hotter yard (30d) | 131 | 56.5% | +78.4% | |
| hotter yard, else market | 220 | 57.7% | +72.3% | |
| hotter jockey (30d) | 150 | 47.3% | +56.0% | |
| fresher (fewer days) | 195 | 50.8% | +67.2% | |
| beaten less last time | 196 | 53.1% | +69.7% | |

## code H

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 119 | 56.3% | +39.8% | |
| better class line | 81 | 55.6% | +55.5% | |
| rising lines (law 3b) | 40 | — | — | under 50, no verdict |
| class line, direction within a rung | 80 | 46.2% | +27.5% | |
| direction, then class line | 95 | 51.6% | +44.1% | |
| won last time out | 35 | — | — | under 50, no verdict |
| hotter yard (30d) | 76 | 51.3% | +43.9% | |
| hotter yard, else market | 119 | 50.4% | +39.7% | |
| hotter jockey (30d) | 87 | 48.3% | +46.9% | |
| fresher (fewer days) | 112 | 50.0% | +56.7% | |
| beaten less last time | 99 | 50.5% | +54.7% | |

## code C

| rule | decided | strike | ROI at SP | |
|---|---|---|---|---|
| market's first (BENCHMARK) | 57 | 64.9% | +90.5% | |
| better class line | 42 | — | — | under 50, no verdict |
| rising lines (law 3b) | 18 | — | — | under 50, no verdict |
| class line, direction within a rung | 34 | — | — | under 50, no verdict |
| direction, then class line | 46 | — | — | under 50, no verdict |
| won last time out | 22 | — | — | under 50, no verdict |
| hotter yard (30d) | 36 | — | — | under 50, no verdict |
| hotter yard, else market | 57 | 52.6% | +65.5% | |
| hotter jockey (30d) | 46 | — | — | under 50, no verdict |
| fresher (fewer days) | 49 | — | — | under 50, no verdict |
| beaten less last time | 50 | 46.0% | +58.7% | |

---
Nothing above is a rule. A rule is born three ways only: the master teaches it, the master validates it, or the record field-tests it long enough to earn belief.
