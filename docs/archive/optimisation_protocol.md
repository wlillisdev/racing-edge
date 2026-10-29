# Optimisation protocol — improving the method WITHOUT overfitting

Distilled from two adversarial research agents (a methodology designer + a
red-teamer). The point: *a backtest is not evidence of an edge — it's the upper
bound on how good the edge could possibly look.* Reality is always worse. Every
rule below stops the gap between backtest and live from being a surprise.

## The two non-negotiables
1. **CLV (vs BSP) is the primary judge.** Beating the closing line is the closest
   thing to an overfit-proof signal, and it converges far faster than ROI. ROI vs
   the same-race favourite is the secondary judge. (We currently settle vs SP —
   BSP is the cleaner target, a known fix.)
2. **The test set is touched exactly once, at the end.** The most insidious trap
   is the human peeking, tweaking, and re-checking — *your eyeballs are a
   gradient-descent step.* Once you change the method having seen the hold-out,
   it's burned.

## The split
- Walk-forward by **race-day** (all of a day's picks fall in one block).
- Multi-season if available (train S1, test S2, …; quarantine the latest season).
- One winter only → chronological **50/25/25** train/validation/test, and accept
  the test is underpowered → the real exam is **paper-trading next winter live.**

## The experiments (in order, each PRE-REGISTERED in git before running)
- **A. Signal ablation** — leave-one-out: a signal earns its place only if
  removing it *hurts* held-out CLV beyond the bootstrap band. Expect several of
  the 18 to be noise → drop them as one pre-registered action. (True ablation
  needs a re-pick run; `analyse.by_signal` is the cheap associational cue first.)
- **B. Conviction threshold** — a COARSE 3-value grid (median/60th/75th), not a
  fine sweep. (`analyse.by_conviction`.)
- **C. Race-context** — ≤4 pre-written hypotheses (handicaps, small fields), each
  counted in the testing budget.
- **D. Weight re-tune** — only with heavy shrinkage toward the hand-set weights,
  signs locked, coarsely rounded; keep hand-set weights on a tie. At most once.

## Statistical guards
- **Sample gates:** ≥100 picks to *act*, ≥300 to *trust*; <30 isn't even a
  direction. (`analyse`/`metrics` flag thin cells.)
- **Bootstrap CIs**, block-resampled by race-day; an effect is real only if its
  CI excludes zero.
- **Multiple-testing correction (Benjamini–Hochberg)** across *all* ~25 tests —
  50 worthless tests yield ~2.5 false "edges" at p<0.05.
- **Effect-size realism:** a backtested ROI edge >5–8% over the favourite is
  suspicious, not alpha.

## The leak checklist (run before believing any improvement)
- [ ] Every signal frozen point-in-time (no post-race / whole-period data). *(Our
      backtest filters horse history `as_of` the race, and SKIPS the current
      trainer-A/E/jockey endpoint, which would leak. The card's 14-day form is
      point-in-time and kept.)*
- [ ] Settlement at **BSP net of commission**, not industry SP. *(SP today — a
      known optimism; fix to BSP.)*
- [ ] Universe built from declarations (non-runners/voids/Rule 4 modelled), not
      from results.
- [ ] Locked hold-out, consulted **once**; all tuning on train/validation.
- [ ] Test count registered; corrected significance; coarse/constrained weights.
- [ ] ROI with a bootstrap 95% CI; no claim under the sample gate.
- [ ] Edge isn't concentrated in one month/ground/trainer (walk-forward holds).

## Stop rules — what "no edge, accept it" looks like
Declare no transportable edge if, on held-out data: CLV CI doesn't clear zero and
beat-the-close ≤ ~50%; OR the favourite isn't beaten; OR no signal's removal
hurts CLV; OR the edge only lives in <100-pick cells. "Accept it" = keep the
method as a transparent decision aid, **stake nothing on a failed edge.**

## Honest base case
Given the negative-CLV pilot, the prior is that little or no transportable edge
exists. This protocol exists to find one *if it is real* — never to manufacture a
good-looking backtest. The cleanest confirmation of anything that survives is
forward paper-trading on a fresh winter, recording taken price vs BSP in real time.
