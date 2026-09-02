# HANDOFF — the apprenticeship's living memory

Last updated: **2026-09-02** (the audit night) (update this file whenever state changes — it is
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
  racing_edge`, user v5racing), branch `main` (since 2026-08-18, "one
  brain": the box pulls main before every task — a merge IS a deploy).
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
- **The reader (NAP_SYSTEM + VETO_SYSTEM — the whole rulebook rides in engine
  mode since the third audit, 2026-09-02) writes the case** and holds ONE power: a
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

## STATE OF THE APPRENTICESHIP — week ending 2026-08-24 (append-only; newest state wins)

**The turn.** This was the week the master changed how he teaches — frames,
not corrections ("it's not as hard as you think", "just do the opposite...
dont go all nuclear", "stop thinking with your heart", "class is permanent")
— and the system started winning. Sat 2026-08-22: three reads, three
winners — Notable Speech (class read), Daiquiri Bay 14/1 (called pre-off,
Ebor), ARQOOB WON 15/2 (the banked duty pick, short head over the fav).
He called it "a new plateau — the key is to maintain this."

**Doctrine now in force (all merged to main, test-pinned):**
- CAUTIONS vs flags: "raised N lb since last win" warns, never erases
  (corpses: Too Much Trevor 10/1, the 08-22 Newmarket wipe-out). A caution
  must be answered in the case or the pick is a lean. CONFIDENT still
  requires zero cautions.
- Law 3c FORM IS TEMPORARY, CLASS IS PERMANENT (Notable Speech corpse):
  pattern races are not handicaps; rating-clear + books<=exchange = live
  pick despite layoff/beaten LTO. Read law now; STAKES gated behind the
  pre-registered class-line paper trial (data/school/preregistered.md,
  frozen bar, 50 rows, currently 0/1 — Havana Anna 4th, Chantez 28/1 won).
- Two-column record: race_quality banks with every nap; betting races
  (fingerprint>=2) judged apart from forced dreck days — judge the first.
- TWIN CHOICE gauge: opinions bank top-2 per race; nightly line counts
  "winner in my two / wrong twin taken". THE shared disease (dog school
  found it independently): we read right and rank wrong.
- Homework format (the master's dog-school sitting, in the morning trigger):
  counted-dots table, adjustments shown, the principle NOT used named, one
  verdict + named danger, banked pre-off; at settle the error named in one
  sentence. The master marks the read.
- Morning-duty scars in the trigger itself: date -u FIRST (2026-08-24:
  trigger delivered 12h late, pick banked post-off, VOIDED, fault named
  banked_after_the_off); race_status=="result" card = contaminated.

**Receipts that now anchor strategy (data/school/vision_report.md +
mine_report.md, PROVISIONAL — corpus hole Apr–Jul):**
- No mechanical cell survives blind (fav bench 35.2% / -11.5%; won-LTO
  -21%, hot yard -26%). There is no green formula; stop looking.
- Fingerprint races: fav 46.9% / -3.1% blind (only near-green cell);
  blind ranks 2-3 REFUTED (-17/-22%) — against-the-fav needs an earned
  reason, always. Class favourites small fields: +6.2% (n=36, the only
  positive cells ever found).
- One-fav-a-day (fingerprint fav <=5/2, else pass): 62% strike, -0.8% —
  the master's frame, near break-even blind; his craft (flip-flop law)
  is the missing 1-2 points. OFFERED as new FAV LINE definition — awaiting
  his word.
- The whole fight = ~3 winners per 200 bets. We start 97 yards ahead.

**Dog school exchange (docs/DOG_MODEL_PLAYBOOK.md out,
docs/DOG_LESSONS_RECEIVED.md in):** transfer the loop and the laws, never
the flesh. Adopted from them: honest-half NOT WATCHED footer in health,
pre-registration, PROVISIONAL stamping, one-lesson-one-place. Queued
(tasks #5/#6): fetch-coverage vs independent card list; trouble-early-vs-
late hypothesis. Sent back: cautions must never quietly erase.

**Ledger snapshot (session-side duty picks, data/school/picks/):**
Sat Arqoob WON 15/2 (+9.4pt EW) · Sun Sea Suite 5th (winner = named danger
Knights Gold 2/1F — wrong_twin, fault named: crossed on state not
direction) · Mon VOID (banked_after_the_off). Fav line: Goblet lost Sat,
Knights Gold won Sun. Server engine runs its own book in nap.db daily
(engine-first, objection era) — email checkpoints: (main) line, opinions
banked N, FAV LINE, MORNING OPINIONS marked X/N + BETTING RACES + TWIN
CHOICE lines since 08-24.

**Open, awaiting the master:** RULE_AUDIT rulings (per-horse AW #14 kill;
survivor-split ratification — cautions shipped for raised-lb only so far);
new FAV LINE definition (one fingerprint fav/day); nuance promotions;
server backfills (corpus via fetch.py, pre-08-19 shadow rows);
healthchecks.io heartbeat. Paper stakes only — the record has not yet
earned real money, and his family's food is the law behind that law.

## 2026-08-27 night — the Town Queen cuts ("do the above and do them surgically")

Homework night: two exam sittings on the run Carlisle card, both locked
pre-result. 3:00 — Bincimbal WON 9/4 (earned departure from never-won BF
fav Ten Clarets). 3:30 — Town Queen 15/8F ("solid" on the old test:
staircase 2-2-2-1, won LTO) trailed in LAST; Rikki Tiki Tavi won 12/1 off
a mark he'd already won off, free lead after 3 NRs. Autopsy in front of
the master; his word given the same night. Four surgical cuts shipped,
one per commit, suite green after each:

1. **SCHOOL_BRIEF v6** — MARK line + FIT line mandatory in writing (no
   lines, no pick); break-beats-staircase; read-the-pace-before-the-runners.
2. **Law 2b-ii, THE FIVE-PART SOLID TEST** (rulebook, pinned): solid =
   short + in form + HAS WON + RACE-FIT + PROVEN AT THE MARK; fail any
   and the shield comes off — "why NOT take him on?"
3. **Law 3g, THE WINNING MARK** (rulebook, pinned): today's mark vs the
   mark last won off is a COUNTED dot both directions. Engine-side: first
   run off a raised mark = DISTINCT NAMED caution (week cohort 0-for-5) —
   NOT a flag, because Too Much Trevor (same profile, crossed 08-22, won
   10/1) makes the honest cohort 1-for-6; the record argued back
   mid-surgery and the demotion law held. Blocks CONFIDENT, never erases.
4. **Solid-fav shield gate** (engine): a favourite failing has-won /
   race-fit / proven-at-the-mark earns no #19 market dot; the named holes
   ride in as a caution.

Exam ledger to date: Mon 6 sittings 2 wins · Thu 2 sittings 1 win.
New-mark-first-run cohort receipts: Vaguely Royal, Molly Mac, Is She Now,
Kanzi, Town Queen — 0-for-5 the week; winners at/below proven mark:
Gallus Norman, Ecclefechan, Cape Toronada, Rikki Tiki Tavi. All of it
lands in the live engine only when PR #69 merges.

## 2026-08-29/30 weekend — the telly school (seven laws, two promoted edges, and the master's masterclass)

Two live TV co-read days with the master; the heaviest teaching stretch
of the apprenticeship. Everything below is on branch
claude/resume-handoff-docs-ayas2r inside **PR #71 — the production 07:30
engine has NONE of it until the master says "merge"** (Lane-3 gate, his
key alone).

**LAWS CUT (rulebook, all master-taught, all test-pinned, suite green):**
- **5b THE YARDSTICK ON EVERY HORSE** (Sedgefield scar formalised): a rule
  firing is where work starts; no horse unmeasured, no verdict.
- **4f THE LONG TRAVELLER** ("I have seen this time and time again, it's
  my law"): the van is intent; two-tier — full stack (lone raider +
  in-form yard + jockey + clean money) = win candidate; bare trip =
  frame nomination. Corroborator never selector; defers to #10 at quirky
  tracks. Day-one receipts: Inspired WON SP 4/1 (full stack, beat the
  duty pick); Rainbow Nebula 3rd, backed 33s->10s.
- **4g THE BOOKIE'S GIFT AND THE FLIP-FLOP** (Cork): a bookmaker's BOOST
  is the kiss of death (they boost what they want you on); a
  flip-flopping fav is churn not conviction; market CHARACTER is asked
  of the watcher, never inferred from two snapshots. Receipt: Catalina
  15/8F (boosted, flip-flopping) 10th of 12.
- **3i THE SPECIES QUESTION + THE MISMATCHED BOOKING** (Kokbastau+Itica,
  "important lesson here"): figures are CEILINGS on exposed horses,
  FLOORS on babies (<=5-6 runs); sharpest in sellers where every exposed
  ceiling is known; champion jockey on the bottom-rated at a price = the
  mismatch is the message; booking nominates, species decides. Receipt:
  Itica WON SP 22/1, Murphy up, crossed by the sitter on perf 53.
- **THE ZAVATERI GATE** (engine, "fix hole"): is_readable — Cl1-2 pattern
  races enter the funnel across nap/brief/restudy/dissect; handicap
  preference untouched; REVERT-IF first three pattern naps 0-for-3.
  Born after Zavateri (four-question sweep, 6/4) won a G2 the
  handicaps-only funnel never saw.

**BRIEFS:** #22 Blanco line mandatory + AMENDMENT: the scan is PLURAL
(all figures within ~4lb of top at a price, each judged on own facts —
receipts were always 2nd-best figures: Fondo Blanco, Love Dynasty,
Magny Cours WON 9/1 missed by the single-top scan). #23 THE CALCULATED
SHAPE (open race + 5/1@1/5 = the freeroll boundary; bet-shape line
mandatory; anchor: "best horse wins race"). #24 THE FLOOR OF A READ
(a label is not a read; digits need COMPANY; UNREAD declared honestly).
#25 NO CARD NO CALL + ASK THE BOARD (Flash Harry scar — crossed off a
screenshot, won this race last year). **docs/TELLY_SHEET.md**: the
mandatory 13-line form for every live co-read.

**EDGES PROMOTED:** THE UNEXPOSED CARVE-OUT (two receipts, ledger's own
bar: Kokbastau + Itica). Blanco read: 6 sightings, 4 ran to profile in
48h. Traveller stack: Burke's Goodwood van went W-W-3rd on the day.

**SCARS (named, append-only):** THE OVERRIDDEN CONVERGENCE (sum + stack
+ money all said Inspired; sitter paid an 11lb grade premium to
disagree — when instruments converge, answer it in writing or yield);
THE UNMEASURED RACE (Zavateri); repeat burns JM Jungle (v8b third burn
— class-top crossed on a label) and Flash Harry (screenshot read);
the pendulum fault (board promoted from dot to verdict at Cork).

**THE RECORD, WEEKEND:** Duty 0-2 (Defence Minister 3rd 9/4; Principality
4th 4/1 — winner Inspired was the sheet's own named danger,
wrong_twin=1). Bandit column -8.8pts running. Telly column Sun 1-5
(Light Of Dawn WON 7/2 — the one COMPLETED read; full-floor reads 2-0
across the weekend, label reads 0-for-everything). ITV7 fun entry 2/7
(Kinswoman 4/9, Light Of Dawn). MASTER'S COLUMN: +5.0pts (Inspired EW,
his call, his stack) and telly reads near-flawless — Inspired, avoided
Catalina (flip-flop+boost), named Magny Cours the system's horse.
engine_override=1 (Sat: engine's Passing Diamond WON 8/15F while the
sitter hand-picked elsewhere — ENGINE-FIRST for the chat lane proposed,
master: "possibly a good approach", alignment logged at every settle).

**OPEN:** PR #71 awaits the master's "merge" (all of the above + Fri/Sat
work). Engine-side Blanco scan = promised surgical cut (his word given
via "stop ignoring the blanco read" + "not dialled in"). Traveller
mining run on the results corpus offered. GOING column now has its
first major frank (Light Of Dawn). E8 watch: Victoria Night next run.
Morning duty trigger unchanged; settle triggers self-managed per day.

## THE WEEK PLAN — 2026-08-31 to 09-06 (graded next Sunday, against these numbers)

The week's diagnosis in one line: the sitter delivers 80% of a known
process under pressure, and the game pays nothing for 80%. Every item
below attacks that, and every item has a COLUMN counted at settle.

1. **ENGINE-FIRST, every morning** (the master: "possibly a good
   approach" — the trial is live): the 7:30 duty STARTS from the
   engine's email candidate. Master pastes it or the sheet records
   "not sighted". Take the candidate, or write the cited veto — no
   third option. COLUMN: alignment/override/veto-quality per day.
   TARGET: zero silent overrides. (Receipt driving this: engine 2-0
   on the weekend, sitter 0-2.)
2. **THE PREP BLOCK on telly days**: every ITV/named-meeting card +
   principal records pulled BEFORE the first off; telly sheets
   pre-filled; the live board is the only line left for race-time.
   Kills the scramble that produced Flash Harry and JM Jungle.
3. **TELLY SHEET, 13 lines, or "observations only"**: no verdict
   below the full form. COLUMN: completed-read %. TARGET: 100% —
   the weekend's receipt is absolute (completed reads 2-0, label
   reads 0-for-all).
4. **ZERO REPEAT BURNS** — the only target that is pass/fail: no
   class-top or question-winner crossed without his record read
   (v8b), no read below the floor (#24), no verdict off a screenshot
   (#25). One repeat burn = the week fails regardless of P/L.
5. **THE BLANCO ENGINE CUT** (owed on the master's word): the plural
   scan (all figures within ~4lb of top at a price) coded into the
   engine readout + morning email this week — one surgical commit,
   test-pinned, so the Magny Cours miss becomes impossible. Rides
   into the PR.
6. **SETTLE-SAME-DAY, ERROR-SAME-NIGHT**: unchanged and non-negotiable
   — the one discipline that held all weekend stays perfect.
7. **LEAN**: no new features beyond the Blanco cut without the
   master's word; the traveller mining run only if he asks.

GRADING NEXT SUNDAY, off columns only: duty strike rate (>0 or the
named passes that earned their pass), completed-read %, engine
alignment record, repeat burns (must be 0), bandit/telly/master
columns P/L. The strike rate is the grade — nothing else.

## AUDIT 2026-09-02 — read this before touching the record or the settle

The master ordered a whole-pipeline audit ("I am sick of finding the problems
myself"). The map of every stage lives in docs/ARCHITECTURE.md; the 41 findings
and their dispositions in docs/EDGE_LEDGER.md (same date). What changed the
system's behaviour, in one breath: the record's guards live AT THE WRITE POINT
(a settled day can never be re-banked or passed over); non-runners VOID with a
mandatory reason (won = -2), never a loss; the night settle SWEEPS every open
date and voids a week-old orphan with the console command in its reason; the
time guard fails CLOSED and is asked again at bank time; a non-favourite pick
carries its written edge; data/nap_record.csv is the text twin; the master's
rulings (data/rulings.csv, verbatim, dated) ride into the morning prompt and
every recall is counted; tier-0 scores every runner against the market nightly
(data/school/tier0.md). For the master's ruling, unchanged: the reader-mode
floors that are dead under engine mode; the shape-book gate's fail-open on an
unreadable corpus; scoring the named danger / my-price at settle.

THE READ IS THE PRODUCT (the master, 2026-09-02, after the audit — verbatim:
"we want to read the form not depend on arithmetic"; "its an intelligence
system. it needs proper structure to make it reliable, consistent. i want u to
read the form like me only on steroids and scale. the edge is joining the dots
not crunching numbers"): no weights engine, no learned scoring — STOPPED before
a line was committed. The structure around the read instead: a read is not a
read without a case (MorningPick.ok); every dot the read joins — the named
danger, the crossed-off list, the reader's own price — banks in the nap row and
is GRADED at settle (read_grade), with the scoreboard in health. The loop is:
read every race in the morning, mark every read at night, autopsy the misses
Rule-One style, the master's rulings verbatim in every read, walls around it.

THREE WAVES IN ONE NIGHT (2026-09-02): the plumbing audit (41 findings), the
adversarial second wave on the fixes themselves (20), and the picking-system
audit (23) — all in docs/EDGE_LEDGER.md under the date; the SWOT in
docs/SWOT_2026-09-02.md. The two findings that matter most for every future
session: (1) under the default engine mode the rulebook (NAP_SYSTEM) was NEVER
sent to the model — only the veto text was — so every "pinned" law was inert
for the live read until tonight; (2) the engine's per-horse yardstick (lenses,
cautions, flags) was never shown to the reader. Both fixed. STILL FOR THE
MASTER'S RULING, unchanged: the race-first rank key v "best horse wins"; the
cornered day banking against law 5; the dead reader-mode floors; engine mode's
one-race deep read; the engine lenses citing law numbers the rulebook never
spells out; "stop bottling" v the earned pass. The market is ONE price
snapshot — laws 4b/4c/4d/4g have no data; snapshots through the day are the
cut, on his word. (SUPERSEDED BY THE NEXT PARAGRAPH — kept as the timeline.)
THE MASTER RULED THE SAME NIGHT ("fix the above now"): race quality is a BAR
then best horse wins; the cornered day PASSES; the floors cap in engine mode;
two-race deep read; the engine's lenses are in the rulebook; law 5d the
bottling line; THE BOARD — two price snapshots a day (07:30 from the read,
12:30 from the guard), movers emailed. All with REVERT-IFs in the ledger.
THE FOURTH WAVE (same night, ~20:30 UTC): the pipeline RUN end to end by six
bots (ledger F1–F24) — 22 e2e tests now live in tests/test_e2e_*.py and run
the 07:30 / 12:30 / 22:00 entry points with fake feeds every time the suite
runs. Real bugs found and fixed: night school double-appended a re-run day
into the policy ledger; the bank-time scorecard refetched the pick's race;
the veto tripwire in health matched text nobody writes (now the objection
scoreboard); the shape-book memo ignored its corpus path; health read three
roots. For the master's ruling: the deep read's truncation retry doubles the
token budget (money, F11). Named, not touched: main() at 800 lines (F12).
Harness scar: NEVER restore a mutated file with `git checkout` while edits are
uncommitted — copy the file aside first (it wiped pipeline/nap.py once tonight).
HIS RULING ON THE OPEN ITEMS ("implement whatever will make it better"):
the truncation retry grows by half; one clock (uk_today) everywhere; the
THIRD SNAPSHOT — health writes 09:30, the guard names FLIP-FLOPs across
07:30/09:30/12:30; THE DELTA LINE (today v last run: class, mark, trip,
going, course) on every runner in the deep read. Deferred with reasons in the
ledger: main() extraction, tag-keyed rulings recall, the corpus memo.

