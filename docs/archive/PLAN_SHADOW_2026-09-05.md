# THE SHADOW — the plan (2026-09-05, night)

The master: "proof faster than fifteen mornings exactly, my point — we have
50 races a day, surely we can easily be testing this and learning, even if
it is just a shadow system to feed into the main system. We have the power
to accelerate this. Do all the testing on the shadow." Then: "send out bots
on how we are going to put a plan in place to solve this ongoing problem."

Three plans came back (full text in docs/plans/). This page is the order.
Each day is one cut, one PR, the suite green on GitHub before merge, the
live check the same day. Nothing here moves a live pick without his word.

## The three pieces

| piece | what it is | cost | plan |
|---|---|---|---|
| THE SHADOW LADDER | every night, from the yardstick rows already banked (50 races a day, every priced runner's read), five variant keys each name a pick per settled race and ride into the policy ladder as `shadow:` policies: `key-old`, `key-class`, `key-class-noflag`, `key-class-pattern`, `fav` (the control). Namespaced so they can never crown themselves; one line in the ladder so they never challenge the nap's verdict. Health prints the table, marked PROVISIONAL until 500 picks. | zero API, zero tokens | docs/plans/shadow_ladder.md |
| THE BACKWARD REPLAY | rebuild past races from the results door (one call per 50 races, full field with OR, weight, draw, headgear, SP), cut every history strictly before the race day (`as_of`), run the SAME evaluate_field once per race and rank three ways: the old key, the new key, the new key with the improver flag demoted. First the ~40 settled sittings (~400 calls, 10 min), then 7 days (~1,600 calls, ~1.5 h, overnight). SP stands in for the morning price — declared, confined, identical for all three keys so the head-to-head is clean. Twelve leaks named, each with its guard; the current-stats doors RAISE in replay so a missing `as_of` crashes instead of leaking. | ~2,000 API calls on the plan, zero tokens | docs/plans/backward_replay.md |
| THE READER'S LOOP | (A) the four-line verdict block at the foot of every sitting: class line, weight sum, the danger's decisive line, the market's direction, for the top two; "what would make me wrong" before the verdict; the verdict cites only those eight lines. Filled retroactively on today's Kempton 2:50 it resolves to Pride Of Arras, the winner, from facts already on the sheet. (B) the reader ladder CSV: pick, danger, second danger, class-line horse, favourite, winner per sitting; four strike rates side by side. (C) the box reader's block and the danger with teeth: the `danger_beatable` field, and three consequences when "no" — PASS (his rule 8 verbatim; the King Roly burn is the risk), LEAN (today), SWAP to the danger if it survived elimination and sits within one rung. FOR HIS RULING. | zero | docs/plans/reader_loop.md |

## The order, one cut a day

| day | cut | live check |
|---|---|---|
| Sun 06 Sep, after 09:30 | THE RECEIPTS REGISTER + its test (every rule, flag, threshold in the engine with its birth road; an unreceipted rule turns the suite red). | the suite red on a planted unreceipted label, green with its row |
| Sun 06 Sep | THE SHADOW LADDER, cut A (the guard: `SHADOW_PREFIX`, the challenger skip) then cut B (the grader in the yardstick night step, the health block). Merge before 20:00. | the 22:00 mail prints the SHADOW LADDER block and "N rows written"; the 09:30 page next morning shows the table with n>0 and the nap's verdict line byte-identical |
| Mon 07 Sep, after 09:30 | THE NAP AT 12:30 (his word: "we don't really need to do the nap so early"): the 07:30 read makes the shortlist and mails it; the 12:30 guard applies the board's direction to the top two and banks. | the 12:30 mail carries the bank with the direction line; nap.db holds the row after 12:30, not 07:30 |
| Tue 08 Sep | THE REPLAY, commits 1-2 (adapter, client with raising doors, shape-book seed) + the single-race live check against the real door. | `--race rac_32294411110` prints the door, the histories before the day, the INVERSION line; no history row dated today |
| Wed 09 Sep | THE REPLAY, commits 3-5 (the three keys, the report, the `trial.sh replay` verb); run `--sittings`; the head-to-head to his doorbell. | the report file exists; n_disagree and old v new on the sittings |
| Wed night | run `--days 7` overnight after the 22:00 chain. | the 7-day report; RACE TYPE split; the month test verdict verbatim |
| Thu 10 Sep | THE READER LADDER (B) + the four-line block template (A) written into the sitting procedure; today's six rows entered by hand. | the ladder prints four strike rates for n=6 and says THIN |
| Fri 11 Sep | THE DANGER WITH TEETH, wiring only (C, option 2): the `danger_beatable` field rides into the LEAN path, no behaviour change, so the record grades the question before teeth are added. | the 07:30 mail shows the field answered |
| his ruling | which teeth (PASS / LEAN / SWAP); the improver flag to a caution; pattern races and the twelve-declared penalty; the corpus columns and the 12-month backfill. | — |

## What the shadow cannot do, said once

It tests the engine on the population the engine reads. It cannot test the
reader (the case, the danger, the objection): those exist only for the three
races the deep read sees each day, and stay judged the slow way on the
reader ladder. And a shadow key that beats the live key over the window is
a REPORT to the doorbell, never a carve: the rulebook is closed.
