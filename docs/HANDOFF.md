# HANDOFF — the apprenticeship's living memory

Last updated: **2026-08-09** (update this file whenever state changes — it is
how every new chat remembers everything).

## Who and what

- **William** (williamlillis100@gmail.com) — the master. 30 years' form
  reading. He teaches by short corrections, pasted race results, and blunt
  verdicts. Paper stakes ONLY until the record proves profit.
- **The system** — `racing_edge` on PythonAnywhere (`/home/v5racing/
  racing_edge`, user v5racing), branch `claude/tender-wright-kbn1h6`.
  Scheduled UTC: 07:30 nap · 09:30 health · 12:30 guard · 22:00 night
  (settle+study; Sunday adds synthesis). Two emails/day are the interface.

## The record (as of 2026-08-08 settle)

- ~9/24 settled naps (~37%), level stakes ≈ +15pt at SP. CONFIDENT picks
  ~44%, leans ~2/8. A 5-loss cold streak through early August broke with
  Poet's Dawn (Ripon, 2/1, 3 Aug).
- **Winners' profile** (the record's own numbers): honest UK handicaps,
  straightforward tracks (Thirsk/Ripon/Nottingham class), Cl3-4, exposed
  readable fields, SP 2.6–4.5. **Losers**: festivals (Galway), plot races,
  quirky tracks, and picks at 11/2+ (1 from 7).
- **The shadow A/B**: the mechanical engine's top survivor out-struck the
  deep reader's chosen picks (~45% vs ~36%) → caused THE FLIP (below).
- Oppose-clues keep landing (false favourites correctly called); follow-clues
  are 0-for-everything. Elimination is the sharp end of the toolkit.

## THE FLIP (live since 2026-08-08) — current selection regime

- **The engine selects the nap** (its top survivor — the exact selection the
  shadow scored with). No floors, no reader discretion over selection.
- **The reader (VETO_SYSTEM prompt) writes the case** and holds ONE power: a
  veto on a CITED disqualifying fact. "I prefer another horse" is not a veto.
  Every vetoed pick banks in the shadow column so the record judges the veto;
  health's **veto tripwire** reds a veto that killed a winner, and flags 3+
  vetoes/week as the old departing-disease.
- Every case OPENS with **MY PRICE vs market** (taught 2026-08-08: "why would
  you back a 50/1 shot?") — the daily calibration of our reading vs the
  compilers. In ~2 weeks the ledger can score it.
- Switch: `NAP_MODE=reader` restores the old hierarchy. REVERT-IF: engine-led
  naps 0/8 or strike < 36% over 15 settled.

## The master's taught laws now in the rulebook (NAP_SYSTEM/VETO_SYSTEM)

Rule One (best horse wins — find him); race-first + **the master's glance**
(never nap races he'd never look at: plot handicaps, festival cauldrons,
wall-to-wall moderate fields); **stack the cards** (winning profile + 11/2+
price tripwire, explicitly not a price wall); whole-jigsaw well-in doctrine
(one piece, veto only, corroboration checklist); manner beats bare figures;
eliminate first; beat the danger; OWED symmetric — a doubt is not a fact;
closed rulebook; own-price opens the case.

## OPEN QUESTIONS (chase these)

1. **2026-08-09 veto** — day one of the flip, the reader vetoed the engine
   pick on the week's best card (master furious). The vetoed horse banks in
   shadow and settles tonight; if it ran well the veto power gets cut/removed
   (pre-agreed). GET the veto lines from the master's email, grade the cited
   fact, act on the verdict.
2. **2026-08-03 ledger row** — Poet's Dawn won at 2/1 but a force-rebank may
   have replaced him intraday with a loser. Never resolved: check
   `nap --record` for what stands. LESSON (proposed law): the nap banks once,
   pre-off, and stands — no intraday re-picks.
3. **Aug 4–7 results** — never reported into this chat; the ledger knows.
4. **Master's pending rulings**: kill rule #19 (gamble-chasing, 74/103
   losing)? The blackout-race protocol (what to do when comments are all
   OWED)? ~79 doorbell nuances (learn --promote/--bin N). Saturday funnel
   widening (3→6 candidates on 20+ race cards) — approved in spirit, never
   confirmed; NOTE: engine-first may make it moot.
5. **30-pick verdict** — ~6 picks away: staking decision, lean rule,
   shadow-vs-deep conclusion, engine-glance mechanical ranking.

## Known suspects & lessons awaiting validation

- Reader biases (documented, twice-punished): exposed-safe over live
  improvers; doubt-as-fact against favourites; mark-led case spines (well-in
  0W/3L as spine; 65% as a tick).
- Short-price mirror tripwire proposed (Brighton View 2/5, 3rd in a 5-runner
  crawl): below ~1/2 every visible risk must be named small, or pass.
- Small fields: readable on form, fragile on pace — pace map is primary in
  ≤6-runner races (proposed).
- The engine's candidate menu is still conviction-shaped, not race-quality
  shaped (monthly-window item, with the master's filters).

## Infrastructure facts a new session must know

- Racing API: **Standard plan**. `/horses/{id}/results` is Pro → client
  auto-demotes to `/racecards/{horse_id}/results` (today/tomorrow horses
  only; past cards unavailable on Standard). MCP connector may also work.
- Models: nap = claude-opus-5 (full thinking, max_tokens 16000); study/
  sceptic sonnet-5 at effort LOW (Claude-5 family thinks by default and
  thinking bills from max_tokens — the empty-study bug of 2026-08-01).
  Budgets in `ai/reason.py`; usage in `data/model_usage.csv`.
- Fail-safes: crash emails (run_guarded), CI on every push, engineer's eye in
  health (runtimes/tracebacks), broom judged at 29 days, vote-freshness
  (re-derived lessons count), veto tripwire.
- 152+ tests pin every rule and every past regression. CI:
  `.github/workflows/tests.yml`.

## How to work with William (learned the hard way)

- He pastes: health emails, race results, racecards, task logs. Autopsy
  results Rule One style; grade freehand reads with the iron-rule audit
  walked out loud (OWED symmetric? price before form? cons are events?
  danger beaten? taught ticks at full weight?).
- When he corrects you, encode his words VERBATIM as taught law, with a test.
  When he's angry, own it in few words and show the fix — never explain.
- He measures you on winners. "Almost there but never there" is his 4-month
  wound — don't reopen it with promises; point at ledger numbers and dates.
- Commit style: message quotes the incident/teaching + REVERT-IF; ends with
  the Co-Authored-By + Claude-Session lines (see git log).
