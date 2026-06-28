# Homework Log — the apprentice marking his own results

Dated forensic reads of real results. The notebook holds the *rules*; this holds
the *evidence* — what I actually found studying winners and losers, and the lesson
I banked. Numbers are **directional** until the sample is large; small samples lie.

The grunt work is automated: `python -m racing_edge.cli.homework` mines every
studied race in the study DB and prints the forensic read. This log is where I
write down what it (and the post-mortems) taught.

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
