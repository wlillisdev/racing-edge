# THE BACKWARD REPLAY — implementation plan (bot F, 2026-09-05)

Goal: the receipt for the 2026-09-05 inversion (_rank_key class-first v _rank_key_legacy) in one evening instead of fifteen live mornings. Measurement only — no pick, no rule, no ledger row moves.

## 0. Three live facts established tonight (plan = standard; do not re-derive)

1. `/results/{race_id}` and `/results?start_date..end_date` return the IDENTICAL full document. Race keys: race_id, date, region, course, course_id, off, off_dt, race_name, type, class ("Class 6"), pattern, rating_band, age_band, sex_rest, dist, dist_y, dist_m, dist_f ("12f"), going, surface, jumps, runners, winning_time_detail, comments, non_runners, tote_*. Runner keys: horse_id, horse, sp, sp_dec, bsp, number, position, draw, btn, ovr_btn, age, sex, weight ("8-13"), weight_lbs, headgear, time, or, rpr, tsr, prize, jockey, jockey_claim_lbs, jockey_id, trainer, trainer_id, owner(_id), sire/dam/damsire(+ids), comment, silk_url, performance_rating, speed_rating. Consequence: for an N-day sweep one `results_range(day, day)` (paged 50, client.py:141) hands every race in full — never result_by_id.
2. Histories for arbitrary PAST horses work on the standard plan through `/racecards/{horse_id}/results` (client.py:214): rows carry date, class, type, dist_f, pattern, going, course, race_name plus the nested field — what past_runs_from_raw (normalise.py:236) needs. The door also accepts start_date+end_date (both or neither); not required because build_evidence cuts at as_of (evidence.py:178-179).
3. The results door names AW courses "Kempton (AW)" (data/school/raw confirms), so `is_aw="(AW)" in race.course` (pipeline/nap.py:415) works on a replayed card.

Precedent to reuse: school/bar_backtest.py does a leak-safe cumulative shape-book replay (_new_cell :112, _accumulate_cell :116, _shape_verdict_for :140, MIN_CELL_N=30 :55). Import those.

## 1. Input sets

(a) The settled sittings — data/school/picks/*.csv + *.settled.csv: 77 pick files, 29 settled; 52 carry a literal `rac_\d+`. Recovery ladder: (1) regex `rac_\d{6,}` on the file; (2) 2026-01-15.csv / 2026-03-28.csv bare old-format ids → "rac_"+digits; (3) filename course+off (exam-2026-08-31-cartmel345 → Cartmel 3:45; last digit run, 3 digits H:MM, 4 HH:MM); (4) duty-*.csv → the settled twin's `race` column `^([A-Za-z'’ ]+?)\s+(\d{1,2}:\d{2})`; (5) excluded and named in the log: duty-2026-08-24/27 (VOID), duty-2026-08-28 (NO PICK), exam-2026-08-28-sedgefield640.VOID, itv7-2026-08-30, duty-2026-08-31. For (3)/(4) the resolution call IS the rebuild call: one results_range(d, d) per distinct sitting date (~16), match course (lowercased, (AW)/(IRE) stripped) and `off` (12-hour "3:15", same as the sheets). Cost: ~24 results calls + ~360 horse_results calls (~5-10 min at the client's 0.25 s throttle).

(b) The last N full days: results_range(day, day) per day → rebuild every race → keep race.is_readable (domain/models.py:157) as evaluate_field does (pipeline/nap.py:250). ~1-2 results calls/day, ~20-25 readable races × ~9-10 runners ≈ 200-250 horse_results/day (~4-8 min). Propose N=7 first (~1,600 calls, 1-1.5 h); --days 14 if clean. Never more than 14 in one sitting; never contend with the 07:30.

Rate limiting: everything through RacingAPIClient._get (client.py:47): 0.25 s throttle, 429 honours Retry-After capped 1-30 s with 6 retries. Set RACING_API_HORSE_RESULTS=standard so the pro-door 403 probe (client.py:200-213) never fires. Resumability: JSON disk cache data/school/replay/cache/<horse_id>@<as_of>.json (a re-run costs zero calls).

## 2. Rebuilding a race from a result document

Design rule: build a RACECARD-SHAPED dict and push it through the existing normaliser (racecards_from_raw, normalise.py:177) — ONE home for normalisation.

```python
# src/racing_edge/school/replay.py
def card_from_result(doc: dict) -> dict:
    """One /results race document -> the RACECARD-shaped raw dict race_from_raw expects.
    Pre-race fields only: position, sp/sp_dec/bsp, btn/ovr_btn, time, prize, rpr, tsr,
    performance_rating, speed_rating are dropped — except sp_dec, confined to the price slot
    and named as the look-ahead it is."""
def outcome_from_result(doc: dict) -> dict:
    """{horse_id: {position, status, sp_dec, btn}} — the answer sheet, kept OUT of the Race and read only by the scorer."""
```

Race level: race_id ✓; date ✓ (normalise.py:181, else uk_today()); course ✓ (keeps " (AW)"); off_time ← `off`; race_name ✓ (drives is_handicap/is_novice/is_amateur :162-164); type ✓; class ("Class 6") via _class (:44); pattern ✓ (_pattern :24 prefers the feed key — the inversion's term); distance_f ← normalise._dist_f(doc) (:220; dist_f is the STRING "12f" — _float would blind the trip lens); going ✓; going_detailed absent → ""; region ✓; surface ✓ (is_all_weather :153-155); runners mapped below; non-runners absent by construction.

Runner level: horse_id, horse, trainer(_id), jockey(_id), age, sex, draw, headgear, sire/dam/damsire ✓; lbs ← weight_lbs (runner_from_raw:133); ofr ← `or` (:134 — the mark it RAN OFF, legitimately pre-race); claim ← jockey_claim_lbs; odds ← [{"decimal": sp_dec}] (omit when missing → unpriced, drops out at pipeline/nap.py:308 as live); last_run ← derived (below); headgear_run absent → headgear_first_time always False; trainer_14_days absent → in-form-yard dark; rpr, performance_rating, tsr, speed_rating NEVER MAPPED (post-race); form, wind_surgery, trainer_location, spotlight absent, none read by conviction; position, sp, btn, ovr_btn, time, prize, comment → outcome only.

Days-since-run: absent, but drives law 2b-ii, 3g-ii _quick_return (conviction.py:259-262) and the solid-fav shield hole (:402). The replay PRE-WARMS the history cache, computes last_run = (race_date − history[0].date).days per runner and writes it into the card; build_evidence is served from the cache — zero extra calls. Named in the report.

The price: no morning price exists in a result. Use sp_dec as odds.consensus and say so. SP touches market rank (sweet spot / fair-priced fav lenses conviction.py:381-421), the improver flag (:469), concentration → race_quality_score, market_shape's open-market flag (nap.py:382), the shape book's fav band, the key's last tie-break. A neutral constant is worse (conviction tests price >= 2.5 / <= 3.0 as absolutes). Why it does not corrupt the verdict: both keys and the no-flag variant read the SAME Conviction from the SAME SP-derived market; _rank_key and _rank_key_legacy differ only in the leading (best_class_level, best_class_won). The head-to-head is clean; the ABSOLUTE strike/ROI is inflated v a live morning — print the head-to-head as the verdict, the absolutes as context (bar_backtest.py:302-303's posture).

Lenses that go blind (fairly, both keys): in-form yard (card trainer_14_days) DARK; stable #1 rider (evidence.py:211-213 skipped under as_of) DARK; local master yard / course jockey (evidence.py:194-209, 220) DARK; trip proven from distance_times (evidence.py:185) DARK but conviction.py:437-443 recomputes trip from same-code history; headgear key DARK; market rank PRESENT but shifted; Signposts rating_clear DARK on purpose. Every one is computed once per runner before either key applies, so the blindness cancels in the head-to-head.

## 3. The scoring

```python
class ReplayClient:
    """The morning's client pointed at a past day. racecards() serves the REBUILT card; horse_results() goes to the
    real door via a per-(horse, as_of) disk cache. Every CURRENT-STATS door RAISES LookAheadError: if as_of ever
    failed to reach build_evidence the replay dies loudly instead of leaking."""
    def __init__(self, api, cards: dict, cache_dir: Path, as_of: date): ...
    def racecards(self, day="today") -> dict: ...
    def horse_results(self, horse_id, limit=30) -> list[dict]: ...
    def trainer_jockeys(self, tid): raise LookAheadError(...)
    def trainer_course(self, tid, cid=""): raise LookAheadError(...)
    def jockey_course(self, jid): raise LookAheadError(...)
    def horse_distance_times(self, hid): raise LookAheadError(...)

def seed_shapebook(as_of: date, raw: Path = Path("data/school/raw")) -> None:
    """Fill shapebook._CELLS_CACHE[raw.resolve()] with cells from corpus races STRICTLY BEFORE as_of, n>=MIN_CELL_N
    only — bar_backtest.py:205's guard reused. evaluate_field:399 → glance_for (shapebook.py:191-207) otherwise
    builds cells from the whole corpus incl. the replayed day. No engine signature changes."""

def replay_race(api, doc: dict, cache: Path) -> dict | None:
    """card_from_result -> ReplayClient -> seed_shapebook(as_of) -> evaluate_field(client, day=as_of.isoformat(), as_of=as_of)
    -> the three keys. None when not is_readable or no priced runner."""

def rank_three(field: list[NapPick]) -> dict:
    """new = survivors sorted by _rank_key (cli/nap.py:882+936); old = max(survivors, key=_rank_key_legacy) (:944);
    noflag = new after demoting the improver-favourite FLAG to a caution. survivors = [p for p in field if not p.conviction.flags]."""

_IMPROVER = "improver-favourite"
def _demote_improver(p):
    hit = [f for f in p.conviction.flags if f.startswith(_IMPROVER)]
    if not hit: return p
    c = replace(p.conviction, flags=tuple(f for f in p.conviction.flags if f not in hit), cautions=(*p.conviction.cautions, *hit))
    return replace(p, conviction=c)
```

Output data/school/replay/<run>/races.csv (gitignored under data/school/): date, race_id, course, off_time, race_class, pattern, is_handicap, race_type, field_size, race_quality, race_type_band, above_bar, winner_horse_id, winner, winner_sp, fav_horse_id, fav, fav_sp, fav_won, pick_old(+id, rank, class_level, sp, won), pick_new(+…), pick_noflag(+…), disagree_old_new, n_survivors, n_priced, sitting_file. race_type_band imported from yardstick (:330), never copied. *_won blank per yardstick.settle_day:212-218.

The report data/school/replay/<run>.md, in bar_backtest.render's voice: (1) TERMS AND LIMITS first (SP as price; field = runners that ran; trainer_14d/headgear_run/performance_rating dark; current-stats skipped; days_since_run reconstructed; shape votes leak-guarded; the fairness sentence); (2) THE HEAD-TO-HEAD — only races where disagree_old_new: n_disagree, old/new/noflag wins, level-stakes P/L at SP on that subset; (3) WHOLE-SET strike/ROI per key + fav benchmark; (4) BY RACE TYPE; (5) BY BAR; (6) MONTH TEST via tier0.month_test with exp from a market-rank control as yardstick._control (:287) — expect THIN on 7 days, print verbatim; (7) footer: nothing here is a rule.

CLI: `python -m racing_edge.school.replay --sittings | --days 7 [--end] | --race rac_…` with --picks/--out/--raw/--cache/--limit-races. trial.sh: one manual verb `replay) "${SDK_OFF[@]}" "$PY" -m racing_edge.school.replay "${@:2}" ;;` — never scheduled, never in the night chain.

## 4. No-look-ahead proof — every leak, its guard

1 history rows on/after the race day — evidence.py:178-179 strict `<`. 2 trainer A/E + #1 jockey — evidence.py:211-213 skipped when as_of; the door raises. 3 trainer/jockey at course — :194-209, :220-222; doors raise. 4 distance-times — :185-187; door raises. 5 the result's rpr/performance_rating/tsr/speed — never mapped; test asserts every Runner has rpr None. 6 SP as the decision price — not eliminable; declared, confined, identical across keys. 7 position/btn/time/prize — outcome only. 8 shape-book cells from the replayed day — seed_shapebook(as_of). 9 the corpus pos column — only via guard 8. 10 the why ledger / memory / rulings — the replay never calls cli/nap.py or the model; no ai/reason import (test). 11 the live time guard (nap.py:262) — `if day == "today" and as_of is None` — passing as_of and an ISO day reads the whole past card. 12 as_of silently None — the raising doors crash the run.

The test: `test_a_history_row_dated_on_or_after_as_of_never_reaches_conviction` — a fake client returns rows dated the replayed day and the day after; build_evidence(as_of=race day) hands conviction only earlier rows; assert (i) both excluded, (ii) no PastRun.race_id equals the replayed race_id, (iii) best_class_level equals the pre-as_of value. Fails with `<` → `<=` and with the filter deleted.

## 5. Tests, REVERT-IF, live check, cost, sequence

tests/test_replay.py: 1 card_from_result maps every pre-race field (off→off_time, weight_lbs→lbs, or→ofr, claim, "Class 6"→6, pattern kept, distance_f == 12.0 from "12f", is_handicap from the name, is_all_weather from surface, odds.consensus == 4.00); 2 the adapter never carries a post-race figure; 3 an AW course keeps its suffix; 4 a runner with no SP is unpriced; 5 days_since_run reconstructed from the cache; 6 the as_of test above; 7 the current-stats doors raise and build_evidence completes without them; 8 the two keys disagree on a constructed race (the Proposal/Oolong shape: A four families no line above Cl3, B a Cl2 placing fewer families → old A, new B) — fails if _rank_key is used for both; 9 the no-flag variant moves only the improver-favourite; 10 the report math (strike, ROI, blanks excluded, head-to-head subset, race-type routing, month_test THIN/HOLDS/FAILS); 11 the replay imports no model module; 12 seed_shapebook excludes the replayed day.

REVERT-IF: none — measurement; nothing in pipeline/selection/domain/data/study changes behaviour; the only edits outside new files are one trial.sh verb and its usage line.

Live check (before the batch): `PYTHONPATH=src RACING_API_HORSE_RESULTS=standard python -m racing_edge.school.replay --race rac_32294314260` must print `door: results/{id} OK — N runners, class, pattern, dist`, `histories: N/N answered, rows before <day>, oldest <date>` — ASSERT no history row dates to uk_today() (_date falls back to today when a row lacks a date, normalise.py:181/247, and every such row would be silently dropped by `<` as_of — the failure a fake-client suite cannot see), and the `INVERSION — class first: X; the old key would have picked Y` sentence. Batch guard: abort if >20% of runners in a replayed day have zero history rows.

Cost: ~2,000 API calls on the paid plan, zero tokens (test 11 pins it), ~10 min + 1-1.5 h wall clock, evenings only.

The one-cut sequence: (1) read §0 facts off the code, do not re-audit; (2) commit 1 — the adapter + tests 1-4; (3) commit 2 — ReplayClient, seed_shapebook, tests 5-7, 12; (4) the live check; (5) commit 3 — replay_race, rank_three, _demote_improver, tests 8-9, 11; (6) commit 4 — the CSV, the report, test 10; (7) commit 5 — the trial.sh verb; (8) run --sittings, read the head-to-head first; (9) run --days 7 overnight; (10) report to the doorbell, update HANDOFF; the inversion's own REVERT-IF (15 settled picks) stays where it is.
