# HANDOFF — the apprenticeship's living memory

Last updated: **2026-08-15** (update this file whenever state changes — it is
how every new chat remembers everything).

## 2026-08-15 — THE SCHOOL (new standing method, master-dictated)

The master dictated a self-testing method, adopted exactly (see
`docs/SCHOOL_BRIEF.md`, `src/racing_edge/school/`): Phase 1 mines every
stored result leakage-guarded (signals alone and in pairs, n/strike/ROI at
SP, month-split — sign-flippers discarded; most stable positive cell at
n>=800 becomes THE RULE). Phase 2 sits daily exams on past cards with
results withheld, marks against the SP-favourite benchmark, categorises
misses, appends numbered brief corrections only for 3+ repeat faults
(master-taught corrections are exempt). Standing laws in his prompt of
2026-08-15: nothing graduates to real selections without beating the SP-fav
benchmark over 500+ unseen races (or a Phase-1 cell at n>=800
month-stable); judge nothing under 50 picks; every mechanical rule gets
coded and run for free; one line per exam day in docs/SCHOOL_RECORD.md.

State: tooling committed and tested (mine/pack/mark/fetch). Corpus fetch
via MCP haiku agents STALLED at 46/226 days (rate-limit collision from
launching 13 at once — Aug 2-11 "empty" files are that bug, not no-racing).
CHEAPEST PATH: run `school/fetch.py` on PythonAnywhere (direct API, already
paid) instead of re-fetching through credits. Phase 1 mine + exam round 1
NOT yet run.

Two taught laws born tonight (Market Rasen 5:30, Centurion's Sister won by
10L, flip-flopping fav nowhere): 4b THE FLIP-FLOPPING FAVOURITE
('favourite was flip flopping never goes well') and 4c THE SHAPE WE HUNT
('type of race we can get value and winners... short favourite flip
flopping, the rest 3/1, 4/1') — both verbatim in morningread.py, pinned by
tests. NOTE: live server runs branch claude/tender-wright-kbn1h6; tonight's
work is on claude/resume-handoff-docs-ayas2r — the 07:30 nap will NOT carry
these laws until merged and deployed.

Freehand paper picks today (grade separately, not ledger): Ghasham 7/2,
Market Rasen 6:34 (result unknown at write time); Park Hall read in the
5:30 LOST to Centurion's Sister — sitter's fault logged in brief v2 #10
(maiden 'wins' not verified by sphere).

THE BETTING-RACE FINGERPRINT (2026-08-17, mined from 1,978 scored corpus
races on the master's order — 'you can surely mine results to see what
type of races worked best'; shipped on his word: 'lets go'): form holds
where the market is CONCENTRATED (top-3 conc >0.75: winner in front three
79% vs 45-55% open — the strongest signal), in Cl3-4 (fav 38.2%, top-3
73%), in fields <=11 (12+ collapses to ~55% — shape-bet territory only),
in chases and flat over hurdles (hurdle fav ROI -26.5%), and NOT in
unclassed IRE races (fav -22.6%). Now scored in race_quality_score()
(pipeline/nap.py) leading the engine's rank. THE TRAP CAVEAT (his words:
'the bookies lay the traps for favourites... very few of your picks were
favourites, many were second or third favourite — the benefit of reading
the form finding the gems'): blind 2nd-favs lose -13.8%, ours built
+13.4pt — the ~50-point reading premium lives at ranks 2-3 behind the
trapped fav. The score picks the RACE; my-price + defection pick the
horse. Exposure split deferred (corpus too shallow to trust it yet).

THE MIDDLE-GROUND CHARTER (the master, 2026-08-17, verbatim: 'you have
learned so much since the start good and bad, you are in a lot better
place now to evolve. i understand keep altering things was a problem but
we need a middle ground we have spent a lot of time going no where').
Three lanes govern who may change what:
- LANE 1 — FREE, no permission needed: school-brief corrections (auto at
  3 strikes), trial policies (one line, graded nightly), bug fixes pinned
  by tests, and anything that only ADDS measurement (new record lines,
  new marks). The record is the only judge here.
- LANE 2 — EVOLVE THEN TELL (the new grant): behaviour changes to PAPER
  systems (school, shadow, fav line, grading, alarms) may be made without
  waiting — each ships with a REVERT-IF and is reported to the master in
  the same breath; his one word rolls it back. Time is no longer lost
  waiting where only paper is at stake.
- LANE 3 — THE MASTER'S WORD FIRST, always: the live pick path (NAP and
  VETO prompts — the taught laws are HIS words), staking, anything with
  real money, deleting or rewriting history. This lane never widens
  without him widening it.
The charter itself is Lane 3: he may strike or redraw it with a word.

AMENDMENT — AGILITY OVER SAMPLE PURITY (the master, 2026-08-16, verbatim:
'no 5000 is gone, we need to be agile, if we consistinctly see something
not working we can twait 5000 races to fix it'): the mine's 5,000-race
corpus floor is REVOKED. Verdicts issue at the sample we hold, n always
attached; consistent failure is fixed at the 50-pick bar, never deferred
to big-sample purity. Unchanged by this ruling: judge nothing under 50
picks, and graduation to REAL selections still needs the fav benchmark
beaten over 500+ unseen races — those are his floors and only he moves
them. First rulings under the amendment (2,247 graded races): no
single/pair cell is month-stable (no mechanical RULE — the edge must come
from reading); fav-at-2.0-3.5 is the least-losing cell (-4.2% vs -10.1%
benchmark) and goes on the night-school trial list; tight2 is 43 picks at
-41% — bin it at 50 if it stays consistent.

STANDING LAW — THE CURRICULUM & THE CREDIT ECONOMY (the master,
2026-08-16, verbatim: 'the goal here also is to expedite his process we
are currently a third year student level knowledge wise nearly there, we
have enough races every day that we can learn from, and we dont, we need
to do this economical with credits also'): learning runs in three tiers —
(1) FREE, nightly, unlimited: school/night.py on the server (fetch
yesterday on the paid API sub -> grade every policy on every race ->
ladder verdict into health). Challengers are one line in
data/school/policies.txt. (2) CHEAP, bounded: at most ONE deep exam
sitting per night (pack a past day, sit under the brief, mark, teach) —
that is where reading skill grows. (3) EXPENSIVE, rationed: deep-read
credits go ONLY to genuinely contested races on live cards — never to
questions a mechanical policy can answer. Spend flows down the tiers,
never up.

STANDING LAW — THE EVOLUTION LAW (the master, 2026-08-15, verbatim: 'we
need a system that if its failing, we evolve change tack, no point in
repeating something that is not working, i am at this 3 months and so far
have achieved nothing spent thousands on claude'): school/ladder.py reads
the daily grind and rules with HIS bars only (no verdict under 50 picks;
rolling window up to 500): champion below the fav benchmark = CHANGE TACK,
best challenger named; challenger beating champion AND benchmark = CHANGE
TACK, doorbell. Evolution proposes, the master disposes — promotion into
live selections is his word. PENDING WIRING (needs deploy): ladder verdict
into the daily health email, and the weekly synthesis must show CREDITS
SPENT (data/model_usage.csv) beside paper P/L — the bottom line he feels
is cost-vs-return, and the record must show it.

STANDING LAW — THE DAILY GRIND (the master, 2026-08-15, verbatim: 'as a
system we need to progress and not stagnate, we have enough data and power
every day to accelerate the learning and honing of the system which we
dont use, we keep saying wait 50 races to see, there are 50 races every
day'): learning consumes the WHOLE card daily — school/daily.py grades any
mechanical policy on every 5+ runner race vs the SP-fav benchmark, free,
so graduation bars fill in days not months. Staking is still judged ONLY
on the banked ledger. First real number, 2026-08-15, partial corpus (19
days, 672 races): SP favourite = 33.2% strike, -15.6% ROI — the pass mark
every policy must beat.

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

1. RESOLVED 2026-08-16 (health email): the veto trial settled in the
   reader's favour on outcome — 4 vetoes this week, ZERO killed a winner,
   and shadow (where vetoed picks bank) runs 5/17 vs live 10/32. The veto
   POWER survives per the pre-agreement. But the RATE (4/week vs tripwire
   2) is the old departing disease — flagged red, master aware; if a week
   shows 3+ vetoes again the audit re-opens regardless of outcomes.
   Record as of 2026-08-16: 10/32 (31%), +13.4pt; cold week 1/7; the
   losing week ran on the pre-2026-08-15 rulebook (new laws not deployed).
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
