# UNRECEIPTED — every rule in the engine's live pick path with no birth receipt

75 of 200 register rows. One line each: file:line — rule_id — label. Grouped by kind. Keep or retire.

## aligned (2)

- `src/racing_edge/selection/conviction.py:366` — **aligned:proven-course-winner** — proven course winner (depth)  [the depth idea traces to the Kingofthegame/Caughtinyourtrance tells (28/26 Jun)]
- `src/racing_edge/selection/conviction.py:368` — **aligned:course-winner** — course winner

## caution (3)

- `src/racing_edge/selection/conviction.py:345` — **caution:cold-form** — cold form ({p}-{p} last two)  [demoted flag->caution 2026-08-27]
- `src/racing_edge/selection/conviction.py:466` — **caution:rising-mark-trap** — rising-mark trap  [born of ONE incident (Halfway House Lad, 28 Jun); demoted flag->caution 2026-08-27]
- `src/racing_edge/domain/tells.py:61` — **caution:tells:hat_trick_trap** — TELL — won its last two off a rising mark... distrust as a banker  [this is the tell behind caution:rising-mark-trap]

## constant (16)

- `src/racing_edge/selection/conviction.py:34` — **constant:conviction:NO_CLASS_LINE** — 99  [sentinel; the ladder itself is taught, this ordering is not]
- `src/racing_edge/domain/manner.py:59` — **constant:manner:_GREEN** — the green / unfurnished phrase list  [classifier only]
- `src/racing_edge/pipeline/nap.py:219` — **constant:_rank_key:unclassed_ranks_7** — -(p.race.race_class if p.race.race_class else 7)
- `src/racing_edge/pipeline/nap.py:395` — **constant:evaluate_field:dead_wood_labels** — "cold form" | "no win in" | "STALE"
- `src/racing_edge/school/signposts.py:24` — **constant:signposts:COMBO_MIN_RIDES** — COMBO_MIN_RIDES = 5  [dots only — 'Nothing here moves the engine's score' (signposts.py:15); they reach the reader's sheet and the yardstick ledger]
- `src/racing_edge/school/signposts.py:25` — **constant:signposts:COURSE_TYPE_MIN_RUNS** — COURSE_TYPE_MIN_RUNS = 5  [dots only — 'Nothing here moves the engine's score' (signposts.py:15); they reach the reader's sheet and the yardstick ledger]
- `src/racing_edge/school/signposts.py:27` — **constant:signposts:FRESH_DAYS** — FRESH_DAYS = 180  [dots only — 'Nothing here moves the engine's score' (signposts.py:15); they reach the reader's sheet and the yardstick ledger]
- `src/racing_edge/school/signposts.py:28` — **constant:signposts:COLD_YARD_DAYS** — COLD_YARD_DAYS = 45  [dots only — 'Nothing here moves the engine's score' (signposts.py:15); they reach the reader's sheet and the yardstick ledger]
- `src/racing_edge/school/signposts.py:29` — **constant:signposts:LAST_YEAR_WINDOW** — LAST_YEAR_WINDOW = 7  [dots only — 'Nothing here moves the engine's score' (signposts.py:15); they reach the reader's sheet and the yardstick ledger]
- `src/racing_edge/school/signposts.py:182` — **constant:signposts:MATCH_MIN** — MATCH_MIN = 0.45  [dots only — 'Nothing here moves the engine's score' (signposts.py:15); they reach the reader's sheet and the yardstick ledger]
- `src/racing_edge/school/signposts.py:138` — **constant:signposts:chain_fetch_bounds** — CHAIN_FETCH_MAX = 24, CHAIN_HISTORY_LIMIT = 40  [cost bound, not a betting rule]
- `src/racing_edge/school/shapebook.py:56` — **constant:shapebook:field_bands** — 2-7 / 8-11 / 12-15 / 16+
- `src/racing_edge/school/shapebook.py:66` — **constant:shapebook:fav_bands** — fav<6/4 (<2.5) / fav 6/4-3/1 (<=4.0) / fav>3/1
- `src/racing_edge/school/bar_backtest.py:55` — **constant:bar_backtest:MIN_CELL_N** — MIN_CELL_N = 30
- `src/racing_edge/school/tier0.py:35` — **constant:tier0:MONTH_MIN_N** — MONTH_MIN_N = 30  [the MONTH TEST it serves is taught (rulings.csv:16); the number 30 is not]
- `src/racing_edge/cli/nap.py:374` — **constant:cli:VOID_AFTER_DAYS** — VOID_AFTER_DAYS = 7

## flag (1)

- `src/racing_edge/selection/conviction.py:472` — **flag:all-weather-caution** — all-weather caution (#14)  [CONTRADICTION: the rulebook says '#14 THE ALL-WEATHER CAUTION... a caution, never a cross' (morningread.py:448-450); the code appends it to FLAGS, which disqualify]

## gate (1)

- `src/racing_edge/pipeline/nap.py:385` — **gate:evaluate_field:race_flags_ride_every_runner** — every pick in the race inherits race_flags into conviction.flags  [structural: this is how one race-level caution erases a whole card]

## term (5)

- `src/racing_edge/domain/manner.py:93` — **term:manner:priority_order** — finisher > trouble > non_finisher > green  [decides which of two phrases in one comment wins]
- `src/racing_edge/pipeline/nap.py:215` — **term:_rank_key:confident_first** — int(p.conviction.confident)
- `src/racing_edge/pipeline/nap.py:215` — **term:_rank_key:mark_known** — int(p.conviction.mark_known)
- `src/racing_edge/pipeline/nap.py:216` — **term:_rank_key:len_aligned_tiebreak** — len(p.conviction.aligned)  [his ruling on this tie was asked for (EDGE_LEDGER.md:872) and never given]
- `src/racing_edge/pipeline/nap.py:219` — **term:_rank_key:shorter_price_breaks_final_tie** — -(p.price or 999.0)  [last term only, but it is the market picking]

## threshold (47)

- `src/racing_edge/selection/conviction.py:259` — **threshold:conviction:quick_return_days<60** — runner.days_since_run < 60  [the same 60 is reused at conviction.py:402 and 406]
- `src/racing_edge/selection/conviction.py:315` — **threshold:conviction:placer_risk_runs>=6** — len(hist) >= 6 and no win
- `src/racing_edge/selection/conviction.py:341` — **threshold:conviction:cold_form_last_two>=6** — all(p >= 6 for p in recent[:2])
- `src/racing_edge/selection/conviction.py:383` — **threshold:conviction:fair_fav_price>=2.5** — market_rank == 1 and price >= 2.5  [a 2.4 favourite scores nothing, a 2.5 favourite scores a dot]
- `src/racing_edge/selection/conviction.py:402` — **threshold:conviction:solid_hole_days>=60** — runner.days_since_run >= 60 and not dominant
- `src/racing_edge/selection/conviction.py:425` — **threshold:conviction:stable_strike>=0.15** — stable_strike >= 0.15
- `src/racing_edge/pipeline/nap.py:326` — **threshold:pipeline:stable_runs>=8** — ev.stable_runs >= 8 before a strike is computed
- `src/racing_edge/selection/conviction.py:430` — **threshold:conviction:local_strike>=0.18** — local_strike >= 0.18
- `src/racing_edge/selection/conviction.py:444` — **threshold:conviction:trip_strike>=0.25_runs>=4** — trip_runs >= 4 and trip_strike >= 0.25
- `src/racing_edge/selection/conviction.py:452` — **threshold:conviction:jockey_zero_rides>=25** — jockey_course_strike == 0.0 and jockey_course_rides >= 25
- `src/racing_edge/selection/conviction.py:469` — **threshold:conviction:improver_fav_cuts** — len(history) <= 4 and market_rank == 1 and price <= 3.0
- `src/racing_edge/selection/conviction.py:473` — **threshold:conviction:big_field>=16** — field_size >= 16
- `src/racing_edge/selection/conviction.py:324` — **threshold:conviction:manner_window_4** — nap_verdict over hist[:4] comments
- `src/racing_edge/selection/conviction.py:336` — **threshold:conviction:momentum_window_3** — recent = positions of hist[:3]
- `src/racing_edge/domain/manner.py:140` — **threshold:manner:win_positive** — recent == "finisher" or (fin >= 1 and fin > nonf)
- `src/racing_edge/domain/manner.py:143` — **threshold:manner:excuse_upgrade** — recent == "trouble" or (trouble and trouble >= nonf)
- `src/racing_edge/domain/tells.py:66` — **threshold:tells:hat_trick_price<=3.0** — price <= 3.0
- `src/racing_edge/domain/tells.py:86` — **threshold:tells:headgear_yard_4runs_15pct** — runs >= 4 and (wins / runs) >= 0.15
- `src/racing_edge/domain/tells.py:38` — **threshold:tells:_same_trip_1f** — abs(h.distance_f - race.distance_f) <= 1.0
- `src/racing_edge/domain/profile.py:40` — **threshold:profile:well_in_and_proven** — weight 5.0 when wv <= -2 and won at the level; else 3.0  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:53` — **threshold:profile:class_drop** — weight 4.0 — won at a higher grade than today  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:65` — **threshold:profile:class_ceiling** — weight -4.0 VETO — 3+ runs at the level, no win  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:77` — **threshold:profile:topped_out** — weight -4.0 — only won below today's class  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:86` — **threshold:profile:going_proven** — weight 4.0 won on the band / -4.0 on 4+ unplaced  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:101` — **threshold:profile:trip_proven** — weight 3.0, tol_f = 1.5 furlongs  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:111` — **threshold:profile:course_proven** — weight 2.0 — a winner at the track  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:119` — **threshold:profile:consistency_prb** — PRB >= 0.55 = 2.0, <= 0.45 = -2.0, min 4 runs  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:142` — **threshold:profile:quality_of_win** — weight 2.0 — won Class <= 4 with field >= 8  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:157` — **threshold:profile:claimer_allowance** — claim >= 3lb: 2.5 if >= 5lb else 1.5  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:169` — **threshold:profile:weight_relief** — weight 2.0 when wv <= -3  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/domain/profile.py:180` — **threshold:profile:well_handicapped** — weight 3.0 when RPR - OR >= 7  [DEAD CODE — selection/case.py assess() has no caller in the pick path (only RunnerEvidence is imported); nothing here reaches a pick]
- `src/racing_edge/pipeline/nap.py:140` — **threshold:ew_advice:price>=8.0_thin_terms** — price >= 8.0
- `src/racing_edge/pipeline/nap.py:154` — **threshold:market_shape:bands_0.62_0.52** — anchored >= 0.62 | loose >= 0.52 | else OPEN  [the rulebook's #22 ANCHOR BAR states a PRICE cliff instead — 'a favourite 6/1 or bigger (5/1 below Class 3)' (morningread.py:451-453) — which the code does not implement]
- `src/racing_edge/pipeline/nap.py:158` — **threshold:still_to_run:buffer_5_minutes** — buffer_minutes: int = 5
- `src/racing_edge/pipeline/nap.py:321` — **threshold:evaluate_field:young_unexposed_runner** — i < 6 and (r.age or 99) <= 6 and len(hist) <= 5
- `src/racing_edge/pipeline/nap.py:352` — **threshold:race_gate:young_unexposed>=2_and_half** — young_unexposed >= 2 and young_unexposed * 2 >= contenders
- `src/racing_edge/pipeline/nap.py:371` — **threshold:race_gate:candy_in_form_proxy** — p.history[0].position == 1 (won last time out)  [self-declared proxy; the <=7 field cut is likewise unreceipted]
- `src/racing_edge/pipeline/nap.py:416` — **threshold:evaluate_field:hollow_half_the_field** — hollow = _dead * 2 > len(race_picks)
- `src/racing_edge/school/signposts.py:40` — **threshold:signposts:combo_bands_33_20** — combo 33%+ / combo 20%+ / combo cold  [dots only — 'Nothing here moves the engine's score' (signposts.py:15); they reach the reader's sheet and the yardstick ledger]
- `src/racing_edge/school/signposts.py:107` — **threshold:signposts:yard_here_25_or_cold_8** — yard here 25%+ / cold under 8%  [dots only — 'Nothing here moves the engine's score' (signposts.py:15); they reach the reader's sheet and the yardstick ledger]
- `src/racing_edge/school/signposts.py:296` — **threshold:signposts:dna_fit_needs_3_runnings** — len(lbs) < 3 -> no DNA weight line  [dots only — 'Nothing here moves the engine's score' (signposts.py:15); they reach the reader's sheet and the yardstick ledger]
- `src/racing_edge/school/shapebook.py:113` — **threshold:shapebook:GET_ON_THE_JOLLY** — fav >= 45 and top3 >= 85  [CONTRADICTION with its own docstring ('thresholds present the data, they are not betting rules') — race_quality_score now scores this verdict +1 (nap.py:117-119)]
- `src/racing_edge/school/shapebook.py:116` — **threshold:shapebook:GEM_BEHIND_THE_JOLLY** — top3 >= 78 and fav < 40  [scored +1 in race_quality_score (nap.py:117-119)]
- `src/racing_edge/school/shapebook.py:118` — **threshold:shapebook:BEST_AVOIDED** — top3 < 65  [scored -2 in race_quality_score and it declines leans outright (shapebook.py:222-227)]
- `src/racing_edge/school/shapebook.py:75` — **threshold:shapebook:cell_floor_min_n** — min_n = 30
- `src/racing_edge/school/shapebook.py:228` — **threshold:shapebook:glance_decline_top3>=78_rank>3** — glance["top3"] >= 78 and nap_market_rank > 3
- `src/racing_edge/cli/nap.py:1440` — **threshold:cli:argued_needs_3_cites** — len(mp.cite) >= 3  [still 3 after the finding]
