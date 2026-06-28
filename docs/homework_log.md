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
