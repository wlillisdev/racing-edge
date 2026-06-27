# ML research findings — verified, salvaged from the deep-research run

The deep-research pass ran 106 agents over ~50 min, fetched and read the sources,
and adversarially verified ~75 claims (8 refuted, 67 survived). The final
synthesis step crashed, so this is reconstructed from the verified claim set. It
goes deeper than the original 8 links — it pulled the foundational Benter /
Bolton-Chapman papers, the CLV-validation literature, the leakage paper, the
Betfair-efficiency study, and the staking literature.

## Source-by-source: what's PROVEN vs merely engineered

### Conditional logit (Benter / Bolton–Chapman) — the genuinely proven base
- Bolton & Chapman (1986), Benter (1994): a **multinomial / conditional logit**
  produces win probabilities that **sum to 1 within each race** from fundamental
  factors. This is the canonical, transparent, within-race base. **Verified across
  multiple primary sources.**
- **The edge was in COMBINING with the market, not replacing it.** Benter's winning
  method is *two-stage*: stage 1 estimates strength from fundamentals; stage 2 is a
  second clogit whose two inputs are the stage-1 probability **and the public's
  implied probability**. Benter explicitly treats public odds as a powerful baseline
  to refine, and emphasises **calibration** (estimated prob should match observed
  win frequency) as the quality criterion. **This is the single most important
  finding for us.**

### chris-alex-p/german-horse-racing — real, transparent, but a *tiny, fragile* edge
- It is a **single-stage** clogit with race strata (softmax over runners), odds
  excluded during stepwise-AIC selection then **added back as one term** — NOT the
  true Benter two-stage blend (the "mirrors Benter" framing was **refuted**).
- Readable coefficients confirmed (market odds −0.0835 p<0.001; recent speed
  +0.006; amateur jockey −0.561). **Transparency advantage is real.**
- **The market carries information nothing else replaces:** concordance rises
  **0.682 → 0.738** only when odds are added. The fundamentals add *modestly* on
  top of the market.
- Profit is **weak and not credible for us**: €54.9 over 914 flat €1 bets vs a
  €137 expected loss under 15% takeout, bootstrap p=0.02, **no CLV, no slippage**,
  author concedes it's **fitted to one narrow segment** (Ausgleich IV turf) and
  large bets move the price.

### gmalbert/horse-racing-predictions — best engineering reference; honest about itself
- Stacked **XGBoost/LightGBM/ExtraTrees + Platt calibration**, strict temporal
  walk-forward, UK 2015–2025, ~75 features. **Verified.**
- The "88.5% accuracy" is the **class-imbalance trap**; the honest number is
  **ROC-AUC ~0.671 base / 0.689 ensemble** — modest discrimination.
- **Value-betting / ROI is deliberately disabled** because no real odds are joined:
  the repo makes **no profitability claim**. (Intellectually honest.)
- Leakage protection (`.shift(1)`) is **real but NOT universal** — its OWN
  `DATA_LEAKAGE_AUDIT.md` flags **six sire/pedigree features as leaking** (the
  "shifts ALL features" claim was **refuted**). **Lesson: pedigree features are
  high-leakage-risk even in a careful repo.**

### Ransaka/LTR-with-LightGBM — NOT a horse-racing project
- **It is a LambdaRank tutorial on an anime-recommendation dataset.** No racing
  data, features, or results. The **mechanism transfers** (group=race, item=runner,
  relevance=finishing position; needs the LightGBM `group` param and graded-int
  relevance) but it **proves nothing about racing**.
- Evaluated only on ranking metrics (MAP@1 0.888 / NDCG@1 0.876); **raw LambdaRank
  scores are NOT calibrated probabilities** — a separate calibration stage is
  mandatory before any value read.

### SSRN Plackett–Luce UK paper (6860338, "June 2026") — COULD NOT be verified
- The research run did **not** surface or confirm this paper. The "strongest design"
  is **unconfirmed** — treat Plackett–Luce as an interesting *optional research*
  direction, **not** a committed build, until the actual paper is in hand.

### Silverman & Suchard (2013) regularised clogit + frailty, "36.73% ROI"
- Numbers are real (3,681 HK races) but **refuted as adoptable for us**: a 2013
  paper, train/test framing conflated (hold-out year vs 10-fold CV), **ROI not CLV**,
  HK pari-mutuel. The interesting idea — **optimise for profit, not likelihood, via
  LASSO** — is unproven out-of-sample for our context.

### dickreuter/betfair-horse-racing — feature ideas only, no proven edge
- NN whose loss optimises **back/lay payoff incl. commission**; features are
  **Betfair price-time-series stats** (mean/min/max/median/std/skew/kurtosis,
  last-traded snapshots) from 60 min out. **No metrics reported** — only cumulative
  P&L plots; one specific feature detail was **refuted as fabricated**. Use for
  feature *concepts* only.

### tarb/betfair_data — real, fast ETL tool
- Rust+Python parser for Betfair historical files, **~10× faster** than
  betfairlightweight (~70 vs ~6 markets/sec). Pure parsing — **no model**. Useful
  only when/if we build the market-movement layer.

### BBE XGBoost (SSRN 4691617) — simulation only, in-play, later-phase
- XGBoost learns **in-play dynamic wagering** by imitating profitable sim-agents and
  generalises to beat them **within the Bristol Betting Exchange simulation** — **no
  real-market, obtainable-price, or CLV validation.** Relevant only to a much later
  in-play/trade-timing phase.

## Cross-cutting, well-supported principles

- **CLV is a valid, fast edge judge.** Buchdahl's ~20,000-bet system: 4.0% CLV-
  implied edge vs 3.4% realised ROI — empirically consistent. CLV can reach
  significance in **~50 bets** vs thousands for raw P&L. **Caveat:** only meaningful
  against a properly **de-vigged** sharp closing line.
- **Random train/test splits leak and inflate performance** (Quantitative Finance
  2022, demonstrated experimentally). **Walk-forward / forward-chained only** — even
  for a simple model.
- **The market is a hard benchmark** — but the Betfair-efficiency paper does **NOT**
  prove it's unbeatable (that inference was **refuted**); it only shows price-return
  series are statistically efficient with **mean-reversion** (so price-momentum
  features are unlikely to carry durable signal).
- **Staking matters: fractional / adaptive Kelly** beats flat staking; drawdown-
  constrained Kelly ≈ plain fractional Kelly (so keep it simple).

## What this means for us (the honest bottom line)

Every robust, transparent, historically-real edge in this literature is **Benter's
shape**: a conditional-logit win-probability model **blended with the market**,
judged by **calibration + CLV**, under **strict walk-forward**. The fundamentals add
only **modestly** on top of the market (0.682 → 0.738). The big profits required
either **scale + rebates** (Benter HK) or were **tiny and segment-overfit** (German
turf, €54.9/914 bets, no CLV). For a small operation, the realistic expectation is:
the blend may **modestly beat fundamentals**, may **roughly match the market**, and
any real money lives in **execution / price-capture (CLV) and disciplined staking** —
exactly what our CLV harness already measures.
