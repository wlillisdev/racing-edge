# Winter session — validation plan & open leads

Handoff from the 2026-06-14 session. Everything below was found on a **51-day
summer-flat** deep backtest (2025-06-18 → 2025-08-07, cached). All of it is
**in-sample** and must be confirmed on a **winter / National Hunt** window
before anything changes live.

## Live state right now (do not assume changed)
- **Config C is live** on production: `nap_min_score=44`, drop **Class 3/6/7 +
  unclassified**, drop **chase + hurdle**, no going filter. Confidence/grades
  map 44→MEDIUM, 47→MH, 50→HIGH. Backtest (in-sample): daily-NAP **54.5% win,
  +48.5% ROI**.
- **Component weights are all 1.0** (the reweight below is built but OFF).
- Live form depth raised to 50 results/horse (matches the backtest).

## The two strongest leads to validate on winter (in priority order)

### 1. `topped_out` exclusion — the weight/ahead-of-mark read  ⭐ headline
`handicap_trajectory()` (in `nap_selector_v3.py`) classifies a pick as:
- `topped_out` — has only WON **below** today's class (caught by the handicapper)
- `neutral` / `live_winner` — has won **at today's class or higher** (proven)

In-sample split (floor-44 pool):
| traj | n | win% | ROI |
|---|---|---|---|
| neutral (proven at level) | 95 | **45.3%** | **+13.2%** |
| topped_out (only won lower) | 54 | **27.8%** | **−9.8%** |

→ **Validate:** does excluding `topped_out` hold cross-season? If yes, add it as
a NAP exclusion (same as Class 3) — it targets "places not wins" directly.

### 2. Trainer over form — the reweight
`winner_vs_placer.py` showed (consistent across floors 44 & 35): trainer score
separates **winners**, raw form separates **placers**. The experiment
`--weights '{"trainer":1.6,"form":0.7}'` lifted daily-NAP win 54.5%→**68%** and
ROI +48.5%→**+82%** in-sample.
→ **Validate:** re-run with `--weights` on winter; if the win-rate lift holds,
dial trainer-up/form-down into live `component_weights` (then re-calibrate the
floor — reweighting shifts the score scale).

## Refinement needed
- **"well-in" definition is weak.** Currently `weight_vs_last <= -2` (carries
  less than last run) — almost never fires for improving top-scorers (they go UP
  in weight as they win), so `live_winner` was empty. Redefine "well-in" as
  weight **vs today's field** and/or **OR vs recent winning mark**, not vs last
  run. Then re-test the two-part well-in-AND-ahead-of-mark verdict.

## Bigger direction (the user's standing ask)
Stop scoring "who fits this race" (a placer-finder); read "who is **ahead of
their mark / ready to win**" (weight-first), and let that **lead** selection
with the quant as a sanity check — instead of the AI form-read being capped at
±3 and never allowed to override. The trajectory read + trainer signal are the
two ingredients; winter validation decides if they lead.

## How to run the winter validation (disk-safe)
Winter results-only — **no `--deep` per-horse pull** (that 11GB pull is what
filled the disk; it's dead at day 50/361, leave it). Steps once winter racecards
+ results are cached for the window:
```
python historical_backtest.py --start <winter-start> --end <winter-end> --deep --min-score 1
python calibrate_thresholds.py data/backtest_<...>_deep.csv          # floor + Config A/B/C
python winner_vs_placer.py --min-score 44 data/backtest_<...>_deep.csv   # trainer vs form
# trajectory split (topped_out vs neutral):
python3 -c "import csv,collections;rows=[r for r in csv.DictReader(open('data/backtest_<...>_deep.csv')) if r['has_result']=='True' and float(r['score'] or 0)>=44];g=collections.defaultdict(list);[g[r['traj']].append(r) for r in rows];[print(k,len(v),round(100*sum(x['is_win']=='True' for x in v)/len(v),1)) for k,v in sorted(g.items())]"
# reweight test:
python historical_backtest.py --start <winter-start> --end <winter-end> --deep --min-score 1 --weights '{"trainer":1.6,"form":0.7}'
```

## Tools built this session (all on branch claude/tender-wright-kbn1h6)
- `scoring_healthcheck.py` — empirical scorer audit (catches silent dead components)
- `calibrate_thresholds.py` — ROI-by-score-floor sweep + Config A/B/C evaluation
- `winner_vs_placer.py` — factor separation (aligned to Config C pool)
- `historical_backtest.py --weights` — in-memory component-weight experiments (never persisted)
- `nap_selector_v3.handicap_trajectory()` — well-in & ahead-of-mark read
- component-weight knob in `src/model_params.py` (default 1.0)

## Housekeeping
- Merge `claude/tender-wright-kbn1h6` → `main` so main reflects this work.
- Forward live results of Config C ARE out-of-sample data — track the next
  ~15–20 NAPs (win vs place) as a real-world check alongside the winter backtest.
- Dead deep-pull cache `data/backtest_cache` (~1.6 GB) — keep for now; powers
  the summer backtest. Remove if disk is needed.
