# Research notes — what we learned, and what we adopted

Synthesis of a multi-agent research sweep (academic + practitioner sources) into
the evidence behind this system's design. Findings converged hard across the LLM,
quant-model, value-betting, market-mechanics and academic-efficiency strands.

## The headline: our architecture is what the evidence supports
- **LLMs are readers, not predictors.** GPT-4 in a real forecasting tournament
  scored no better than assigning 50% to everything (Schoenegger & Park 2023). No
  credible study shows an LLM win-prediction edge in racing. LLMs *are* strong at
  reading unstructured text (comments, spotlight, intent) and extracting structured
  fields — the finance-sentiment literature backs this division. → **AI fetches,
  reads narrative, and explains with citations; it never picks or scores.**

## Closing-Line Value is the proven north star
- The closing line/SP is a well-calibrated, near-efficient forecast (Thaler-Ziemba
  1988; Pinnacle ~0.997 calibration; Buchdahl). Beating it consistently = skill.
- **CLV proves an edge in ~50–100 bets; P&L needs ~300–500+** (variance-free vs
  results). Track **(a) % of bets that beat the close** and **(b) mean CLV %**.
  Sharp bar ≈ **60%+ beat-rate over 200+ bets**. → baked into `measurement`.
- De-vig before comparing (power method for racing) so the ~15–20% over-round
  doesn't pollute the signal. (TODO when we wire live SP capture.)

## The favourite–longshot bias is real, signed, and validates our value band
- Backing favourites loses ~5%; longshots ~40%+ (Snowberg-Wolfers, 5.6M starts;
  Thaler-Ziemba). Our own live finding — the 6.0+ band bled −68% — was **not a
  fluke; it's a known law**. → the betting value range avoids the longshot bleed
  zone; favourites are still −EV at SP, so we need a *price*, not just a winner.

## Steamers win slightly more — but following them is NOT profitable
- Steamers win ~3–5.5% more than drifters, but strong steamers still **lost ~13p
  in the £**; the market prices the move in (geegeez; market-efficiency lit).
  Late/informed money is real but you can't profit by chasing it. → **the value
  is in the EARLY price.** We tempered the steamer signal to mild confirmation
  (+1) and take the early price; a big drift is a genuine warning (−2).

## Take the early price, line-shop, plan for the exchange
- BSP beats bookmaker SP ~86% of the time (~10–14% better on average, far more at
  longshots). Best-Odds-Guaranteed = no downside vs SP. → bet early, not at SP.
- Bookmakers **gub winners** (~4.3% of UK accounts restricted; stake-factored to
  1–9%). The exchange never limits winners but charges ~2–5% commission and a
  **Premium/Expert charge up to ~40%** on the biggest winners. The exchange is the
  long-term home; the honest ceiling is lower than the marketing suggests.

## Staking: flat/fractional, never full Kelly on a noisy edge
- Full Kelly on an overestimated edge over-bets and courts ruin (2× Kelly = zero
  growth). Pros cap at ~¼–½ Kelly, ≤~2.5% of bank. → flat 0.5%, **Kelly OFF**
  until CLV proves a stable edge over a few hundred bets.

## The biggest killer is overfitting — which is exactly what wrecked v3
- Data-snooping (test 10 ideas, keep the survivor) and look-ahead bias (using
  closing odds in a backtest) manufacture false edges. **Never trust < 300–500
  bets across seasons.** → walk-forward, season-stratified, pre-registered
  segments, no hard-coded window-findings. The architecture gate + honest ledger
  enforce this.

## Realistic ceiling (the honest line)
- Legitimate individual edges are single-digit % ROI over large samples; treat any
  double-digit claim with deep scepticism. Even Benter relied on rebates (~10%+)
  and scale retail punters can't access. The achievable win is a **disciplined,
  ruin-proof process whose CLV honestly tells you whether the picks contain a real
  edge** — not riches.

_Sources: Snowberg & Wolfers (JPE 2010); Thaler & Ziemba (JEP 1988); Levitt (EJ
2004); Schoenegger & Park (2023) & Science Advances (2024); Management Science
(2024) line-overreaction; Buchdahl/Pinnacle on CLV; geegeez steamers/drifters;
UK GC 2025 restriction study; Betfair commission/Premium-charge docs._
