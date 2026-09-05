# CLASS LINE v VOLUME — one hypothesis, mechanically tested

corpus: 2727 races loaded from data/school/raw; 1509 scored (>= 2026-03-01, >= 5 priced runners, priced winner); 13958 priced runner rows
months scored: 03:661 04:33 05:206 06:68 07:90 08:451

HANDICAP v NON-HANDICAP: **not derivable** from the 13 corpus columns (no race name, no 'Hcap' flag, no official rating). rclass bands below stand in for it and are NOT the same question.

## HOW MUCH HISTORY THE CORPUS ACTUALLY HAS (read this before the rest)
| fact | value |
|---|---|
| priced runners scored | 13958 |
| n_prior = 0 (no corpus history at all) | 6697 (48%) |
| n_prior 1-2 | 5760 (41%) |
| n_prior 3+ | 1501 (11%) |
| has best_class_placed | 2666 (19%) |
| has best_class_won | 1028 (7%) |
| has best_class_run | 5317 (38%) |
| today's race unclassed (rclass 0) | 4144 (30%) |
| mean n_prior | 0.95 |

## THE CONTROL — every priced runner in the scored races, by market rank
| market rank | n | wins | win% |
|---|---|---|---|
| 1 | 1509 | 500 | 33.1% |
| 2 | 1509 | 315 | 20.9% |
| 3 | 1509 | 212 | 14.0% |
| 4 | 1509 | 171 | 11.3% |
| 5 | 1509 | 109 | 7.2% |
| 6 | 1361 | 63 | 4.6% |
| 7+ | 5052 | 140 | 2.8% |

lift pp = win% minus the win% the picks' own market ranks predict from that control (the market held constant). month(lift) is tier0.month_test verbatim (lift > 0 every month with 30+ picks, 2 months min); month(ROI) is the same shape applied to ROI. %fav = share of picks that were the favourite.

## 1-5 THE MECHANICAL SELECTIONS (one horse a race, ties to shortest SP)
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| 1 FAVOURITE (control) | 1509 | 500 | 33.1% | -13.4% | +0.0 | FAILS | FAILS | 100% |
| 2a VOLUME most prior runs | 1509 | 272 | 18.0% | -27.1% | +0.8 | FAILS | FAILS | 28% |
| 2b VOLUME most places last 3 | 1405 | 262 | 18.6% | -26.9% | -0.9 | FAILS | FAILS | 35% |
| 3a CLASS best class PLACED in | 982 | 201 | 20.5% | -16.3% | +0.7 | FAILS | FAILS | 35% |
| 3b CLASS best class WON in | 608 | 110 | 18.1% | -19.3% | -0.3 | FAILS | FAILS | 31% |
| 3c CLASS best class RUN in | 1125 | 223 | 19.8% | -15.3% | +2.6 | FAILS | FAILS | 27% |
| 4a DROP biggest class drop | 617 | 107 | 17.3% | -27.3% | +1.9 | FAILS | FAILS | 20% |
| 4b DROP dropper that won/placed LTO | 215 | 51 | 23.7% | +0.2% | +5.4 | HOLDS | FAILS | 29% |  <UNDER BAR>
| 5a UNEXPOSED fewest runs, top 3 | 1509 | 405 | 26.8% | -17.4% | -0.2 | FAILS | FAILS | 59% |
| 5b UNEXPOSED fewest runs, all | 1509 | 364 | 24.1% | -19.8% | +1.4 | FAILS | FAILS | 47% |
| 6a TOP-2 better class line | 695 | 193 | 27.8% | -15.0% | -0.7 | FAILS | FAILS | 62% |
| 6b TOP-2 more prior runs | 1509 | 434 | 28.8% | -16.8% | -0.6 | FAILS | FAILS | 69% |
| 6c TOP-3 better class line | 796 | 206 | 25.9% | -13.0% | +0.1 | FAILS | FAILS | 51% |
| 6d TOP-3 more prior runs | 1509 | 387 | 25.6% | -18.9% | -0.6 | FAILS | FAILS | 55% |

### MATCHED CONTROL — the favourite over each strategy's OWN races, and the gap
| selection | n | strike | fav strike (same races) | strike gap pp | ROI | fav ROI | ROI gap pp |
|---|---|---|---|---|---|---|---|
| 1 FAVOURITE (control) | 1509 | 33.1% | 33.1% | +0.0 | -13.4% | -13.4% | +0.0 |
| 2a VOLUME most prior runs | 1509 | 18.0% | 33.1% | -15.1 | -27.1% | -13.4% | -13.7 |
| 2b VOLUME most places last 3 | 1405 | 18.6% | 32.5% | -13.9 | -26.9% | -13.3% | -13.6 |
| 3a CLASS best class PLACED in | 982 | 20.5% | 32.9% | -12.4 | -16.3% | -11.1% | -5.2 |
| 3b CLASS best class WON in | 608 | 18.1% | 29.9% | -11.8 | -19.3% | -16.0% | -3.4 |
| 3c CLASS best class RUN in | 1125 | 19.8% | 33.2% | -13.4 | -15.3% | -11.1% | -4.1 |
| 4a DROP biggest class drop | 617 | 17.3% | 31.8% | -14.4 | -27.3% | -12.5% | -14.8 |
| 4b DROP dropper that won/placed LTO | 215 | 23.7% | 34.9% | -11.2 | +0.2% | +0.2% | +0.1 |  <UNDER BAR>
| 5a UNEXPOSED fewest runs, top 3 | 1509 | 26.8% | 33.1% | -6.3 | -17.4% | -13.4% | -4.0 |
| 5b UNEXPOSED fewest runs, all | 1509 | 24.1% | 33.1% | -9.0 | -19.8% | -13.4% | -6.4 |
| 6a TOP-2 better class line | 695 | 27.8% | 33.4% | -5.6 | -15.0% | -9.6% | -5.4 |
| 6b TOP-2 more prior runs | 1509 | 28.8% | 33.1% | -4.4 | -16.8% | -13.4% | -3.4 |
| 6c TOP-3 better class line | 796 | 25.9% | 33.5% | -7.7 | -13.0% | -9.4% | -3.6 |
| 6d TOP-3 more prior runs | 1509 | 25.6% | 33.1% | -7.5 | -18.9% | -13.4% | -5.5 |

### the same selections with NO TIEBREAK (races where the criterion had exactly one holder)
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| 1 FAVOURITE (control) | 1509 | 500 | 33.1% | -13.4% | +0.0 | FAILS | FAILS | 100% |
| 2a VOLUME most prior runs | 800 | 103 | 12.9% | -32.9% | -0.3 | FAILS | FAILS | 14% |
| 2b VOLUME most places last 3 | 770 | 121 | 15.7% | -32.5% | -0.4 | FAILS | FAILS | 23% |
| 3a CLASS best class PLACED in | 576 | 102 | 17.7% | -16.5% | +1.5 | FAILS | FAILS | 22% |
| 3b CLASS best class WON in | 436 | 68 | 15.6% | -26.2% | -1.3 | FAILS | FAILS | 26% |  <UNDER BAR>
| 3c CLASS best class RUN in | 621 | 101 | 16.3% | -12.7% | +3.3 | FAILS | FAILS | 14% |
| 4a DROP biggest class drop | 399 | 62 | 15.5% | -29.5% | +2.4 | FAILS | FAILS | 14% |  <UNDER BAR>
| 4b DROP dropper that won/placed LTO | 190 | 41 | 21.6% | -11.0% | +3.8 | FAILS | FAILS | 27% |  <UNDER BAR>
| 5a UNEXPOSED fewest runs, top 3 | 656 | 133 | 20.3% | -22.2% | -2.1 | FAILS | FAILS | 32% |
| 5b UNEXPOSED fewest runs, all | 169 | 22 | 13.0% | -27.1% | +0.9 | THIN | THIN | 14% |  <UNDER BAR>
| 6a TOP-2 better class line | 560 | 143 | 25.5% | -18.3% | -1.9 | FAILS | FAILS | 53% |
| 6b TOP-2 more prior runs | 915 | 230 | 25.1% | -18.1% | -1.8 | FAILS | FAILS | 50% |
| 6c TOP-3 better class line | 564 | 128 | 22.7% | -17.8% | -1.1 | FAILS | FAILS | 38% |
| 6d TOP-3 more prior runs | 916 | 190 | 20.7% | -24.6% | -2.1 | FAILS | FAILS | 34% |

## 6 HEAD TO HEAD — class line v volume, inside the market's first k
(only races where the two measures name DIFFERENT horses)
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| 6 top-2: better CLASS line | 141 | 37 | 26.2% | -18.4% | -1.2 | THIN | THIN | 54% |  <UNDER BAR>
| 6 top-2: more PRIOR RUNS | 141 | 37 | 26.2% | -12.3% | -0.3 | THIN | THIN | 46% |  <UNDER BAR>
| 6 top-2: neither won | 67 | - | - | - | - | - | - | - |
| 6 top-3: better CLASS line | 270 | 63 | 23.3% | -17.8% | -1.8 | FAILS | FAILS | 47% |  <UNDER BAR>
| 6 top-3: more PRIOR RUNS | 270 | 59 | 21.9% | -19.3% | -0.7 | FAILS | FAILS | 34% |  <UNDER BAR>
| 6 top-3: neither won | 148 | - | - | - | - | - | - | - |

## 7 STORY v LINE — sp_rank 2-3, class line better than the favourite's
(a runner population, not one a race: stake one unit on every qualifier)
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| 7a beats fav on best class PLACED | 83 | 18 | 21.7% | +2.9% | +3.9 | THIN | THIN | 0% |  <UNDER BAR>
| 7b beats fav on best class WON | 7 | 2 | 28.6% | +50.0% | +10.6 | THIN | THIN | 0% |  <UNDER BAR>
| 7c beats fav on best class RUN | 228 | 47 | 20.6% | -10.9% | +3.1 | HOLDS | FAILS | 0% |  <UNDER BAR>

## STRATA — code / class band / field size (each strategy split)

### 1 FAVOURITE (control) — sp_rank 1
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 950 | 322 | 33.9% | -11.3% | +0.8 | FAILS | FAILS | 100% |
| JUMPS | 559 | 178 | 31.8% | -16.9% | -1.3 | FAILS | FAILS | 100% |
| cls1-3 | 219 | 82 | 37.4% | +1.4% | +4.3 | HOLDS | FAILS | 100% |  <UNDER BAR>
| cls4-5 | 701 | 244 | 34.8% | -13.2% | +1.7 | FAILS | FAILS | 100% |
| cls6-7 | 232 | 69 | 29.7% | -13.8% | -3.4 | FAILS | FAILS | 100% |  <UNDER BAR>
| unclassed | 357 | 105 | 29.4% | -22.6% | -3.7 | FAILS | FAILS | 100% |  <UNDER BAR>
| fld5-7 | 543 | 218 | 40.1% | -6.5% | +7.0 | HOLDS | FAILS | 100% |
| fld8-11 | 631 | 206 | 32.6% | -10.9% | -0.5 | FAILS | FAILS | 100% |
| fld12+ | 335 | 76 | 22.7% | -29.2% | -10.4 | FAILS | FAILS | 100% |  <UNDER BAR>

### 2a VOLUME most prior runs — max n_prior (exposure)
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 950 | 181 | 19.1% | -21.8% | +2.3 | FAILS | FAILS | 26% |
| JUMPS | 559 | 91 | 16.3% | -36.3% | -1.8 | FAILS | FAILS | 30% |
| cls1-3 | 219 | 38 | 17.4% | -31.0% | +0.7 | FAILS | FAILS | 28% |  <UNDER BAR>
| cls4-5 | 701 | 144 | 20.5% | -19.5% | +2.2 | FAILS | FAILS | 30% |
| cls6-7 | 232 | 35 | 15.1% | -42.4% | -1.3 | FAILS | FAILS | 22% |  <UNDER BAR>
| unclassed | 357 | 55 | 15.4% | -29.8% | -0.7 | FAILS | FAILS | 27% |  <UNDER BAR>
| fld5-7 | 543 | 133 | 24.5% | -17.9% | +3.8 | FAILS | FAILS | 37% |
| fld8-11 | 631 | 104 | 16.5% | -28.3% | -0.2 | FAILS | FAILS | 25% |
| fld12+ | 335 | 35 | 10.4% | -39.9% | -2.3 | FAILS | FAILS | 16% |  <UNDER BAR>

### 2b VOLUME most places last 3 — max places_l3
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 858 | 149 | 17.4% | -28.5% | -0.5 | FAILS | FAILS | 29% |
| JUMPS | 547 | 113 | 20.7% | -24.4% | -1.6 | FAILS | FAILS | 42% |
| cls1-3 | 194 | 27 | 13.9% | -38.1% | -1.9 | FAILS | FAILS | 23% |  <UNDER BAR>
| cls4-5 | 646 | 140 | 21.7% | -14.1% | +1.1 | FAILS | FAILS | 37% |
| cls6-7 | 232 | 46 | 19.8% | -35.3% | -0.7 | FAILS | FAILS | 38% |  <UNDER BAR>
| unclassed | 333 | 49 | 14.7% | -39.3% | -4.5 | FAILS | FAILS | 35% |  <UNDER BAR>
| fld5-7 | 482 | 119 | 24.7% | -19.7% | +2.8 | HOLDS | FAILS | 41% |  <UNDER BAR>
| fld8-11 | 598 | 100 | 16.7% | -29.8% | -2.7 | FAILS | FAILS | 33% |
| fld12+ | 325 | 43 | 13.2% | -32.3% | -3.4 | FAILS | FAILS | 29% |  <UNDER BAR>

### 3a CLASS best class PLACED in — min best_class_placed
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 650 | 125 | 19.2% | -15.8% | +0.2 | FAILS | FAILS | 33% |
| JUMPS | 332 | 76 | 22.9% | -17.2% | +1.6 | FAILS | FAILS | 39% |  <UNDER BAR>
| cls1-3 | 165 | 28 | 17.0% | -6.3% | +0.7 | FAILS | FAILS | 27% |  <UNDER BAR>
| cls4-5 | 567 | 120 | 21.2% | -16.6% | +0.8 | FAILS | FAILS | 35% |
| cls6-7 | 220 | 50 | 22.7% | -15.6% | +0.7 | HOLDS | FAILS | 44% |  <UNDER BAR>
| unclassed | 30 | 3 | 10.0% | -70.9% | -1.2 | THIN | THIN | 17% |  <UNDER BAR>
| fld5-7 | 365 | 101 | 27.7% | -3.6% | +5.4 | FAILS | FAILS | 40% |  <UNDER BAR>
| fld8-11 | 458 | 77 | 16.8% | -27.1% | -2.1 | FAILS | FAILS | 32% |  <UNDER BAR>
| fld12+ | 159 | 23 | 14.5% | -14.4% | -1.9 | FAILS | FAILS | 30% |  <UNDER BAR>

### 3b CLASS best class WON in — min best_class_won
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 432 | 76 | 17.6% | -16.3% | +0.2 | FAILS | FAILS | 29% |  <UNDER BAR>
| JUMPS | 176 | 34 | 19.3% | -26.8% | -1.5 | THIN | THIN | 35% |  <UNDER BAR>
| cls1-3 | 116 | 17 | 14.7% | +2.3% | -0.0 | FAILS | FAILS | 21% |  <UNDER BAR>
| cls4-5 | 337 | 56 | 16.6% | -31.3% | -2.5 | FAILS | FAILS | 32% |  <UNDER BAR>
| cls6-7 | 146 | 36 | 24.7% | -5.6% | +4.7 | FAILS | FAILS | 36% |  <UNDER BAR>
| unclassed | 9 | 1 | 11.1% | -72.2% | -2.9 | THIN | THIN | 22% |  <UNDER BAR>
| fld5-7 | 199 | 46 | 23.1% | -27.9% | +2.0 | HOLDS | FAILS | 38% |  <UNDER BAR>
| fld8-11 | 305 | 50 | 16.4% | -9.0% | -1.2 | FAILS | FAILS | 28% |  <UNDER BAR>
| fld12+ | 104 | 14 | 13.5% | -33.1% | -2.1 | THIN | THIN | 25% |  <UNDER BAR>

### 3c CLASS best class RUN in — min best_class_run
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 741 | 144 | 19.4% | -13.2% | +3.1 | FAILS | FAILS | 24% |
| JUMPS | 384 | 79 | 20.6% | -19.3% | +1.8 | FAILS | FAILS | 32% |  <UNDER BAR>
| cls1-3 | 188 | 35 | 18.6% | -2.8% | +2.8 | FAILS | FAILS | 23% |  <UNDER BAR>
| cls4-5 | 642 | 137 | 21.3% | -13.8% | +3.3 | FAILS | FAILS | 28% |
| cls6-7 | 232 | 43 | 18.5% | -30.8% | +0.9 | FAILS | FAILS | 30% |  <UNDER BAR>
| unclassed | 63 | 8 | 12.7% | -10.3% | +1.5 | THIN | THIN | 13% |  <UNDER BAR>
| fld5-7 | 427 | 125 | 29.3% | +14.0% | +9.1 | FAILS | FAILS | 34% |  <UNDER BAR>
| fld8-11 | 511 | 81 | 15.9% | -27.6% | -0.3 | FAILS | FAILS | 24% |
| fld12+ | 187 | 17 | 9.1% | -48.2% | -4.1 | FAILS | FAILS | 19% |  <UNDER BAR>

### 4a DROP biggest class drop — max class_drop (>0 only)
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 412 | 66 | 16.0% | -31.7% | +1.3 | FAILS | FAILS | 18% |  <UNDER BAR>
| JUMPS | 205 | 41 | 20.0% | -18.4% | +3.0 | THIN | THIN | 23% |  <UNDER BAR>
| cls1-3 | 69 | 15 | 21.7% | -17.3% | +5.9 | THIN | THIN | 22% |  <UNDER BAR>
| cls4-5 | 386 | 70 | 18.1% | -20.3% | +2.0 | HOLDS | FAILS | 22% |  <UNDER BAR>
| cls6-7 | 162 | 22 | 13.6% | -48.1% | -0.1 | FAILS | FAILS | 15% |  <UNDER BAR>
| fld5-7 | 225 | 63 | 28.0% | +9.6% | +10.1 | HOLDS | HOLDS | 25% |  <UNDER BAR>
| fld8-11 | 295 | 32 | 10.8% | -51.8% | -3.2 | FAILS | FAILS | 16% |  <UNDER BAR>
| fld12+ | 97 | 12 | 12.4% | -38.5% | -1.5 | THIN | THIN | 19% |  <UNDER BAR>

### 4b DROP dropper that won/placed LTO — max class_drop, last_placed
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 153 | 35 | 22.9% | -1.3% | +4.6 | FAILS | FAILS | 29% |  <UNDER BAR>
| JUMPS | 62 | 16 | 25.8% | +3.9% | +7.2 | THIN | THIN | 29% |  <UNDER BAR>
| cls1-3 | 28 | 7 | 25.0% | -12.5% | +8.3 | THIN | THIN | 29% |  <UNDER BAR>
| cls4-5 | 133 | 33 | 24.8% | +4.4% | +6.0 | HOLDS | FAILS | 29% |  <UNDER BAR>
| cls6-7 | 54 | 11 | 20.4% | -3.4% | +2.2 | THIN | THIN | 28% |  <UNDER BAR>
| fld5-7 | 71 | 27 | 38.0% | +57.3% | +17.0 | THIN | THIN | 37% |  <UNDER BAR>
| fld8-11 | 104 | 17 | 16.3% | -38.3% | -0.6 | FAILS | FAILS | 23% |  <UNDER BAR>
| fld12+ | 40 | 7 | 17.5% | -0.8% | +0.2 | THIN | THIN | 30% |  <UNDER BAR>

### 5a UNEXPOSED fewest runs, top 3 — min n_prior within sp_rank<=3
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 950 | 265 | 27.9% | -16.2% | +0.3 | FAILS | FAILS | 62% |
| JUMPS | 559 | 140 | 25.0% | -19.3% | -1.1 | FAILS | FAILS | 53% |
| cls1-3 | 219 | 69 | 31.5% | -5.3% | +2.7 | FAILS | FAILS | 68% |  <UNDER BAR>
| cls4-5 | 701 | 189 | 27.0% | -21.5% | +0.2 | FAILS | FAILS | 58% |
| cls6-7 | 232 | 47 | 20.3% | -22.8% | -4.3 | FAILS | FAILS | 44% |  <UNDER BAR>
| unclassed | 357 | 100 | 28.0% | -13.2% | -0.0 | FAILS | FAILS | 66% |  <UNDER BAR>
| fld5-7 | 543 | 165 | 30.4% | -17.0% | +3.5 | FAILS | FAILS | 58% |
| fld8-11 | 631 | 161 | 25.5% | -20.5% | -1.4 | FAILS | FAILS | 58% |
| fld12+ | 335 | 79 | 23.6% | -12.2% | -4.1 | FAILS | FAILS | 63% |  <UNDER BAR>

### 5b UNEXPOSED fewest runs, all — min n_prior, whole field
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 950 | 247 | 26.0% | -16.0% | +2.4 | FAILS | FAILS | 52% |
| JUMPS | 559 | 117 | 20.9% | -26.3% | -0.3 | FAILS | FAILS | 38% |
| cls1-3 | 219 | 63 | 28.8% | -12.2% | +2.3 | HOLDS | FAILS | 62% |  <UNDER BAR>
| cls4-5 | 701 | 172 | 24.5% | -19.7% | +2.0 | FAILS | FAILS | 46% |
| cls6-7 | 232 | 34 | 14.7% | -35.8% | -2.8 | FAILS | FAILS | 25% |  <UNDER BAR>
| unclassed | 357 | 95 | 26.6% | -14.5% | +2.5 | FAILS | FAILS | 54% |  <UNDER BAR>
| fld5-7 | 543 | 149 | 27.4% | -15.7% | +3.8 | HOLDS | FAILS | 48% |
| fld8-11 | 631 | 147 | 23.3% | -21.7% | +1.2 | FAILS | FAILS | 45% |
| fld12+ | 335 | 68 | 20.3% | -23.0% | -2.1 | FAILS | FAILS | 47% |  <UNDER BAR>

### 6a TOP-2 better class line — min best_class_placed within sp_rank<=2
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 438 | 119 | 27.2% | -16.4% | -1.3 | FAILS | FAILS | 62% |  <UNDER BAR>
| JUMPS | 257 | 74 | 28.8% | -12.6% | +0.2 | FAILS | FAILS | 63% |  <UNDER BAR>
| cls1-3 | 93 | 27 | 29.0% | +1.0% | +0.5 | THIN | THIN | 62% |  <UNDER BAR>
| cls4-5 | 426 | 112 | 26.3% | -21.4% | -2.0 | FAILS | FAILS | 60% |  <UNDER BAR>
| cls6-7 | 167 | 51 | 30.5% | -8.4% | +1.3 | HOLDS | FAILS | 68% |  <UNDER BAR>
| unclassed | 9 | 3 | 33.3% | -3.0% | +5.6 | THIN | THIN | 56% |  <UNDER BAR>
| fld5-7 | 269 | 93 | 34.6% | -1.3% | +6.0 | HOLDS | HOLDS | 62% |  <UNDER BAR>
| fld8-11 | 333 | 80 | 24.0% | -22.8% | -4.3 | FAILS | FAILS | 61% |  <UNDER BAR>
| fld12+ | 93 | 20 | 21.5% | -26.6% | -7.7 | THIN | THIN | 68% |  <UNDER BAR>

### 6b TOP-2 more prior runs — max n_prior within sp_rank<=2
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 950 | 279 | 29.4% | -16.9% | -0.1 | FAILS | FAILS | 70% |
| JUMPS | 559 | 155 | 27.7% | -16.7% | -1.6 | FAILS | FAILS | 69% |
| cls1-3 | 219 | 73 | 33.3% | -6.2% | +2.9 | FAILS | FAILS | 78% |  <UNDER BAR>
| cls4-5 | 701 | 210 | 30.0% | -16.2% | +0.3 | FAILS | FAILS | 71% |
| cls6-7 | 232 | 66 | 28.4% | -10.4% | +0.3 | FAILS | FAILS | 59% |  <UNDER BAR>
| unclassed | 357 | 85 | 23.8% | -28.9% | -5.2 | FAILS | FAILS | 66% |  <UNDER BAR>
| fld5-7 | 543 | 193 | 35.5% | -7.5% | +5.9 | FAILS | FAILS | 72% |
| fld8-11 | 631 | 172 | 27.3% | -20.5% | -2.0 | FAILS | FAILS | 68% |
| fld12+ | 335 | 69 | 20.6% | -24.9% | -8.6 | FAILS | FAILS | 68% |  <UNDER BAR>

### 6c TOP-3 better class line — min best_class_placed within sp_rank<=3
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 504 | 125 | 24.8% | -16.7% | -0.8 | FAILS | FAILS | 50% |
| JUMPS | 292 | 81 | 27.7% | -6.7% | +1.6 | FAILS | FAILS | 52% |  <UNDER BAR>
| cls1-3 | 117 | 31 | 26.5% | +6.5% | +2.1 | HOLDS | HOLDS | 44% |  <UNDER BAR>
| cls4-5 | 482 | 120 | 24.9% | -18.1% | -0.8 | FAILS | FAILS | 49% |  <UNDER BAR>
| cls6-7 | 187 | 52 | 27.8% | -12.0% | +0.9 | HOLDS | FAILS | 58% |  <UNDER BAR>
| unclassed | 10 | 3 | 30.0% | -12.7% | +3.7 | THIN | THIN | 50% |  <UNDER BAR>
| fld5-7 | 311 | 98 | 31.5% | -3.2% | +5.6 | HOLDS | FAILS | 51% |  <UNDER BAR>
| fld8-11 | 378 | 83 | 22.0% | -23.9% | -3.5 | FAILS | FAILS | 48% |  <UNDER BAR>
| fld12+ | 107 | 25 | 23.4% | -3.0% | -3.1 | THIN | THIN | 56% |  <UNDER BAR>

### 6d TOP-3 more prior runs — max n_prior within sp_rank<=3
| selection | n | w | strike | ROI@SP | lift pp | month(lift) | month(ROI) | %fav |
|---|---|---|---|---|---|---|---|---|
| FLAT | 950 | 254 | 26.7% | -16.5% | +0.5 | FAILS | FAILS | 55% |
| JUMPS | 559 | 133 | 23.8% | -22.8% | -2.5 | FAILS | FAILS | 55% |
| cls1-3 | 219 | 67 | 30.6% | -0.8% | +3.6 | HOLDS | FAILS | 61% |  <UNDER BAR>
| cls4-5 | 701 | 184 | 26.2% | -21.4% | -0.4 | FAILS | FAILS | 57% |
| cls6-7 | 232 | 59 | 25.4% | -13.5% | +0.9 | FAILS | FAILS | 44% |  <UNDER BAR>
| unclassed | 357 | 77 | 21.6% | -28.6% | -4.5 | FAILS | FAILS | 53% |  <UNDER BAR>
| fld5-7 | 543 | 173 | 31.9% | -10.6% | +5.1 | HOLDS | FAILS | 58% |
| fld8-11 | 631 | 151 | 23.9% | -24.7% | -1.9 | FAILS | FAILS | 53% |
| fld12+ | 335 | 63 | 18.8% | -21.5% | -7.3 | FAILS | FAILS | 53% |  <UNDER BAR>

MIN_REPORT_N = 500 (mine.py). Anything marked <UNDER BAR> recommends nothing.
