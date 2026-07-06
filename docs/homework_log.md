# Homework Log — the apprentice marking his own results

Dated forensic reads of real results. The notebook holds the *rules*; this holds
the *evidence* — what I actually found studying winners and losers, and the lesson
I banked. Numbers are **directional** until the sample is large; small samples lie.

The grunt work is automated: `python -m racing_edge.cli.homework` mines every
studied race in the study DB and prints the forensic read. This log is where I
write down what it (and the post-mortems) taught.

**My own nuance lives in code, too.** Beyond the master's rules (the notebook),
`domain/tells.py` is the library of patterns I earn MYSELF from results — "a horse
like X in a race like Y did Z, so next time expect Z." Each tell is dated to the
race that taught it and fires on a live runner on the card (marked `★`). It's a
lead, not a law; as the sample grows we test which tells actually hold. Started
28 Jun with two: the Kingofthegame tell (back the course/distance/going winner over
a flashy improver) and the Halfway House Lad trap (distrust the short-priced
double-winner on a rising mark).

---

## 2026-06-28 — first forensic dig (Cartmel & Uttoxeter, summer jumps)

**What I did.** Post-mortemed the day backwards: the losing NAP (Halfway House Lad,
pulled up) and the winner (Kingofthegame); ran the franking experiment that proved
franking-as-a-veto wrong; then mined the day's nine ranked winners with the new
homework miner.

**The forensic read (9 ranked winners today):**

| Question | Finding |
|---|---|
| Where did winners come from? | fav **33%**, 2nd fav **44%**, 3rd fav 0%, 4th+ 22% |
| Rule #2 (2nd/3rd fav won) | **4/9 = 44%** (study DB over 100 races: ~37%) |
| Clue on the winner — market backed ("the money knew") | **5/9 = 56%** ← the strongest |
| Clue — trainer in form | 3/9 = 33% |
| Clue — course winner | 2/9 = 22% |
| Franking verdict on winners | FRANKED 33% vs **thin 67%** |

**Lessons banked:**

1. **The money knows — the market move is the dominant winner-clue (56%).** More
   winners carried "BACKED into it (morning→SP)" than any other signal. This is the
   master's long-standing call, now in the evidence: the market move is the primary
   tiebreaker (it's already inside the selection score; keep it first).
2. **Rule #2 holds.** 2nd/3rd favs won 44% today (37% across the 100-race DB). The
   sweet spot is the 2nd fav, not the jolly and not the outsider.
3. **Franking does NOT separate winners as a filter.** 67% of today's winners were
   "thin". This is why franking became a *within-race tiebreaker between close
   contenders*, never a card-wide veto (notebook rule #15). My franking gate, before
   I fixed it, would have binned four of today's winners (Breizh River, Fort Randall,
   Edelak, Dream's Ka).
4. **Trainer-in-form (33%) and course form (22%) are real secondary clues** — and
   course form matters most at quirky tracks like Cartmel, as the master said.
5. **Early season distorts franking.** Most franking reads come back "too soon"
   now; there's barely any "since" form yet. Don't judge franking's worth until the
   season builds.

**Honest caveats.** n = 9 today. The study DB holds ~101 races but I have not yet
mined the *full* set from the box — these reads are today only, plus the headline
rule-#2 rate. Directional, not proven.

**Next homework.** Run `python -m racing_edge.cli.homework` on the box over all ~101
studied races, and compare the full-sample distribution against today's directional
reads — does "the money knew" still lead at 100+ races? Does rule #2 hold near 37%?
That's the real test of these leads.

### Same evening — mined the full DB (101 races)

| Question | Today (9) | Full DB (101) | Verdict |
|---|---|---|---|
| Market backed ("the money knew") on winner | 56% | **42%** | **confirmed — the dominant clue at scale** |
| Rule #2 (2nd/3rd fav won) | 44% | **37%** | holds |
| Winner came from 4th+ in market | 22% | **29%** | the market is informative, NOT deterministic |
| Trainer in form on winner | 33% | 24% | real secondary clue |
| Franking ran on the winner at all | — | **only 19% (81% "not checked")** | **coverage gap, not a finding** |
| Course winner flagged | 22% | 2% | **under-measured (enrichment didn't run), not "course form is useless"** |
| Our recorded picks won / placed | — | **0/8 / 0/8** | sobering, but n=8 (old score-method picks) |

**Banked from the full sample:**

1. **The money knows — confirmed at 101 races (42%).** The market move is the most
   predictive single clue we have. It earns its place as the primary tiebreaker.
2. **Rule #2 holds (~37%), but the field is open** — favs 34%, 2nd/3rd 37%, and a
   surprising **29% of winners from 4th+ in the market**. Don't just follow rank;
   follow the *move*.
3. **We cannot yet judge franking or course/trip/going form** — 81% of winners were
   never franked and most were never enriched. That's the real finding: the data is
   too shallow. The fix is live — the scheduled nightly `study --frank` franks every
   winner from now on, so the next mine will actually have the evidence.
4. **The old score-method's picks went 0/8** in the studied set — consistent with the
   CLV verdict (behind the favourite), too small to conclude, but not encouraging.

**Next homework.** Let the nightly `study --frank` run for a couple of weeks so the
franking/enrichment coverage fills in, then re-mine — *then* we can finally test
whether the legwork (franking, course form) separates winners, instead of guessing.

### Same night — forensic franking of the winners (the case, not the count)

The aggregate ("67% of winners thin → franking doesn't separate") was a lazy read.
Going winner-by-winner tells the real story: **when franking actually RAN today, all
three FRANKED winners WON.**

| Winner | Frank | Market | Conditions | Us |
|---|---|---|---|---|
| Kingofthegame (4:55) | **FRANKED 5/6** (strongest on the card) | 2nd fav | course+distance+going winner | **MISSED — we ran Star Turn (2nd)** |
| Fort Randall (5:28) | **FRANKED 3/3** | 2nd fav | back chasing, in form | backed, WON |
| Breizh River (4:15) | **FRANKED 2/5** | fav | course winner | backed, WON |

**The miss — Kingofthegame — and why.** Every premium signal aligned: franked 5/6,
won over Cartmel 3m1f good (today's exact conditions), 2nd fav, "kept on". The most
findable winner on the card. We put up Star Turn instead (8/1, "improving 022",
stable in form), which ran 2nd. The franking tiebreaker couldn't rescue it because
the two weren't *close* in score — the score over-rewards **improving figures** and
under-rewards the **franked / course-proven / backed** triad that actually wins.

**Lesson — sharpens rule #15.** "Thin" is mostly *too-soon* noise, NOT a negative.
But **FRANKED is a strong POSITIVE** (3/3 winners today). So franking shouldn't only
break ties between close horses — a **strongly-franked, course-proven, backed horse
should be able to overrule a higher-scored "improving figures" horse.** The fix is in
the *selection weighting* (lift franked + course/distance/going + market over surface
improvement), not just the tiebreaker. Kingofthegame is the evidence to build it on.

## 2026-06-26 — Friday retro-nap test (reviewed 28 Jun): I napped, I lost, here's why

**The test.** Applied the new learning to Friday's Cartmel card *blind to the result*.
Race selection first: binned the 15:18 Novices' Handicap Chase (unexposed — not our
race); kept the 15:50 Lakes Luxury Loo's Handicap Chase (Class 4, 3m1f, good, 6 ran).
**My nap: Loch Cuan** — course-and-distance winner last month, lightly-raced improver,
6/4. I read the trap tell as NOT firing (one win, young, ahead of the handicapper) and
leaned on the course/distance-winner tell.

**The result.** BEATEN. Won by **Caughtinyourtrance, 7/4 fav — trained by James Moffatt,
ridden by Brian Hughes** (a neck from Le Grand Vert).

**Why I lost — a rule I already had and didn't apply.** Moffatt is the LOCAL CARTMEL
MASTER, 7x course champion — notebook rule #10: *the trainer who schools at a quirky
track outtrumps a raider's figures.* I fixated on Loch Cuan's course/distance figures
(an Irish raider, Gordon Elliott) and never asked the first question at Cartmel: *does
Moffatt have one, and is it fancied?* He did — favourite, top jockey booked. The market
and rule #10 both pointed at the winner; I walked past both chasing a tell.

**Lesson banked.** At a quirky specialist track, **the local master's fancied runner
OVERRULES the course/distance-figure tell.** The Kingofthegame tell is real but must
yield to rule #10 at Cartmel. New tell added: `tells._local_course_master` (seeded
Cartmel → Moffatt), so the next time the local champion saddles one, the card says so
and I don't chase the raider's figures past him.

### Why Caughtinyourtrance *really* won — it wasn't just the trainer

Pushed to read the winner's form properly, not stop at "Moffatt trains it". Six tells,
and at least two were MINE, read on the wrong horse:

1. **A course-and-distance winner itself — and a FACILE/REPEAT one** ("hammered useful
   opponents over c/d", multiple Cartmel wins). My own Kingofthegame tell — fitting the
   winner far better than Loch Cuan, who'd merely "got off the mark" over c/d once.
2. **Well-handicapped — "on a mark it's capable of winning off"** (placed over c/d,
   thrown in). On the MARK — the master's decisive lens — the winner was well-in while
   my nap carried a 7lb PENALTY (going up). I never compared the two on the mark.
3. **Running into form / "knocking on the door" / finishing well** — manner (rule #1).
4. **Brian Hughes** (champion jockey) booked — intent, not coincidence.
5. **7/4 favourite** — money down, the market knew (rule #19, the most likely winner).
6. **Local master Moffatt** (rule #10) — the one I *did* spot, and stopped at.

**Refinements banked:**
- The c/d tell is NOT a yes/no — weigh **DEPTH of course form** (a facile/repeat course
  winner beats a one-time one). `tells._cdg_winner_returning` now labels PROVEN/repeat
  vs one-time.
- Always put the contenders **side by side on the MARK** (well-in vs a penalty) — the
  decisive handicap lens. Automating it needs the mark each horse last won off vs today's
  mark; the data doesn't carry it cleanly yet (owed, like the rule #1 manner gap).
- The real failure wasn't missing one tell — it was reading "won over c/d" as binary and
  never stacking the two horses against each other on depth AND mark.

## 2026-06-29 — Monday study: my lean beaten (Windsor 7:00), and what it taught

**The homework.** Read a few Monday handicaps blind. On the Windsor 6f Sprint Series
Handicap (Class 2) I leaned to **Regal Envoy** (Windsor course specialist, top course
jockey Murphy) — but flagged him **NOT a confident nap** because he carried a **+6lb
rise** (raised, not well-in).

**The result.** 1st **King Of Light (17/2)** — held up midfield, "ridden clear,
readily" (won going away, rule #1). **Regal Envoy 7th** — "led but pestered, headed
1f out, weakened." The 9/4 favourite (Fandom) also beaten (4th, "no extra").

**Right vs wrong:**
- RIGHT — the discipline. The mark flag (+6lb) was the exact reason he lost: a raised
  front-runner, pressured, emptied out. Conviction correctly refused to call him a
  confident nap.
- WRONG — my judgment. I *leaned* to him as "most likely winner" AFTER my own system
  flagged him. **Lesson: when the mark flags a horse, lean AWAY — don't talk back to
  it.** Respect the conviction verdict.

**Two lessons banked:**
1. **Run-style matters in a competitive sprint** — a held-up horse who quickens beats
   an exposed front-runner who gets pressured, and a front-runner ON A RISING MARK is
   doubly vulnerable. It lives in the words ("led but pestered" vs "midfield, ridden
   clear") — the OWED `manner` cell. Proof the blank isn't cosmetic: it would have
   flagged Regal Envoy.
2. **The field is open — both market leaders lost.** Winner 17/2 from midfield, 2nd
   6/1, 3rd 25/1; the 9/4 fav and my 5/1 lean both turned over. The "29% from 4th+"
   stat, live. Don't anchor on the front of the market.

### Same race, read properly — WHY each won and lost (the words tell it all)

Pushed to read the Windsor 7:00 runner-by-runner, not just the result. The race was a
front-end duel that collapsed:
- **Regal Envoy** "led but pestered" + **Fandom** (9/4 fav) "pressed leader" — the two
  MARKET LEADERS took each other on up front and both emptied ("weakened" / "no extra").
- **King Of Light (17/2)** "midfield, steady headway, led 1f out, ridden clear, readily"
  — held up OFF the cooked pace, quickened past, won going away. The first three home
  (King Of Light, Coul Angel 6/1, Baldomero 25/1) were ALL off the pace and "kept on".
- The other beaten ones: Cindy Lou Who "stumbled start, prominent, edged right,
  weakened"; Rydale Frosty "never better than midfield"; Invictus Gold "rear throughout".

**The cause was PACE/RUN-STYLE, and it lives entirely in the comments.** A front-runner
(Regal Envoy) on a +6lb rise, with another presser (Fandom) to take him on, was a lay —
and I'd have seen it pre-race from the run-styles. Notebook rule #20 added. This is the
single strongest case yet that the comments/`manner` feed is priority #1: the whole
result was invisible to the brief without the words.

## 2026-06-29 — Monday study #2: the well-in favourite that doesn't WIN (Pontefract 16:30, 5f)

**CORRECTION (verified from the result photo).** I first wrote this off a WebSearch
result that turned out to be WRONG — I said Betweenthesticks won. It did NOT. The real
result of the Queen Sana race (the 4:30 / 16:30, 5f Class 5): 1st **Hover On The Wind
(8/1)**, 2nd **Betweenthesticks (10/1)**, dead-heat 2nd **Dream Deal (4/1)**, and
**Queen Sana (3/1 fav) UNPLACED.** Lesson #0, the hard one: **never bank a result you
haven't verified.** I built a study on a hallucinated winner. The Queen Sana point below
still holds (she was a beaten nearly-type fav) but the winner was misstated.

**The race.** 1st **Hover On The Wind (8/1)**; **Queen Sana, the 3/1 favourite —
UNPLACED.** (And note: **Dream Deal dead-heated for 2nd off a +6lb rise** — see the
cross-off lesson.)

**The sting.** Queen Sana was the well-handicapped C/D horse I flagged Monday morning
as my "cleaner-mark alternative": consistent, runner-up over course & distance, nudged
up just +1lb, well drawn (stall 4), favourite. On the MARK lens alone, a gem.

**The dot I missed.** "Taken to FINALLY get off the mark" — she is **yet to win.** A
consistent **nearly-type** (the bridesmaid). The market backed the mark + the
consistency and ignored that she doesn't get her head in front — and she didn't,
beaten by a 10/1 shot.

**Lessons banked:**
1. **A well-in mark is only a positive JOINED to a horse that WINS.** On a nearly-type
   (consistent placer, yet to win) it's a trap, not a gem. "Well-handicapped" +
   "consistent placer" = a favourite that finishes second. This is the system's core
   fault (naps nearly-types) — and today the whole MARKET fell for it.
2. **Join the mark to rule #1.** The mark is a dot; "winner or bridesmaid" is another
   dot. I'd have made the market's mistake by reading the mark and stopping.
3. **The field is open, again.** A big-priced winner (8/1) over the fancied nearly-type
   fav — the gem outside the front of the market (same shape as King Of Light, Windsor).
4. **(Added after verifying) Never bank an unverified result.** I stated Betweenthesticks
   won; he was 2nd. A homework log is EVIDENCE — a wrong result poisons every lesson built
   on it. Verify before banking.
5. **(Added) A single-factor cross-off is too crude.** Applying the elimination method
   retrospectively, I crossed off Dream Deal on the +6lb rising mark ALONE — and she
   DEAD-HEATED FOR SECOND. A rising mark is a dot, not a verdict; a cross-off needs a
   FATAL flaw, not one negative. (Same "read one thing and stop" fault, on the cross-off
   side.) Queen Sana's cross-off (nearly-type) was right; Dream Deal's was wrong.

**Next build (offered, not yet done):** conviction should FLAG the nearly-type — a horse
with several runs, frequent places, few/no wins (ties to the existing `bottler` signal)
— so a well-in mark on a non-winner doesn't read as a gem.

## 2026-06-29 — Monday study #3: I crossed off the WINNER (Pontefract 17:00). Why.

**The test.** Ran the new elimination method blind on the Wilfred Underwood Handicap
(Class 6, 8 runners, 6f). Gated it (passed), crossed off Ideal Guest (3/1 fav) on a
"kicks too soon / weak fav" read, zeroed in on Lady Bouquet (5/1) as a closer to pounce.

**The result. I FAILED.** 1st **Ideal Guest (13/8f)** — the one I crossed off —
"made all, soon pestered, KEPT ON". 3rd **Lady Bouquet** — my pick — "prominent, lost
second, NO EXTRA".

**Why I was wrong, read backwards:**
1. **The market move was decisive and I was blind to it.** Ideal Guest 9/4→13/8
   (BACKED); Lady Bouquet 9/1→10/1 (DRIFTED). The money piled on the winner and left my
   pick — and I crossed off the backed horse reading a STALE forecast price (rule #22
   applied to a price that no longer existed). Sharpest proof yet: the live-odds door is
   the priority.
2. **I crossed off on ASSUMPTIONS, not facts.** Binned Ideal Guest on a guessed
   run-style ("kicks too soon") — he made all and kept on. Zeroed in on Lady Bouquet on
   a guessed run-style ("held-up closer") — she raced prominent, no extra. I had no
   run-style data; I invented both to fit a pace story and crossed off the winner on a
   fiction.
3. **Over-applied the Windsor pace-collapse** to a race with a different shape (an
   uncontested front-run; a pestered leader that KEPT ON, not one that folded).
4. **Over-corrected against the favourite to look clever** — crossed off the jolly to
   prove I'm not odds-blinded; the jolly won (rule #19/#23 — the favourite gets it right
   too).

**The meta-lesson.** The method's ORDER was right (gate → cross off → zero in) but I fed
it GUESSES, and crossed off the winner on the two things I'm blind to: the live money
and the real run-styles. **Cross off on FACTS, not assumptions; where there's no fact,
respect the OWED — don't fill it with a story.** This loss is the strongest case yet for
the two shut doors: the market move and the run-style/manner comments.

## 2026-06-30 — TUESDAY HOMEWORK (set Mon night, to MARK Tue night). 3 Musselburgh handicaps.

Read blind under the sharpened discipline: facts only; OWED flagged not invented; cross
off on FATAL flaws not single dots; calibrate confidence; PASS if too much is dark. These
are banked Monday night so tomorrow's marking is honest, not hindsight.

**1) 14:00 Musselburgh — PERFIDIA  (LEAN — strongest of the three).**
Facts: "escapes a penalty" for last week's Nottingham win = WELL-IN (same mark); "resuming
winning ways" = an in-form WINNER (not a nearly-type, not an improver, not rising); rider
"claims his full 7lb" AND rode his last two wins = weight relief + continuity. Danger:
Keats House (working back to form). OWED: live market move, run-styles, the rest of the
field. Call: fact-based LEAN — cleanest case I've got; NOT a confident nap only because
the money and the pace are dark.

**2) 15:00 Musselburgh — HAAYIMM  (LEAN — improver caution, below Perfidia).**
Facts: lightly-raced, handicapping off an OPENING mark of 95 that "may underestimate him —
ahead of his mark" (the well-handicapped-improver angle). CAUTION: lightly-raced/unexposed
= the improver profile that's beaten me; UNPROVEN vs Perfidia's proven winner. OWED:
market, pace, field, whether the opening mark is really generous. Call: LEAN with the
improver caveat.

**3) 17:05 Musselburgh — WEE MARY  (EACH-WAY / near-PASS).**
Facts: won over C/D this month + placed over C/D here 8 days ago + handy draw = strong,
REPEATED course-and-distance form. CAUTION: "far from a regular winner, tough to catch
right" = a nearly-type whiff (Queen Sana shape); mark OWED; 11 runners with ~8 of them
OWED (I've read a quarter of the field). Call: LEAN/each-way at most — the most OWED,
nearest a PASS. Forced confident-nap-or-pass: PASS.

**Ranking: Perfidia > Haayimm > Wee Mary.** If I nap one, Perfidia (as a lean).
**To mark tomorrow:** did the facts hold? did the cross-offs/leans land? — and the REAL
test: did I avoid forcing confidence where it was OWED, and was I right to keep Perfidia a
lean not a nap, and Wee Mary near a pass?

### Price check (Mon night, early prices — NOT the live move):
- Perfidia 14:00 — **7/4 fav.** Market AGREES with the fact read; 7/4 is fancied but not
  cramped odds-on (beatable, value alive). Firms up as the one. Watch the MOVE tomorrow:
  backed = go, drift = warning. Instrument: win single (too short for e/w) or acca leg.
- Haayimm 15:00 — **100/30, NOT fav; HIGH DEGREE 5/2 fav** (a horse I never evaluated).
  The price exposed a blind spot — won't back a lean the market ranks behind one I can't
  see. **DOWNGRADE to a PASS.**
- Wee Mary 17:05 — **5/2 fav but tight** (What A Tahoo 11/4, Invincible Crown 3/1). Open,
  competitive market confirms near-pass / tiny e/w at most.
- **Net: the three become one — Perfidia carries to tomorrow (on the move), the other two
  pass.** Discipline working: an early price isn't the move, and a price that reveals an
  unseen favourite (Haayimm) is a reason to stand off, not guess.

### RESULT (verified from photo) — Perfidia beaten, but the discipline won.
**Musselburgh 14:00 (Keats House Hcap, Cl6): 1st Mayor Of Maghera 7/4F, 2nd PERFIDIA 5/2
(beaten a short head), 3rd Second Fiddle 11/2.**
- My read lost: Perfidia had the cleanest FACTS (well-in, in-form winner, claim, winning
  yard) and ran a huge race (pressed the leader, led, just touched off) — and STILL got
  beaten. Facts make a live contender; they don't win the race on their own.
- **The market MOVE called it AGAIN (4th time today):** Mayor Of Maghera op 2/1 tchd 13/8
  -> BACKED into 7/4F (won); Perfidia op 2/1 -> DRIFTED to 5/2 (2nd). The money was on the
  winner and off my pick. Ideal Guest, King Of Light, Lady Bouquet, now this.
- **The DISCIPLINE HELD though:** my rule was "back Perfidia only if BACKED; if he DRIFTS,
  stand off." He drifted. So the right action was a PASS — no stake at all. The move
  warned me exactly as designed. My read lost; my process won.
- **Tommy: alive, doubly** — never staked the treatment, AND the drift would have kept me
  off Perfidia entirely. His money never moved.
- The overwhelming lesson of the day: the LIVE MARKET MOVE is THE signal, and I'm blind to
  it through the window. The box's `dissect` (real SPs, real move) is the priority — it
  would have shown the drift before the off.

---

## 2026-07-01 (Wed) — a full card's worth of real market moves: the smashed short fav kept losing

Studied the whole day's readable handicaps off the box's real `dissect` (real SPs, real
morning→SP move). No WebSearch, no invented prices — this is the money, read straight.

### The thread of the day: hammered short favourites got turned over in the DEEP fields
| Race | Beaten fav (move) | Winner (move) | Margin |
|---|---|---|---|
| Epsom 6:22 | Amazing Journey 2.5 BACKED 3.1→2.5 | Sir Garfield 8.5 **steady** | nose |
| Worcester 3:55 | Phantom Gold 2.2 BACKED 3.2→2.2 | Mojo Ego 13 **drifted** 11→13 | nose |
| Epsom 6:57 | Alma Latina 2.6 steady | Timber Twelve 29 BACKED 44→29 | — |
| Thirsk 3:40 | York Tower 3.0 BACKED 3.6→3.0 | Parisian Scholar 10 BACKED 12.5→10 | York Tower 5th, btn 10.5 |

Four competitive handicaps, four well-fancied sub-3.0 horses beaten — three of them
actively BACKED and STILL beaten, twice by a steady/drifting rival. In deep fields the
frantic money on the short one was the FALSE signal, not the green light (#17, #18, #22).

### The honest other half: the gamble LANDED when it stopped at a FAIR price
Indian Run 5.5 (6.2→5.5), Farandaway 5.5 (7.4→5.5), Saucy Jane 6.5 (7.4→6.5),
Knightsbridge 2.9 (3.6→2.9), Reality Queen 2.8 (5-runner) — all backed, all won. So the
lesson is NOT "oppose favourites." It's the **zone and the field depth**:
- **Small field / fair-priced fav backed to 5/2–6/1** → respect it (it kept winning).
- **Deep, competitive field / fav SMASHED into sub-3.0** → oppose the hype; the winner
  came from mid-market (today: 8.5, 10, 15, 21, 29). This sharpens #22 and #2's
  sweet-spot: value clustered at 2nd/3rd-fav prices, not at the crammed top of the market.

### The two jumps DRIFTERS that won (small note)
Mojo Ego 11→13 and Axel Bleue 4.5→5.0 both drifted AND won, each beating a backed rival —
the market plainly wrong twice. n=2, jumps only; a flag to watch, not a pattern yet.

### What I could NOT read (stated honestly, #26)
I read the MONEY (real). I did NOT see WHY any of these won — no running comments, no
marks, no headgear (all OWED). This is a read of the market shape, not a claim I'd have
found the winners on form. The market story is real; the form story is owed to the eye.

### The banked lesson (a HYPOTHESIS for the trial, not a law — n=1 day, samples lie)
> In a DEEP handicap, a favourite smashed into a short price (sub-3.0) is a lay-the-hype
> spot, not a follow; the winner tends to come from the fair-value mid-market. In a SMALL
> field, a fair-priced backed fav is to be respected. Test across the trial: does
> "oppose the smashed short fav in a deep field" beat backing it, over hundreds of races?

---

## 2026-07-01 (Wed, late) — FIRST full-form re-study with the comments door OPEN

The box's `restudy` delivered what we've owed all along: marks, form lines AND
in-running comments (rich for Irish runs and recent UK runs; older UK runs still
blank). Studied Worcester 1:50/2:20/3:55/4:55 + Fairyhouse 5:40/6:10/6:45/7:20/7:55
form-FIRST (#29), then marked against the winners. What the form said BEFORE the result:

### Where the lenses WORKED (findable winners)
- **Worcester 1:50 — Knightsbridge 2.9 (BACKED 3.6→2.9).** Last-time-out WINNER, +5lb,
  and his winning comment read like a winner: *"challenged at the last — ASSERTED on the
  run-in."* Every fancied rival's comment read beaten: Culligran *"retreated, beaten well
  out"*, Jullou *"gave out after 12th"*, Majestic Moment *"blundered 3 out, fell away"*
  (he PU'd today). The manner lens alone found this winner. Rule #1 vindicated on live data.
- **Fairyhouse 6:10 — Treasure Rose 6.5.** THE TEACHING CASE: she and Glory To Be were
  BOTH last-time winners raised +3lb — the mark could not split them (our pattern-check
  correctly calls that a no-bet tie). But the COMMENTS split them: Treasure Rose *"hit the
  front, pressed late and HELD"* (game finisher) vs Glory To Be *"found NOTHING in the
  final furlong"* (non-finisher). Winner beat him 0.2L. **When the mark ties, the manner
  is the tiebreaker** — the #29 jigsaw working exactly as drawn.
- **Fairyhouse 5:40 — Monastere 21.0 (BACKED 28→21).** Form 000-02 looks nothing, but the
  last run: 2nd at THIS course 19 days ago, *"drew clear — collared inside final furlong —
  kept on"*, and runs off the SAME mark (41) today. Nearly won off it, C&D, unchanged
  mark, market support. Findable at a huge price.
- **Fairyhouse 7:55 — Pete's Dream 8.0 (BACKED).** Last run: *"moved up to fourth — SHORT
  OF ROOM — could not sustain."* The excuse lens (trouble-in-running upgrade), at a fair
  price. Contrast Phantom Gold below — an excuse/eye-catcher is a BET at 8.0 and a TRAP
  at 2.2: the market had already eaten Phantom Gold's excuse and then some.

### Where the traps fired (findable LOSERS — as valuable)
- **Worcester 2:20 — Lord Chamberlain, +11lb, smashed 6.0→4.5:** beaten 18.5L. RAISED
  HARD + BACKED HARD + SHORT = the worst combination on the card.
- **Worcester 3:55 — Phantom Gold 2.2 (3.2→2.2):** last comment *"finished powerfully —
  CAUGHT THE EYE."* The eye-catcher gamble, overbet to 2.2 in a deep field — mugged a
  nose by a DRIFTER (Mojo Ego 11→13). Extends the day nuance: the smashed short fav
  loses, and an eye-catcher comment is often WHY it got smashed.
- **Worcester 4:55 — Artiste d'Ainay, +7lb recent winner, DRIFTING 5.0→5.5:** 7th, btn
  28. Raised winner + drift = stand off (the Perfidia lesson again, in jumps clothing).
- **Fairyhouse 6:45 (18 ran) & 7:20 (14 ran):** winners (Caitouna 15.0, Kirkland Sioux
  7.0) had NO findable form story — big-field Irish cavalry charges. Our big-field
  lottery flag is RIGHT: these are passes, not puzzles to solve.

### Honest misses
- Worcester 2:20 (Merely A Detail), 3:55 (Mojo Ego), 4:55 (Lacrima): winners' marks OWED
  (no prior win) and comments blank — NOT findable through tonight's window. Lacrima's
  thread worth watching: an OR that slid 117→113→105→102 — the handicapper relenting to a
  winnable mark. A "mark-slide" lead, unproven.

### Banked
1. Manner lens on live comments FINDS winners and SPLITS mark-ties (Knightsbridge;
   Treasure Rose). Already wired into conviction — tonight is its evidence.
2. Raised + backed + short = oppose (Lord Chamberlain, Majestic Moment, Phantom Gold,
   Artiste d'Ainay — four for four tonight).
3. The excuse upgrade pays at a PRICE, is a trap when the gamble has eaten it (Pete's
   Dream 8.0 vs Phantom Gold 2.2).
4. Big-field Irish handicaps: the flag stands — pass.
All directional: one card, small sample, the trial record is the judge.

---

## 2026-07-03 (Fri) — the nap LOST at Chepstow 17:10: the master's dissection, banked

**Result (from the master's photo):** Green Sky (IRE) 9/1 won readily (6yo, OR67,
B R Millman — "towards rear, improved 3f out, led approaching 2f, readily drew away");
Jindri 5/4f 2nd (Oisin Murphy — "led... ridden and headed... no match for winner");
our nap lost. 5 ran, Class 5 fillies' handicap.

**Why the system picked it (honest):** the well-in lens — won last time out,
unpenalised. That single alignment carried it. Nothing in the pipeline asked the
three questions the master asked in ten seconds:
1. **"Stay away from races with young unexposed horses."** The field was young,
   lightly raced fillies — a novice in disguise behind a handicap title. The #13 gate
   reads the TITLE; it never read the FIELD. → fixed: field-exposure gate (#30).
2. **"It was a bad race he won — what about form franking?"** `frank_form` existed
   and the nap path never called it. The pick's last win was hollow and checkable.
   → fixed: the nominee's form is franked before banking; a THIN frank kills confident.
3. **"The jockey was out of his league... Oisin Murphy dictated the race."** Small
   tactical field, elite riders, our claimer outgunned — and the winner came from the
   good stable with the good record. No code lens for jockey class yet — banked here
   as the master's read; the eye covers it until the record earns a rule.

**The market note:** Jindri was backed off the board AND had the best jockey AND
dictated — and still got hammered by the exposed older horse. The money and the
tactics both lost to CLASS-IN-FIELD. In a 5-runner race the smashed fav failing is
the same lesson as the deep-field version (2026-07-01) wearing different clothes:
the gamble is not the form.

**Meta:** the loss is banked in nap.db (settle records it) — the record stays honest.
One pick, one loss, three structural fixes. That is the loop working as built.

---

## 2026-07-03 (Fri evening) — the jigsaw profile wins again, and the clock keeps us honest

**Beverley 7:02 (Cl4, 8 ran): I'M NEXT WON at 2/1F; Emperor Spirit 2nd at 9/2.**
Read form-first off the pre-race brief (pulled 18:39): WELL-IN + 2 course wins + the
yard's NUMBER ONE rider up + 17% in-form yard + fair-priced fav (#19). The brief's TWO
well-in tells in the race finished FIRST and SECOND. This is the Indian Run profile
winning again — n=2 now for "well-in course specialist, stable's top rider, fair price."
Still a small sample; the profile is a lead the record keeps testing, not a law.

**The verification lesson (the master's challenge — "did you cheat?"):** the read
landed in chat after the off, so it is UNVERIFIABLE and counts for NOTHING on the
record, however right it was. Only picks banked in nap.db with a pre-off timestamp
count. Right call, wrong channel = no credit. That discipline is the whole trial.

**The brief's blind spot, caught live:** manner printed '·?' on every horse all night
while the comments were demonstrably flowing — the scorecard's manner lens was
hard-coded OWED from before the comments door opened (2026-07-01). Fixed tonight:
the lens now reads FINISHER / placer! / excuse+ from the history comments, OWED only
when genuinely blank. Tomorrow's brief reads the finish, not just the figures (#1).

**Late calls (pre-off, results unknown at time of writing — settle honestly):**
Giant Haystacks (Wexford 8:00, well-in -9, calculated gamble, move-dependent) and
Qazaq e/w (Beverley 8:40, first-time headgear from 29% yard, #16). Mark them either
way in tomorrow's restudy — no cherry-picking the ones that won.

**SETTLED (master's word, same night):** Giant Haystacks WON the Wexford 8:00 — "won
well." Called pre-off at ~19:44 on one fact: WELL-IN -9lb, the biggest treatment gap
on the remaining card, at a fair 4.4 (#19), flagged as a calculated gamble with the
move as the go/no-go. That's TWO winners tonight read off the same lens stack
(I'm Next 2/1F, Giant Haystacks ~7/2) — the WELL-IN mark doing the heavy lifting both
times. Qazaq (Beverley 8:40 e/w, the #16 headgear tell) still unsettled — mark it
either way tomorrow, no cherry-picking.

Discipline note, again: neither goes on the nap ledger (not banked in nap.db pre-off)
and one evening is noise. But the evening's evidence keeps stacking the same way:
the mark lens finds live ones, the drift rule keeps us off dead ones, and the record
— the real one, banked at 07:30 each morning — is the only judge that counts.

### The master's question, answered: "why weren't tonight's two winners in the morning read?"
Diagnosed against the code, not hand-waved. The evening read used FOUR dots the
conviction engine structurally could not score:
1. **No rule #19.** Rank 2/3 earned the market lens; the FAVOURITE earned nothing,
   ever. I'm Next (2/1F) and Giant Haystacks (7/2F) each lost a lens purely for being
   #1 — the engine had rule #2 without its counterweight.
2. **No magnitude.** "Well-in" scored 1 whether the gap was 0lb or -9lb. Giant
   Haystacks' whole case WAS the -9.
3. **No intent.** The yard's 14-day form and the stable's-#1-rider booking were
   collected by evidence and printed on the brief — and never passed to conviction.
   Half the I'm Next jigsaw couldn't score.
So the engine napped a filly on well-in + 2nd-fav while two stronger profiles sat
capped. FIXED same night: #19 fair-priced-fav lens (>=2.5, cramped still earns
nothing), a heavily-treated lens at -5lb+, and the intent dots wired from evidence
into conviction. Test pins the exact case: the I'm Next profile now outranks the
bare sweet-spot profile. Tomorrow's 07:30 pick is the first with the full jigsaw.

---

## 2026-07-05 — the master's re-evaluation: "learn how to pick the correct TYPE of race"

Two poor naps in a row (2026-07-04/05) and the fault was RACE selection, not horse
selection — "unexposed horses, poor classes and grade, anything could win." Audit of
the engine confirmed it: race choice was a title gate + a big-field flag, nothing else.
No class read. No market-shape read. And the RANKING was blind to race quality — a Cl6
scramble outranked a Cl3 on price alone, so the nap kept landing wherever the raw score
happened to fall, which is exactly how you end up in lotteries.

FIXED (rule #31 — the readability checklist):
1. Bottom-grade gate: Cl6 flat = inconsistent animals, flagged.
2. Market-anchor gate: fav 5.0+ (or 4.0+ in a 12+ field) = the market itself saying
   anything could win. Believe it. Flagged.
3. Exposure gate broadened (age<=5, runs<=5 for half the contenders).
4. Class breaks ties in the ranking: equal reads -> the better-class race gets the nap.
5. The self-study now asks QUESTION ZERO on every result: was this race READABLE at
   all — and scores rule #3 on the scoreboard, so race selection is permanently on
   trial alongside the picks.

EXPECT MORE NO-BET DAYS from here. That is the point — the master passes nine races
to bet the one he's sure of. The nap should live in the most readable race of the
day, not wherever the biggest number fell.

---

## 2026-07-05 (later) — the master's alarm ("you are losing your way"): two agents sent out, both came back with blood

Two audit agents dispatched on the master's order: one forensic (winners vs losers),
one on the learning loop. Findings and fixes, all landed same day:

### Forensic verdict
WINNERS (Indian Run, Great Mates, I'm Next, Giant Haystacks): multi-lens, WELL-IN
anchored, readable Cl3/4 races, exposed fields, fair price 2.5-7. LOSERS (Chepstow,
Celestias Comet): single-lens picks in unreadable races — the mirror image on both
axes. Gate walkthrough proved variants could STILL slip (Cl5/jumps low grade, 4.5 fav
in a 10-runner scramble, 6yo unexposed fields) and three structural faults: the
winning profile advised the prompt but never blocked the bank; a hollow frank only
downgraded; the deep read saw just 4 horses per race while the whole field's evidence
was fetched and discarded (Green Sky at 9/1 = the horse it couldn't weigh). Worst
irony: my "pass is the lazy student's answer" prompt line SHAMED the model into
forcing least-bad picks on bad cards — the exact genesis of both losers.

### Loop audit verdict (13 leaks)
Deadliest: the night study critiqued a pick whose reasoning it could not see — the
case died in the email, so "why_i_picked" was A SELF-CRITIQUE OF AN INVENTED MEMORY.
Also: learning tasks never in the documented schedule (the ledgers were starving);
sceptic kill-reasons discarded (failure modes invisible); rule scoreboard fed nothing;
tracked clues couldn't promote a race into the shortlist and are never settled;
synthesis unscheduled and write-only.

### Fixed today, all pinned
1. PROFILE FLOOR at bank time: well-in + Cl4-or-better + anchored market or NO BET —
   the profile now blocks, not advises.
2. FRANK = VETO: a hollow-win pick is crossed off and the next survivor franked;
   all hollow = no bet.
3. Whole field to the deep read; FOLLOW-tracked horses can promote their race into
   the candidate list; every tracked horse running today rides in the lessons block.
4. The CASE banks with the pick (nap.db migration) and is handed to the night
   critique — no more invented memories. Deep read's own confident/lean now decides
   the CONFIDENT tag.
5. Sceptic verdicts banked as status='refuted' with the ground; synthesis now reads
   all three ledgers (nuances + rule scoreboard + tracked).
6. Gates widened: any-code Cl6, fav>=4.0 in 8+ fields, 6yo unexposed counted.
7. DRIFT GUARD (12:30 task): the banked pick's price re-checked pre-off; 20% drift =
   STAND OFF email. The move — the strongest clue in this log — finally guards the
   stake at the only moment it matters.
8. The prompt's anti-pass shaming removed: a pass is CORRECT off-profile; the
   profile_match checklist is now REQUIRED in the pick's JSON or it doesn't parse.
9. TRIAL.md schedule corrected: 07:30 nap / 12:30 guard / 22:00 night / Sun synth.
