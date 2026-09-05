# THE SHADOW LADDER — implementation plan (bot E, 2026-09-05)

Read-only reconnaissance; nothing changed. Anchors are as of main at 19:00Z 05 Sep.

## 0. What already exists

| thing | anchor |
|---|---|
| yardstick row schema (`FIELDS`) | src/racing_edge/school/yardstick.py:39-48 |
| rows banked each morning (every priced runner, `mkt_rank` by morning price, ties by `horse_id`) | yardstick.py:108-159; called at src/racing_edge/cli/nap.py:784-786 |
| `settle_day` fills `pos/sp_dec/won`, non-runner → `won=''` | yardstick.py:187-232; called at cli/nap.py:475-485, :510, :585 |
| `load(root, days)` → typed rows | yardstick.py:269-281 |
| `race_type_band(row)` → pattern / heritage / fingerprint / other | yardstick.py:330-347 |
| the "our pick" mirror of the rank key (the shadow generalises this) | yardstick.py:377-378 |
| `main()` (writes yardstick.md, no CSV arg today) | yardstick.py:538-551 |
| live rank key (class line first since 2026-09-05) | src/racing_edge/pipeline/nap.py:181-224 |
| legacy key | pipeline/nap.py:227-236 |
| cross-off rule ("strongest SURVIVOR after crossing off every horse with a flaw") | pipeline/nap.py:433-440 |
| race gates stapled to EVERY runner of a race | pipeline/nap.py:341-390 (`replace(... flags=(*flags, *race_flags))` at :385-390) |
| `improver-favourite (unexposed, short price)` flag | src/racing_edge/selection/conviction.py:470 |
| `Conviction.best_class_level/_won` | conviction.py:110-111 |
| policy ledger append (one row per (day, policy), dedup) | src/racing_edge/school/daily.py:80-104 (header :97) |
| corpus grind: 5+ runner floor, tie-break `min(sp, horse)`, skip-race-if-no-candidate | daily.py:56-57, :66 |
| ladder bars + verdict + challenger loop | src/racing_edge/school/ladder.py:41-42, :104-150, challengers at :125-132 |
| night chain order | trial.sh:90 (settle) → :95 learn → :100 why → :109 night school → :116 tier0 → :123 yardstick |
| health: ladder verdict + fav freshness | src/racing_edge/cli/health.py:414-425, :426-445; `_check` at :23 |
| constants usable without his word | ladder.MIN_JUDGE=50, ladder.WINDOW=500; tier0.MIN_FIELD=5, tier0.MONTH_MIN_N=30, tier0.RANK_CAP=7 (tier0.py:34-36), tier0.lift_pp :99, tier0.month_test :103 |

There is no ladder TABLE in health today — only the verdict line (health.py:420-425) and the fav-freshness line (:437-445). The per-policy rollup is printed by daily.main at night (daily.py:136-144).

## 1. Decisions

1.1 Namespace: every shadow policy is `shadow:<key>`. (a) Name collision: a plain `fav` would collide with the corpus benchmark in data/school/daily_policy.csv; append_policy_rows dedups on (day, policy) so one silently wins and ladder.verdict reads rows["fav"] (ladder.py:112) and health.py:435 reads last_day(rows,"fav"). The shadow's control is `shadow:fav`, a different population (morning favourite over engine-readable races v SP favourite over all 5+ runner results). (b) Verdict hijack: ladder.verdict's challenger loop (:125-132) treats every non-champion, non-fav policy as a challenger; 50 shadow picks/day clears MIN_JUDGE in one day, so the nap's verdict would read "CHANGE TACK — challenger shadow:…" on the first morning. One line skips the namespace.

1.2 The picking code lives in yardstick.py (owns FIELDS, _typed, load, race_type_band, the rank-key mirror). ladder.py stays a pure reader: it gains the constant and the one-line skip. daily.py stays the single append site. Import direction yardstick → ladder (constant), yardstick → daily (append). No cycle.

1.3 When: inside yardstick.main(), the night step at trial.sh:123, after settle (trial.sh:90 → cli/nap.py:585). No new trial.sh line, no cron, no module. Night school's verdict at trial.sh:109 prints before the shadow rows land — irrelevant, shadow rows never enter a verdict; the 09:30 page reads the CSV fresh.

1.4 Grade the WHOLE ledger every night: append_policy_rows skips rows already present, so re-grading every day in data/school/yardstick/ is free and self-backfilling.

## 2. The variant keys

All keys order runners WITHIN one race, so every race-level term of _rank_key drops out (the bar :220, race_quality :221, race_class :219 are identical across a race's rows). What survives: the class line + the jigsaw + the shorter price.

Reconstructible from FIELDS: confident, mark_known, score, price (morning consensus), class_level, mkt_rank, flags, cautions, pattern, race_class, is_handicap, won, sp_dec.

NOT reconstructible (state in docstring and handoff): (1) conviction.best_class_won (the live key's second term, :214) — the ledger banks class_level and the bucket, never the won flag; on equal rungs the shadow falls through to the jigsaw. Fix = one new column (§8 cut 2). (2) the RAW len(conviction.aligned) (:216) — the ledger banks _joined_keys, deduped on lens_key (yardstick.py:96-97); a lower bound, bites only when confident, mark_known and score all tie.

Crossing off (mirror the engine): nominate_nap (pipeline/nap.py:438-439) keeps only picks with NO flags; cautions never disqualify. A row is crossed off iff its flags column is non-empty. Race gates are stapled to every runner, so a gated race yields zero candidates for every crossing-off variant — the live engine's own behaviour; `shadow:fav` still grades those races, which makes the gate's cost visible.

| policy | pick rule |
|---|---|
| shadow:key-old | over rows with empty flags: min by (-confident, -mark_known, -score, -n_aligned, price, mkt_rank, horse_id) |
| shadow:key-class | same candidates: min by (class_level or 99, *old key) — the live key minus best_class_won |
| shadow:key-class-noflag | candidates = rows whose flags MINUS the key `improver-favourite` is empty; then the key-class order |
| shadow:key-class-pattern | key-class, only for races where race_type_band(row) in ("pattern","heritage") |
| shadow:fav | rows with mkt_rank == 1, tie-break horse_id. NO cross-off — a control that inherits the gates is not a control |

Ties: every key ends (…, mkt_rank, horse_id) under min(), mirroring daily.pick_for (daily.py:57). Which races count: a race is graded only if some row has won == 1 (as _bands_by, yardstick.py:362-366); if the chosen row's won is not 0/1 (non-runner/absent/withdrawn), that race contributes NO pick for that key (voids, no hindsight re-pick). No field-size floor (the engine has none; shadow:fav sits in the same population). A day/key with zero picks writes no row.

## 3. Code to add

3a. ladder.py — after WINDOW = 500 (:42):
```python
SHADOW_PREFIX = "shadow:"   # THE SHADOW LADDER (the master, 2026-09-05: "we have 50
                            # races a day... do all the testing on the shadow"): variant
                            # rank keys graded nightly off the banked yardstick rows.
                            # Namespaced because they are MEASURED, never CROWNED.
```
At :126-128 the challenger loop: `if p in (champion, "fav") or p.startswith(SHADOW_PREFIX): continue`.

3b. yardstick.py — new block after _race_type_bands (after line 393, before _version_table :396):
```python
from racing_edge.school.daily import append_policy_rows
from racing_edge.school.ladder import SHADOW_PREFIX

SHADOW_KEYS = ("key-old", "key-class", "key-class-noflag", "key-class-pattern", "fav")

def _tags(row: dict, field: str) -> set[str]:
    return {t for t in (row.get(field) or "").split("|") if t}

def _n_aligned(row: dict) -> int:
    """len(conviction.aligned) as the LEDGER can see it — the deduped lens_key count, a lower bound."""
    return len(_tags(row, "aligned"))

def crossed_off(row: dict, keep: tuple[str, ...] = ()) -> bool:
    """Mirror pipeline/nap.py:438: ANY flag disqualifies, cautions never do. `keep` names flag keys that do NOT cross off."""
    return bool(_tags(row, "flags") - set(keep))

def shadow_rank_key(row: dict, *, class_first: bool) -> tuple:
    """SMALLER IS BETTER (min()). class_first=True mirrors _rank_key (:213-224); False mirrors _rank_key_legacy (:227-236). Race-level terms dropped on purpose."""
    horse = (-int(row.get("confident") or 0), -int(row.get("mark_known") or 0),
             -int(row.get("score") or 0), -_n_aligned(row),
             float(row.get("price") or 9e9), int(row.get("mkt_rank") or 99), str(row.get("horse_id") or ""))
    if not class_first:
        return horse
    lvl = row.get("class_level")
    return (99 if lvl in (None, "") else int(lvl), *horse)

def shadow_pick(race_rows: list[dict], key: str) -> dict | None:
    if key == "fav":
        cands = [r for r in race_rows if r.get("mkt_rank") == 1]
        return min(cands, key=lambda r: str(r.get("horse_id") or "")) if cands else None
    if key == "key-class-pattern" and race_type_band(race_rows[0]) not in ("pattern", "heritage"):
        return None
    keep = ("improver-favourite",) if key == "key-class-noflag" else ()
    cands = [r for r in race_rows if not crossed_off(r, keep)]
    if not cands:
        return None
    return min(cands, key=lambda r: shadow_rank_key(r, class_first=(key != "key-old")))

def shadow_day_rows(rows, keys=SHADOW_KEYS) -> list[tuple[str, str, int, int, float]]:
    """(day, 'shadow:<key>', picks, wins, returned) — the five-tuple append_policy_rows takes; level stakes at SP."""
    by_day_race = defaultdict(list)
    for r in rows:
        by_day_race[(r.get("date") or "", r.get("race_id") or "")].append(r)
    tally = defaultdict(lambda: [0, 0, 0.0])
    for (day, _rid), rs in by_day_race.items():
        if not any(r["won"] == 1 for r in rs):
            continue
        for k in keys:
            p = shadow_pick(rs, k)
            if p is None or p["won"] not in (0, 1):
                continue
            t = tally[(day, k)]
            t[0] += 1
            if p["won"] == 1:
                t[1] += 1
                t[2] += float(p["sp_dec"] or 0.0)
    return [(day, f"{SHADOW_PREFIX}{k}", t[0], t[1], t[2]) for (day, k), t in sorted(tally.items()) if t[0]]

def grade_shadow(rows, csv_path: Path, keys=SHADOW_KEYS) -> tuple[int, int]:
    """Append the shadow's day rows; -> (written, skipped). Idempotent via append_policy_rows."""
    day_rows = shadow_day_rows(rows, keys)
    skipped = append_policy_rows(csv_path, day_rows)
    return len(day_rows) - skipped, skipped

def shadow_table(rows, keys=SHADOW_KEYS) -> str:
    """The night's rollup over the whole ledger — the columns daily.py:140-144 prints."""
```

3c. yardstick.main(): add `--policy-csv` (default `<root>/../daily_policy.csv`, derived from root so tests that pass `--root tmp` never write the repo's ledger); after print(text): `written, skipped = grade_shadow(rows, csvp); print(shadow_table(rows)); print(f"shadow ladder: {written} row(s) written, {skipped} already graded -> {csvp}")`.

3d. health.py — extend the open block at :426-445 (it already holds `_rows`; do not load the CSV again). Print a `shadow ladder (...)` block: one line per policy `name n= strike= ROI=`, sorted by strike, then `last graded <date> · PROVISIONAL until 500 picks (the graduation bar) — nothing here moves a pick or a rule.` The `school ladder:` verdict line above it must be byte-identical to the day before.

## 4. MIN_JUDGE / WINDOW at ~50 picks a day

MIN_JUDGE=50 is cleared in 1-2 days, WINDOW=500 in ~10. Fifty picks is not a verdict (SE ≈ 6pp at 25%). The guard, existing constants only: (1) structural — shadow policies excluded from ladder.verdict; promotion is a doorbell decision always; (2) printed — PROVISIONAL until 500 (ladder.WINDOW as the belief bar); (3) later — tier0.month_test when two calendar months exist. Anything tighter is a new threshold and needs his word.

## 5. Back-fill

data/school/yardstick/ is gitignored (.gitignore:105-106) and lives on the box only; started 2026-09-03 (3 files at most tonight). First grade_shadow run grades every day the ledger holds. Check on the box: `ls -la data/school/yardstick/; wc -l data/school/yardstick/*.csv`.

## 6. Tests (existing files)

tests/test_yardstick.py (reuse `_row` at :159-166, add class_level/pattern to base):
1. test_shadow_pick_mirrors_the_live_key_and_crosses_off_flags — A (level 9, score 4, confident, 2.5, no flags), B (level 4, score 1, 8.0, no flags), C (level 2, score 5, 3.0, flags "big-field lottery"): key-class → B, key-old → A, C never. Fails with the crossed_off filter deleted.
2. test_shadow_keeps_the_improver_favourite_only_for_the_noflag_variant — C flags exactly "improver-favourite": key-class → B, noflag → C; "improver-favourite|big-field lottery" crossed off by both.
3. test_shadow_grades_only_settled_races_and_voids_a_non_runner_pick.
4. test_shadow_pattern_variant_grades_only_pattern_and_heritage_races.
5. test_shadow_rows_are_namespaced_and_idempotent(tmp_path) — grade twice: (written>0, 0) then (0, written); file unchanged; every policy starts with "shadow:".
6. extend test_main_writes_markdown (:227-243): daily_policy.csv exists beside root and contains ",shadow:fav,".
tests/test_school_mine.py (owns the ladder tests): 7. test_shadow_policies_never_challenge_the_champion — nap 60 picks HOLD, fav 60, shadow:key-class-pattern 60 at +200% ROI: verdict identical with and without the shadow rows; "shadow:" not in the verdict. Fails with the skip removed.

## 7. REVERT-IF, live check, cost

REVERT-IF: the 09:30 `school ladder:` verdict line changes wording on the first morning shadow rows exist, or the night's yardstick step exits non-zero / mails night:yardstick.
Live check: (1) the 22:00 mail's yardstick output prints `SHADOW LADDER —` and five `shadow:… picks=N` lines and `shadow ladder: N row(s) written, 0 already graded`; (2) `grep ',shadow:' data/school/daily_policy.csv | tail -20`; (3) re-run by hand → `0 row(s) written`, md5sum unchanged; (4) tomorrow's 09:30 page shows the block with n>0 and the verdict line unchanged; (5) sanity: shadow:key-class picks in the same ballpark as the day's `engine` row.
Cost: zero.

## 8. The one-cut sequence

Cut A (inert guard): ladder.py constant + skip + test 7. Cut B: the yardstick block, main() wiring, the health block, tests 1-6. Never B before A. Do NOT add anything to data/school/policies.txt (it feeds daily.pick_for over the corpus). Merge before 20:00. Handoff entry: the shadow ladder, the two fidelity gaps, the PROVISIONAL bar, the REVERT-IF.
Cut 2, a later day: add `best_class_won` to FIELDS and rows_from_field and as the second term of shadow_rank_key so key-class mirrors the live key exactly.

## 9. Risks

Look-ahead: clean — every ranking column is written at 07:30; won/sp_dec only grade. Survivorship: the shadow measures keys on the population the engine reads; shadow:fav ≠ the corpus fav; never compare a shadow line to the corpus fav. Champion/verdict semantics unchanged and pinned by test 7. Frozen partial days: a late-settled race keeps the earlier count (same imprecision the engine/fav rows carry; manual repair by deleting the day's shadow lines and re-running). Two fidelity gaps named. No rule born here.
