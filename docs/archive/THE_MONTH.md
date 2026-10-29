# THE MONTH — the bar, written before the data exists

The master, 2026-09-20: *"so have we finally created a system that will work,
you have 1 month to provide a return on investment or be shot down."*

Fair. This page fixes what counts as success **before a single day of it has
run**, so that on day 30 neither of us can move the line. That is the same
discipline as `FINAL_CALL_CANDIDATES.md`: a bar chosen after seeing the
numbers is not a bar, it is a story.

**Window: 21 September to 20 October 2026 inclusive (30 days).**

---

## WHAT WAS ACTUALLY FIXED, AND WHAT WAS NOT

Fixed on 20 September: **delivery.** The pick is made by the box at 07:30 on
cron, on a clock that cannot suspend, and the engine banks a named pass when
it declines, so every day carries a row. Three picks in nineteen days was a
plumbing failure and the plumbing is what changed.

**Not fixed, because it was never the thing that broke: the edge.** Nothing
done on 20 September makes a horse run faster. The month tests whether the
method returns anything. It does not start from a position of proof.

## THE HONEST STATISTICS, STATED UP FRONT AND NOT LATER AS AN EXCUSE

Thirty bets is below the master's own bar of "judge nothing under 50 picks",
and the arithmetic says why. At a strike rate around 33%, the standard error
over 30 settled bets is about **9 percentage points**, so a 95% interval is
roughly **±17 points**. A month can detect a disaster. It cannot prove a
modest edge, and it cannot disprove one either.

This is said now, on day zero, because saying it on day 30 would be an
excuse. What follows is built around what 30 days *can* honestly answer.

## WHAT IS MEASURED

Everything comes from `data/record.csv`, exported from `nap.db` by
`racing_edge.school.record_export` and committed so the numbers can be
checked from the repo rather than taken on trust. Level stakes, one point a
bet, settled at SP. Paper stakes only.

The comparison that matters is **against the SP-favourite on the same races**
— the ledger's `favline`. It is his graduation bar of 2026-08-15 and it
controls for the difficulty of the races chosen, which a bare strike rate
does not. Beating a 33% benchmark with 40% shots is not an edge.

## THE DECISION RULE AT DAY 30

**SHOOT IT DOWN if any of these is true:**

1. **Delivery fails.** Fewer than 28 of 30 days carry a banked row. The one
   thing that was actually fixed did not hold.
2. **ROI worse than −40%** over the settled bets. That is outside the noise
   band for 30 bets and is a real answer, not bad luck.
3. **The record still cannot be read from the repo.** If the month's numbers
   come from my recollection again, the month proved nothing and the honest
   verdict is that the project cannot measure itself.

**CLEAR CONTINUE if both:**

4. Level-stakes ROI is **positive**, and
5. it beats the favourite line on the same races on **both** strike and
   return — his correction of 7 September: strike alone flatters the shorter
   horse, return alone flatters the longer.

**THE MIDDLE — and this is the most likely outcome.** Delivery holds, the
return is somewhere between −40% and zero, or positive but inside the noise.
Then the report says exactly that, gives the interval, and **the decision is
his**. What will not happen: the middle dressed up as progress, a favourable
subset quoted as the headline, or a request for more time on the strength of
a promise. If the month lands in the middle, the truthful statement is "30
bets could not settle it", and he is entitled to shoot it down on cost alone.

## WHAT I OWE HIM DURING THE MONTH

- **Every day:** the box banks; I settle, grade and autopsy that night. A loss
  gets Rule One and my error in one sentence. A win gets the win autopsy, and
  a lucky win is called lucky.
- **Every week:** the running numbers from `THE_RECORD.md` — picks, strike,
  ROI, and the favourite line beside them. No adjectives.
- **The bill.** Cost is real money. The health mail prints the real figure and
  it goes in the weekly report; I will not estimate it from memory.
- **No new machinery.** No new ledgers, lenses or thresholds from my own head.
  A pattern the ledgers surface goes to his doorbell.

## THE THREE FAULTS THAT MUST CLOSE INSIDE THE MONTH

From `AUDIT_2026-09-20.md`, in order, one at a time:

1. **The record readable from the repo.** Exporter built 20 Sep and wired into
   the box's settle. **Open question needing his word:** the export writes
   `data/record.csv` and `docs/THE_RECORD.md` on the box, and his standing
   rule is that box-written artefacts are never git-tracked. Getting the
   record into the repo means breaking that rule for these two derived files,
   or shipping them some other way. Until he rules, the export runs and
   prints, but the repo copy is not being written by the box.
2. **One writer, one schema for the settled files**, pinned by a test that
   fails on a corrupt row.
3. **A `TESTING` lesson goes red when its named test has not reported** by its
   named date.

---

*Written 2026-09-20, before day one. Nothing in this page may be edited after
the window opens; a correction is appended and dated.*
