# Greyhound Engine (v0)

A new selection system for graded greyhound racing (primary target: Greyhound
Racing Ireland tracks, e.g. Curraheen Park; the same engine covers GBGB
racing), bootstrapped from the lessons of the horse racing NAP model in this
repo. The horse system is the
prior art, not the parent — nothing here imports from it.

## What transfers from the horse system (and what doesn't)

| Horse-system lesson | Greyhound translation |
|---|---|
| Score bands must be calibrated by backtest, not intuition | Same 0–100 scale, same band methodology. Weights below are PLACEHOLDERS until we have logged results. |
| Form franking — judge a race by what the field did next | v1 feature. Needs a results log first; same subsequent-winners logic. |
| Pipeline honesty — verify outputs, no silent failures | Scorer refuses to score a card with missing critical fields rather than guessing. |
| Market drift protection | v1 — needs a price feed or manual late prices. |
| Key-name drift killed the horse pipeline | One canonical card schema (`card_template.json`), validated on load. |

Not transferable: jockey/trainer combos, weight, OR handicapping, stamina
profiles, draw bias by course geometry. Greyhounds are a different problem:
**6 traps, ~30 second races, early pace and trouble-in-running decide most
graded contests.**

Irish specifics (GRI): distances in yards (Cork: 330/525/575/750), grades
A1–A9 with S grades for sprints. The scorer treats distance as a plain
number in the card's native unit and grades as letter+number, so both codes
work unchanged.

## v0 scoring components (weights uncalibrated — DO NOT bet these bands yet)

| Component | Range | Rationale |
|---|---|---|
| Early pace (best recent split, ranked in field) | 0–30 | Sectional to the first bend is the single biggest edge in graded sprints. First to the bend avoids trouble. |
| Time form (best recent calc time at tonight's distance) | 0–30 | Calculated times normalise going; best raw ability measure on a card. |
| Trap / running-style fit | −10 to +10 | Railer drawn 1–2 good; wide runner in 6 good; wide runner drawn 1–2 actively bad. |
| Grade edge (dropping vs rising in grade) | −10 to +15 | A dog dropping from A3 to A4 meets weaker; grade inflation is the greyhound form franking analogue until we have real franking. |
| Recency / fitness | −10 to +5 | 4–14 days between runs ideal; 28+ days a negative. |
| Consistency (top-2 finishes in recent runs) | 0–10 | Graded dogs are creatures of habit. |
| Race comments | −8 to +8 | Trouble (Crd/Blk/Bmp) in a beaten run is an excuse; StyWl/FinWl/RnOn marks a dog that keeps finding; Fd one that empties; QAw/SlAw trap habits. |
| Running lines (SPi) | 0 to +8 | Half for early position taken, half for ground made through the race. Late passers thrive in trouble races. |
| Draw bias (learned) | −5 to +5 | Per track+distance trap win-rates from `results_log.csv` via `log_result.py`. Silent until 30+ logged races — never guessed. |

Also emitted per race: a **pace map** (predicted order to the first bend) and
a **crowding flag** when 3+ early-pace dogs are drawn adjacent — those races
are coin flips and should be no-bet regardless of scores.

## Calibration plan

1. Score tonight's card(s) blind, BEFORE the races.
2. Log predictions + results in `greyhound/log/` (same discipline as
   `performance_log.csv` on the horse side).
3. After ~100 scored races, run the band analysis (which score bands are
   profitable at SP) — identical methodology to the horse backtest that found
   the 70–79 band.
4. Only then set stake rules.

## Usage

```bash
python greyhound/scorer.py path/to/card.json
```

Card format: see `card_template.json`. Minimum viable data per runner:
trap, name, and recent runs with (position, split, calc_time, grade,
days_ago). Running style (R/M/W as printed on UK cards) strongly recommended.
