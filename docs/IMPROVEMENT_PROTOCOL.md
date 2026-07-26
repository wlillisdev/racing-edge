# THE IMPROVEMENT PROTOCOL — getting better without wrecking it

**Dated 2026-07-26. Signed actors: THE MASTER (the owner), THE RECORD (settled rows in
nap.db + nuances.db), THE TESTS (the 128 pinned tests), THE CORONER (the nightly
self-study).**

The system's worst losses came from improving it: thresholds refit after single bad
days, lenses added faster than verified, a learning loop that rewrote behavior nightly
(git log: the coroner fixes, the Saturday wipe-out, the value audit). This protocol is
the answer to "how do we get better" — and it is held to the same standard as a pick:
numbers, named approvers, and a revert clause written before go-live.

## 1. THE LADDER OF CHANGE — every improvement has a rung, every rung a price

| Rung | Change | Evidence to go live | Approves | Testing path |
|---|---|---|---|---|
| 0 | New margin-note lesson (nuance row, `proposed`) | 1 race. Free. | Nobody — auto | Dedup vote (Jaccard >=0.6 -> seen_count+1); rides capped (3 proposed / 4 field-tested lines in the prompt) |
| 1 | Lesson promotion to `field-tested` | >=5 settled forward-clues on its theme at >=60% held (`field_test_themes`) | THE RECORD, automatically | None — it only reweights prompt text |
| 2 | Prompt wording change (NAP_SYSTEM, build_nap_prompt) | Side-by-side deep-read output on 3 recent cards showing intended difference and no other | THE MASTER | 128 tests green + adversarial review (a second read hunting for what the wording breaks) |
| 3 | Lens weight / lens add-remove | Lens attribution: >=10 settled picks carrying the lens AND win-loss gap >= 2*sqrt(n) (same rule build_lessons applies to rules) | RECORD proposes, MASTER approves | 14 settled challenger-shadow days (S2b) before the live config changes |
| 4 | Threshold or floor value (anchor bar, conviction bar, 5/60% promotion bar, drift 20%) | >=30 settled challenger bets, OR >=100 backtested picks per docs/optimisation_protocol.md sample gate | MASTER + RECORD (both, in writing in the commit) | Challenger shadow full window; the new number lands with a pinned test asserting it |
| 5 | Gate add/remove/rewire (profile floor, frank veto, top-class door) | Same as rung 4 PLUS a named loss or wrong-kill it would have prevented, cited by date | MASTER only, inside a review window (S3) | Challenger shadow + a new pinned test per gate branch |
| 6 | Structural refactor | Zero behavior change — proof, not promise | MASTER | 128 tests green + one dual-run day producing byte-identical picks/passes. Any diff -> it is not a refactor; reclassify to rung 4/5 |

Anything not on the ladder is rung 5 by default. When in doubt, round the rung **up**.

## 2. THE SHADOW PATH — trial without touching the live method

**(a) Napcheck backtests — limited, and here is exactly why.** `data/client.py`
(racecards): on the Standard tier, past dates return an honest empty — *past cards are
Pro-only*. So napcheck can only replay history when `RACING_API_CARDS=pro`; on Standard
it replays silence and a careless reader would call that "all pass days." Napcheck also
tests only the mechanical skeleton — the deep read is not in the loop. Verdict: useful
for rung 3-4 skeleton checks *when on Pro*; never sufficient alone; never available as
routine on Standard.

**(b) CHALLENGER vs CHAMPION shadow ledger — the recommended path.** The infrastructure
exists: `naplog.py` already carries a `shadow` table with record/settle/strike, banked
inside the morning run and settled inside `--settle`. Minimal extension (~40 lines):
add a `method TEXT` column to `shadow` (migration in `__init__`, same `ALTER TABLE`
pattern as `case_text`); each morning, after the champion banks, re-run the *changed*
config (the challenger's gate/threshold/weight values) over the already-fetched field
and `record_shadow(method="challenger-<name>")`; settle both in the same `_settle`
pass. Cost: zero extra API calls (the evidence is already in memory), zero risk (the
live ledger and the emailed pick are untouched). Verdict at window end: challenger
beats champion only if its level-stakes P/L at SP is higher over >=30 settled
challenger bets AND its strike rate is not worse by more than 2*sqrt(n). One
challenger at a time.

**(c) Paper-only trial windows.** For changes the shadow can't express (prompt changes
needing the deep model): run the variant by hand each morning, log picks in a dated
text ledger before off-time, settle by hand. Honest but expensive in attention;
reserve for rung 2.

**The cheapest honest one is (b).** It is forward-looking (no look-ahead possible),
tier-proof (no Pro dependency), settles itself, and produces exactly the evidence
rungs 3-5 demand.

## 3. THE CADENCE — tinkering has a season

- **The monthly review window:** the first Sunday of each month, one sitting. Inputs:
  `nap --record` (strike, level-stakes P/L, lens attribution), the clue scoreboard,
  the rule tally, any completed challenger verdict. The monthly ROI go/no-go gate is
  finished as part of this window's checklist: **level-stakes P/L over the trailing 60
  settled bets >= 0.0pt = GO; below = the month's only permitted work is investigating
  why — no new lenses, no loosening.**
- **Budget: at most 2 changes per window, at most 1 at rung >=3.** A queued third idea
  waits — it will still be true next month if it was ever true.
- **Between windows the system just runs.** Rung 0-1 learning continues nightly (it's
  ledger-only). Everything else is queued as a dated note in the homework log.
- **The emergency lane** exists ONLY for: an uncaught exception, a RED line in
  health.py, or a ledger writing falsehoods. A losing streak — of any length — is not
  an emergency; the record is allowed to be cold. Emergency commits must cite the
  traceback or the RED line in the commit message.

## 4. THE ROLLBACK RULE — the revert is written before the change

Every rung >=2 change goes live as **one commit** whose message contains a
`REVERT-IF:` clause naming (a) the metric (level-stakes P/L at SP unless stated
otherwise — declared in advance, no metric shopping after the fact), (b) the window in
settled bets, (c) the number. Example: `REVERT-IF: live P/L trails the pre-change
trailing-30 baseline by 5.0pt over the next 30 settled bets.` No clause, no merge.
Reverting is `git revert <sha>` — never a hand-edit — followed by the 128 tests green.
A revert is a normal outcome, logged without ceremony; the change may re-queue with
better evidence. Default clause when none is argued: **revert if the next 30 settled
bets' P/L is >=5.0pt worse than the trailing-30 P/L at go-live.**

## 5. THE STUDENT'S SIDE — full-speed learning inside the regime

The nightly self-study never slows down, because it never touches code: it writes
nuances (proposed, themed, with mechanism and fails_when), forward clues (28-day
broom, settled on the run), rule evidence, and votes (seen_count) — and
`build_lessons` carries all of it into the next morning's exam, honestly labelled by
tier. Promotion is earned two ways only: THE RECORD (5+ settled clues at 60%+,
automatic) or THE MASTER (`validated`, his word alone). The student proposes at
machine speed; nothing it proposes changes behavior until a rung's price is paid.

**The master's 10 seconds a day:** read the morning email; when a proposed nuance with
seen_count >=3 appears in it, answer with one word — *validate* or *reject*. That
single word is the highest-bandwidth training signal in the system: it is the only
path to `validated`, and a rejection kills a bad idea months before the record could.

## 6. FAILURE MODES OF THE PROTOCOL ITSELF — one tripwire each

| Rot | Tripwire |
|---|---|
| Review windows quietly skipped | health.py goes RED if no `REVIEW:` stamp commit in 45 days — the daily email nags until the window happens |
| Emergency lane becomes the fast lane | Any month with >2 emergency commits, or one lacking a cited traceback/RED line, forces the next window's agenda to be "the protocol itself" — no other changes that month |
| Thresholds quietly redefined | Every number in this document is asserted by a pinned test (extend the 128 to cover 5/60%, 2*sqrt(n)/n>=10, the 20% drift, the anchor bar); editing a threshold test IS a rung-4 change and cites this file |
| Challenger killed early when it looks bad | A challenger window that ends before 30 settled bets is logged BURNED; the same change cannot re-trial for 60 days |
| Metric shopping after results | The judge is named in the REVERT-IF clause before go-live; any post-hoc appeal to a different metric is void on its face |
| Lesson inflation drowning the prompt | The caps (3 proposed / 4 field-tested / 8 leads) are pinned by test; raising a cap is rung 4 |
| The protocol document itself drifts | This file changes only by a rung-5 entry: master's approval, in a review window, with its own REVERT-IF |

The system's edge, if it exists, will be visible in the record slowly. The improvement
process exists to be slower than the record, never faster — the last two months proved
that every shortcut around that sentence has a price in points.
