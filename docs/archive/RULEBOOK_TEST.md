# HIS RULEBOOK, TESTED ON FAVOURITES — 27 September 2026

The master, 27 Sep: *"u have the full form read we have been teaching you for
last 6 months ... u reframe it and how u implement it"* and *"u can test it
properly from today, u can get all the information needed"*.

**The verdict: the favourite filter, as it stands, already picks the winner
with its nap about 44% of the time. Adding the other rules on top makes its
picks worse, not better. The filter stays as it is.**

## The data

`data/archive/results_2026.csv.gz` — every GB and Irish race from 1 January to
26 September 2026 (9,600 races, 87,795 runners) with the fields the old
corpus never kept: **draw, weight, official rating, age, going, headgear,
trainer, jockey**. Re-run everything below with:

    PYTHONPATH=src python -m racing_edge.school.rulebook_test

Favourites at evens or bigger only (his odds-on ruling). History built from
earlier days only. Two periods judged apart: **1 Mar – 14 Aug** and
**15 Aug – 26 Sep**. A rule HOLDS only if it points the same way in both,
clearly (z ≥ 1.5 in each).

## 1. Rule by rule — does it separate winning favourites from losing ones?

| rule | fires: Mar–Aug | 15 Aug on | verdict |
|---|---|---|---|
| 6 class 1–4 preferred | 33.6% v 30.5% | 34.8% v 28.0% | **HOLDS** |
| 3i young fav already exposed (≤4yo, 7+ runs) | 26.0% v 32.9% | 25.8% v 32.7% | **HOLDS** (against) |
| 2b-ii SOLID, all five parts | 33.1% v 30.9% | 36.7% v 29.7% | same way, weak |
| 3g at/below last winning mark | 35.0% v 28.5% | 33.0% v 29.2% | same way, weak |
| 3e carries top weight | 34.7% v 30.2% | 32.3% v 30.0% | same way, weak |
| 3f drawn in course's worst third | 28.3% v 31.6% | 27.7% v 31.2% | same way, weak |
| 3g first run off a raised mark | 28.5% v 30.7% | 28.4% v 29.7% | same way, weak |
| 3h placed at today's course | 29.8% v 31.6% | 28.0% v 31.8% | **the wrong way, both** |
| off the track 60+ days (a −1 dot in the filter) | 31.9% v 31.1% | 37.7% v 30.2% | **the wrong way for the dot** |
| has actually won · trip · going · a rival won LTO · last two improving · course jockey · best draw | | | flip between periods |

## 2. The real question — do they make the filter's picks win more?

The filter's picks exactly as it runs live (top two a day, the nap first):

| | Mar–Aug top-2 | nap | 15 Aug on top-2 | nap |
|---|---|---|---|---|
| **the filter as it is** | **38.9–39.8%** | **43–44%** | **44.2%** | **44.2%** |
| + all six rules that pointed the right way | 37.1% | 40.7% | 40.7% | 44.2% |
| + class 1–4 alone | 38.3% | 38.9% | 46.5% | 44.2% |
| + each of the other five alone | worse or level in at least one period | | | |

Why: the rules DO separate winning favourites across the whole card, but the
filter's own dots (and the market) have already found those horses. Adding
them again re-sorts the top of the list on weaker evidence.

## Honest limits

- The favourite here is the **SP** favourite; live, the filter reads the
  07:30 price. Some days they are different horses.
- Run comments were available for **39%** of the favourites' last runs, so
  the comment dots fired less often here than they do live.
- The nap figure moves by one or two picks with the order ties are broken
  (same score, same price) — hence 43–44%, not one number.
- Not testable from results at all: the market moves (flip-flops, boosts).

## For his ruling (reported, not changed)

Two of the filter's own dots run the wrong way on this data: **off 60+ days**
(−1 in the filter; those favourites won *more*) and his **3h course form**
(placed at the course won *less*). Neither is significant alone. Both are
his rules; they stay until he says otherwise.
