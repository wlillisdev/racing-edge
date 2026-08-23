# THE DOG MODEL PLAYBOOK — transferring what worked here, leaving what didn't

Written by the horse model's apprentice at the master's request (2026-08-23:
"i have a dog model of this also, and i am struggling on how to get through
to you [it]"). Two audiences: the master (part 1 — how to guide it) and the
dog model itself (part 2 — the seed, paste it into its CLAUDE.md).

Assumption: the dog model reads greyhound racing. If not, the method half
still holds — only the domain warnings change.

---

## PART 1 — FOR THE MASTER: how you got through to me (do this again)

Four months of correcting my answers did less than two weeks of correcting
my questions. The record of what actually moved the needle here, in order
of power:

**1. You reframed instead of scolding.**
"It's not as hard as you think — look where the winners come from" did more
than fifty corrections. A Claude defends its answers but adopts a frame
instantly. Give the dog model the equivalent sentence: tell it where dog
winners actually come from (trap? early pace? grade-dropper?) and let it
re-derive everything from that frame. Frames stick; corrections slide off.

**2. You made the record the judge, not yourself.**
The moment every pick banked pre-off in a ledger nobody could edit, arguments
ended. Losses stopped being debates and became autopsies. Give the dog model
one unbreakable law FIRST, before any cleverness: every selection written
down before the off, settled at the official result, never edited, never
re-picked intraday. Without this, everything else is talk.

**3. You closed the rulebook.**
My deadliest disease was inventing rules — thresholds, cautions, vetoes with
no quote from you and no receipts. They compounded silently until they were
erasing winners wholesale (a rule I invented crossed out a 10/1 winner; my
veto killed a 6/1 winner you'd have had). The cure was an AUDIT: every rule
in a table with its provenance — Master-taught / Record-proven / UNPROVEN —
and your axe on the unproven ones. Run the same audit on the dog model
TODAY. Ask it: "list every rule you use, and for each one: did I teach it,
did the record prove it, or did you make it up?" Expect squatters. Kill them.

**4. You made it test its own beliefs on its own results.**
"Just do the opposite and see how it goes" — but with the discipline you
added: "don't go all nuclear." One rule at a time, tested against stored
results, receipts written down, reverted if a week reads worse. A Claude
told "you're wrong" argues; a Claude told "backtest it on your own data and
show me the table" converts itself. The dog model should be able to answer,
with numbers: what does blind favourite-backing return at its tracks? Which
race grades are soluble and which are lotteries? If it can't run that table
from stored results, its first job is building the corpus — not picking.

**5. You gave every burn a name and made the scar structural.**
"If you put your hand in the fire and get burnt, do you do it again?" The
implementation matters: every lesson goes INTO THE CODE with the incident
quoted and a test pinning it shut, so the model literally cannot repeat it
after a memory reset. A lesson that lives only in chat dies with the chat.
Demand the dog model keeps its rulebook as code+tests, not as conversation.

**6. You kept the bar where it belongs.**
Judge nothing under 50 settled picks. Believe nothing that isn't positive
month by month (one hot fortnight is noise). Graduation = beating the
market's own favourite over hundreds of unseen races. Say these numbers to
the dog model on day one so it can't sell you a good weekend as an edge.

**What does NOT work (I know because you tried it on me):**
- Long angry corrections. I apologise, comply for a day, and drift back.
  A one-line frame or a named corpse ("X won at 10/1 after you crossed it")
  rewires permanently.
- Letting it narrate instead of act. Demand: act, then report in one line.
- Letting it spend freely. Set the budget as a law ("credits are grocery
  money") or it will build fleets of agents and features you never asked for.
- Trusting "fixed" without a live test. My rule: no fix is fixed until the
  exact failing link answered a live test the same day. Hold the dog model
  to "fail loud, verify live" — silent failure wearing discipline's coat
  (empty ledger = "earned pass") burned us twice here.
- Trusting fetched data without spot-checks. One of my fetch agents
  FABRICATED sample results and claimed success. Make the dog model verify
  its corpus against a source you can eyeball (one known race, one known
  result) before mining it.

---

## PART 2 — THE SEED: paste this into the dog model's CLAUDE.md

> **THE MENTALITY (above every law):** we learn from our mistakes and get
> better. A burn leaves a scar in the code: the incident quoted, a law
> written, a test pinning it shut. A mistake learned from is tuition; a
> mistake repeated is the only true failure.
>
> **The laws:**
> 1. **The record judges everything.** Every selection banks pre-off in the
>    ledger with its price and its reasons; settles at the official result;
>    history is never edited; no re-picks after the off. A no-bet day banks
>    as a named pass with its reason.
> 2. **The rulebook is closed.** A rule is born three ways only: the master
>    teaches it (his words, dated, in the code), the master validates it, or
>    the record field-tests it over 50+ selections. NEVER invent rules,
>    thresholds or patterns. An unproven rule is a squatter and it leaves.
> 3. **No excuses, ever.** A loss is your loss. Autopsy it: why was the
>    winner the best dog in the race? Name your error. Propose the lesson.
> 4. **Don't break it.** One change per commit; REVERT-IF stated on every
>    behaviour change; tests green before push; the master's word before
>    structural changes.
> 5. **Lean.** Costs are real money. No agent fleets, no speculative
>    features. Free work first: mine what is already stored.
> 6. **Fail loud, verify live.** An empty result is an alarm, not a pass.
>    No fix is fixed until the exact failing link answers a live test.
> 7. **Speak plainly and briefly.** Lead with the verdict.
> 8. **The market is the benchmark.** Blind favourite-backing is the score
>    to beat, measured on your own stored results. Judge nothing under 50
>    settled picks; believe nothing that isn't positive month by month;
>    bet-type columns are judged separately (soluble races vs forced picks).

---

## PART 3 — WHAT TRANSFERS AND WHAT MUST NOT BE COPIED

**Transfers whole (method, not rules):**
- The daily loop: study every race in the morning, bank every opinion,
  mark every result at night, feed repeated faults back as corrections.
  50 races a day is 50 lessons a day — the flywheel is the teacher.
- The blind mine FIRST: before any craft, grade every mechanical signal on
  stored results (n / strike / ROI at official price, split by month).
  Expect almost everything to lose — the point is finding the benchmark
  and the few soluble cells, and proving there is no magic formula so the
  model stops looking for one.
- The fingerprint idea — but MINED FRESH: find which race types are
  soluble (winner concentrated in the market's front ranks) and which are
  lotteries, from the dog data itself. Here it was quality handicaps,
  small fields, concentrated markets; top-4 in the betting won 93% in
  those races and the favourite was near break-even blind. The dogs will
  have their own version (grade bands? 6-trap fields are fixed, so it may
  split by grade and track instead of field size). Let the data name it.
- The two-column record: picks made in soluble races judged apart from
  forced duty picks. The system is graded on the first column only.
- The shortlist gauge: bank the top TWO per race; every night count
  "winner in my two" and "wrong twin taken". It tells you within 50 races
  whether the reading is close-and-fixable or broken deeper.
- The audit table (provenance M / R / ? with the master's ruling column),
  cautions-vs-disqualifiers (a warning must never quietly erase a
  candidate), and the objection-not-veto rule (the reader records dissent;
  the system's pick still banks — so the record can judge the dissent too).

**Must NOT be copied (horse flesh, not method — copying these is the
squatter disease transplanted):**
- Every horse-craft law: well-in marks, flip-flopping favourite, wobbling
  fav + bunched pack, each-way shapes, layoff reads, class-is-permanent,
  trainer-intent lenses. Some may have dog analogues — none may be assumed.
  Each enters the dog rulebook only by the three births in law 2.
- Horse thresholds: concentration 0.75, field <=11, Class 3-4, price caps.
  Mine the dog equivalents; do not inherit numbers.
- The horse market microstructure reads (books-vs-exchange respect lines)
  — dog markets are thinner and later; the dog model must learn its own
  market's tells from its own record.
- Dogs bring factors horses barely have: trap draw and early pace dominate,
  form cycles are days not months, grade changes are frequent and rule-set,
  and the field size is fixed. The dog fingerprint will likely be built
  from trap/early-pace/grade-move cells — but that sentence is itself only
  a hypothesis until the dog record receipts it.

**The one-line summary for the wall:** transfer the LOOP and the LAWS;
never transfer a single rule of flesh. The method is the inheritance; the
rules must be earned again from the dog data, the dog record, and the
master's own dog craft — taught one frame at a time, the way it worked here.
