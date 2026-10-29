# DOWN TO TWO — the four bots' report (2026-09-05, evening)

The master: "I picked a story over the best form line. same story we need to
change the record, we have the short list and have properly found the right
horses for a short list but are struggling to pick the right one, can you
send out some bots to see if you can get to the bottom of this, this is the
final piece in the jigsaw so it deserves time and effort, as it needs a fix
once and for all."

Four bots, four doors, one evening. Nothing below is carved. Every cut is
FOR HIS RULING.

## 1. The record (34 settled sittings with a pick and a named danger)

| | n | % |
|---|---|---|
| pick won | 10/34 | 29 |
| named danger won | 8/34 | 24 |
| pick or danger won | 18/34 | 53 |
| second danger won | 1/8 | 13 |
| winner outside the shortlist | 13/34 | 38 |
| of those, SEEN and crossed off on a named rule before the off | 9/13 | 69 |

In the nine races where a danger beat the pick: the winner had the higher
class line in 3 (2 the other way, 4 sheets too thin to say); the pick having
MORE runs was NOT one-directional (2 for, 2 against); the winner went off the
market's first or second choice in 6, usually having shortened from the
morning; "what would make me wrong" named the winner's exact scenario in 3 of
the 4 sheets that carry the line, and the pick stood anyway.

The shortlist is right more than half the time and the read sees the winner
in eight races of ten. The verdict is the fault.

## 2. The engine (the code that chooses)

Between two candidates in one race the key is, in order:
`confident → mark_known → lens families → raw labels → shorter price`
(pipeline/nap.py:184-193). Four volume terms and the market. There is NO
class term. `PastRun.race_class` reaches the score only AGAINST (the raised
mark, the class hike). `MarkRead.win_class` — the class of the last win — is
computed on every runner every morning (domain/mark.py:77) and thrown away.
The card's rpr and performance_rating are parsed and never scored. A
class-aware module (domain/profile.py: class_drop +4, quality_of_win +2) is
dead code, reachable only from a test. `improver-favourite (unexposed, short
price)` is a FLAG: the once-raced Godolphin/Appleby/Buick profile is crossed
off before any tie-break runs, against the rulebook's own words ("the
species question decides"). `pattern` (Group 1/2/3, Listed) is in the feed on
both doors, verified live tonight, and parsed nowhere — so a Group 1 winner
and a Listed winner are both `race_class = 1` and invisible to each other.
`race_quality` gives a pattern race neither the handicap +1 nor the Cl3-4 +1,
so the best races fall below the betting bar most easily. BEAT THE DANGER
binds only the case-writer, who cannot re-pick since the flip: the system can
name a danger it admits it cannot beat and bank the pick regardless — today's
five from six, mechanically.

## 3. The corpus (1,509 scorable races, no look-ahead)

Nothing beats the favourite (33.1%, −13.4% ROI). Over the SAME races a
mechanical "best class line" horse bleeds 3.4–5.2 points of ROI to the jolly;
a "most form lines" horse bleeds 13.6–14.8. The direct head-to-head inside
the market's first two: 37 wins each on 141 races — unresolved. The corpus
cannot answer: mean prior runs per runner 0.95, 48% of runners have no
history in it, only 19% carry a class line, April–July near-empty. The cells
that looked alive (a class dropper that placed last time, +5.4pp lift, month
test holds; a non-favourite in the first three with a better class line than
the jolly, +3 to +4pp) sit at n=83–228, under the 500 bar.

## 4. His own words, in the order they rank (bot D, every step sourced)

best horse wins (07-26, 08-30, 09-03) → past winners give the shape (08-31,
09-05) → class is permanent, form is temporary (08-22, 09-05 Kempton) →
down to two, pound-a-length (08-24) → floors and ceilings, class horses run
well fresh (08-29) → beat the danger honestly or it IS the pick or pass →
the Blanco line, never skip the figures horse (08-29, 09-05) → the
bookmaker's question, "the bookies tricked you" (08-16, 09-05) → the market's
direction, flip-flop never goes well (08-15, 08-30) → pass and name the kill.
Two live tensions in his own rulings: the odds-on bar v "a great case at
odds-on should not be ruled out"; the Past Winners weight DNA v the class
tell (Ascot 2:10 and Haydock 3:05 gave opposite right answers the same day).

## 5. THE FIX, IN ORDER — for his ruling, one cut a day

1. **Parse `pattern`** (Group 1/2/3/Listed) onto Race and PastRun.
   Measurement only; two lines in the normaliser. Without it the class
   ladder above Listed does not exist in the system.
2. **The class tie-break.** At equal `confident`, `mark_known` and family
   score, the horse whose last win came at the higher class wins the tie
   (`-(win_class or 9)` inserted before the raw-label count; suppressed when
   the win is STALE, an existing receipted quantity). Zero new thresholds.
   Graded FIRST as a yardstick signpost key ("best win Cl1-2 / Cl3-4 /
   Cl5-6") against the market before it moves the key; test fails with the
   bug put back; REVERT-IF over the next 15 picks; live check the same day
   (print the top two by old and new key, confirm an order changes).
3. **Demote `improver-favourite` from flag to caution** — the standing
   demotion law, applied four times already in the same file; the FLAGS
   table in the yardstick grades it (lift should be negative; if it is
   positive the flag is crossing off winners). Also: it reads the all-codes
   history while its neighbours read same-code — fires unevenly.
4. **BEAT THE DANGER with teeth.** His rule 8 in his words: "if you cannot
   beat the danger honestly, then the danger IS the pick, or the race is a
   pass." Today the case-writer's "cannot beat" changes nothing. His ruling:
   does an un-beaten danger PASS the race (the method), or does it stand as
   LEAN (today)? Nothing moves without his word.
5. **`race_quality` stops penalising pattern races** — a Group/Listed race
   scores at least what a Cl3-4 handicap scores. His ruling (it is the bar).
6. **Backfill the corpus to the door's 12 months** (Sept 2025 onward), free
   within the plan, so the numbers can judge 2 and 3 with a real history
   behind every runner; then re-run the corpus test.

What none of this changes: the sittings. There the fault is mine and the
discipline is written in every settled sheet from today — one decisive line
per principal, the danger's line weighed against the pick's on the page, the
class line first, "what would make me wrong" written before the verdict.
