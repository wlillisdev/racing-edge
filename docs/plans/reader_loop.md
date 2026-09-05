# THE READER'S LOOP — three artefacts, FOR HIS RULING (bot G, 2026-09-05)

Read: docs/DOWN_TO_TWO_2026-09-05.md, docs/AGE_OLD_PROBLEMS_2026-09-05.md (1, 2, 6, 10), the six settled sheets of 2026-09-05, VETO_SYSTEM / MorningPick / parse_morning_pick (study/morningread.py:524-772), _rank_key (pipeline/nap.py:180-224, inverted today), the candidates loop and objection handling in cli/nap.py, school/sitting.py, the board in cli/health.py and cli/nap.py:213-371. Nothing below is carved.

## A. The four-line verdict block (sittings)

Template, verbatim, at the foot of every sitting sheet:

```
════════ FOUR-LINE VERDICT BLOCK ════════
[HORSE 1]
 1. CLASS LINE  — highest rung WON or PLACED at, with date: "<class/grade>, <won/Nth>, <date>, <course>" (OWED if no date)
 2. WEIGHT SUM (3e) — beaten margin last time v today's weight swing to HORSE 2, one currency: "beaten __L last time; today __lb [better/worse] than H2 = net __L [for/against]"
 3. DANGER'S DECISIVE LINE — the one fact from H2 that could beat H1
 4. MARKET DIRECTION — morning price -> now: "__ -> __ [STEAMER/DRIFTER/FLIP-FLOP/steady/not sighted]"
[HORSE 2] — same four lines, (3) argued from H1
WHAT WOULD MAKE ME WRONG (written BEFORE the verdict — must name a horse): "___"
VERDICT (may cite ONLY the eight lines above): "___"
```

Filled retroactively — Kempton 2:50, 2026-09-05 (under class-first the true top two are Gethin and Pride Of Arras; Constitution Hill's best line is an AW novice win, no rung):

```
GETHIN
 1. CLASS LINE — G3, 2nd (neck) to Ombudsman, Brigadier Gerard S., date OWED
 2. WEIGHT SUM — 133lb, level with Pride Of Arras; beaten margin last time (Eclipse, "faded") OWED — net: level/OWED
 3. DANGER'S LINE (Pride Of Arras) — set the pace and ran 117 in a G2 (York Stakes) two starts back
 4. MARKET — 8/11 -> SP 4/6F: steady
PRIDE OF ARRAS
 1. CLASS LINE — G2 WIN, Great Voltigeur Stakes, date OWED
 2. WEIGHT SUM — 133lb, level; beaten margin last time OWED — net: level/OWED
 3. DANGER'S LINE (Gethin) — the only proven Group/Listed form on THIS surface, course and trip (won the Magnolia here); Pride Of Arras never on the all-weather
 4. MARKET — 7/1 -> SP 11/2: STEAMER (ratio 0.81)
WHAT WOULD MAKE ME WRONG: "If Pride Of Arras dictates a slow pace and Gethin fights Rodriguez for his head, Pride Of Arras's class and the money beat him."
VERDICT: weight (2) is a wash. Class (1) favours Pride Of Arras by a whole rung (G2 win beats G3-second/Listed). Market (4) confirms it (STEAMER v steady). Gethin's only answer is (3), one surface fact against a class gap AND the money. VERDICT: PRIDE OF ARRAS.
```

That is the actual winner at 11/2 over the actual 8/11 favourite, from facts already on the sheet. Settled-twin rule: name which of the eight lines was decisive in hindsight — here line 1, corroborated by line 4, which is the master's own post-race ruling (data/rulings.csv:26-27). Test: a fixture reproducing this block from the sheet's numbers, asserting the resolution order weight-wash → class decides → market corroborates.

## B. The reader ladder

File: data/school/reader_ladder.csv. Columns: date, race, pick, pick_sp, danger, danger_sp, second_danger, second_danger_sp, class_line_horse, favourite, favourite_sp, winner, winner_sp, which_won (pick / danger / second_danger / class_line_horse / favourite / other, joined with + when several apply).

Today's six rows:

| race | pick | danger | 2nd danger | class-line horse | favourite | winner | which_won |
|---|---|---|---|---|---|---|---|
| Haydock 1:55 | Rocket Boy | First Law | — | First Law | First Law | First Law | danger+class_line_horse+favourite |
| Ascot 2:10 | Archers Bay | Heyzoom | Decade Of Time | (Blanco horse, unread) | Heyzoom | Turty Tree | other |
| Kempton 2:50 | Gethin | Constitution Hill | Pride Of Arras | Pride Of Arras | Gethin | Pride Of Arras | second_danger+class_line_horse |
| Haydock 3:05 | Aegean Prince | Stressfree | Finalise | Aegean Prince | Aegean Prince | Aegean Prince | pick+class_line_horse+favourite |
| Haydock 3:40 | Marvelman | Almeraq | Big Mojo | Almeraq | Almeraq | Almeraq | danger+class_line_horse |
| Thirsk 3:15 (duty) | Proposal | Oolong Poobong | — | Oolong Poobong | Oolong Poobong | Oolong Poobong | danger+class_line_horse+favourite |

At n=6 the class-line horse column carries 5 of 6 winners. Renderer: `ladder_scoreboard(rows) -> str` in school/sitting.py (pure, beside sitting_floor :21-36): four strike rates side by side (pick, danger, class_line_horse, favourite) with n and tier0.month_test's shape and bar (tier0.py:99-123, MONTH_MIN_N=30) — it will read THIN for months at one sitting a day; that is the bar working. Banking/settling by hand from the settled twin; a CLI is machinery for his word. Test: tests/test_sitting.py::test_ladder_scoreboard on a fixed 10-row fixture.

## C. The box reader's block and the danger with teeth

Prompt addition to VETO_SYSTEM (morningread.py:524-568) and the schema hint (:570-592): the same four lines for BOTH the engine's pick and the named danger, plus `"danger_beatable": {"answer": "yes|no", "fact": "the cited fact"}`. Wire into MorningPick (:595-627: `danger_beatable: str = ""`, `danger_beatable_fact: str = ""`) and parse_morning_pick (:722-757).

Consequence when "no" — three options, anchored at the objection branch cli/nap.py:1181-1239:
1. PASS the race — rule 8 verbatim (morningread.py:490-495). Mechanism: route through _bank_pass (nap.py:128, as at :975). Risk: the mechanism the master killed on 2026-08-19 ("your vetos are crippling us" — the vetoed King Roly won at 6.0); the record must judge it.
2. LEAN (today): the pick stands, capped, objection printed (nap.py:1198-1205); only the new field rides along for the record. Risk: "no teeth" — 8/34 danger-wins bank this way.
3. SWAP: the danger becomes the pick if it survived elimination and sits within one class rung. Mechanism: all_by_race[nap.race.race_id] (nap.py:992-994); find the danger's NapPick by norm_horse_name; gate on abs(best_class_level difference) <= 1 (NO_CLASS_LINE never "within one rung"); _record_nap (nap.py:107-116) with the danger substituted, labelled a rule-8 swap. Risk: a mechanical swap on a thin class field repeats Kempton in reverse; needs the corpus backfill first.
What the record grades either way: the reader ladder's pick v danger strike.

The board's direction reaching the 12:30 bank (his word, rulings.csv:30): board_moves (nap.py:251-275) fed by 07:30/09:30/12:30 snapshots (nap.py:243-249, health.py:105-114, nap.py:278-311) is read today only by _guard (nap.py:314-371) to protect the STAKE. Hook: inside _guard at nap.py:326-343 after _board_read(day, cards) — if the banked pick's row is DRIFTER/FLIP-FLOP while the named danger's row in the same race is STEAMER, that is the trigger; with the nap moved to 12:30 the same read makes the bet.

Tests: parse test for danger_beatable (missing/malformed never guessed, as _tup/_price at morningread.py:733, 760-772); one test per option's mechanism in tests/test_nap.py.

## One-cut-a-day order

1. A's template — zero code; fixes the sittings on his say-so. 2. B's CSV + ladder_scoreboard — pure measurement. 3. C option 2 wiring only — the field rides into the LEAN path, no behaviour change, so the record grades the question before teeth. 4. His ruling on which teeth. 5. The board hook into the 12:30 bank, after 3-4 are graded.
