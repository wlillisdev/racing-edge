"""
scoring_healthcheck.py — empirical audit of the NAP scoring engine on REAL data.

Why this exists
---------------
The suitability bug (the biggest scoring factor silently scoring 0 for every
horse, because the code read fields — 'position', 'distance_f' — that don't exist
in the real full_form data) was invisible to code review and to synthetic tests
written to match the code's own assumptions. The only way to catch that class of
bug is to run the real scorer on real data and watch the outputs.

What it does
------------
Runs the live `score_runner` over a real day's card and reports, per scoring
component, the distribution of its contribution across all runners. A silently
dead/degraded component (Suit=0 across ~100% of runners — the exact bug
signature) is flagged RED. It also:
  - checks each external data source (full_form, trainer_profiles, market_movers,
    form_read, race_shape) for presence and coverage;
  - verifies the data contracts the suitability bug violated (can the nested
    finishing position be read? does the past-race distance parse?);
  - reports the total-score distribution against the confidence thresholds, so a
    scale/threshold mismatch is visible.

Run it where the daily pipeline wrote its files:
    python scoring_healthcheck.py [YYYY-MM-DD]

Exit code 1 if any critical component is dead/degraded or a critical source is
missing — so it can also run as a pipeline guard that alerts on regressions.
"""

from __future__ import annotations

import statistics
import sys

from racecard_loader import load_racecard
from src.helpers import data_path, log, safe_load_json, today_str
from nap_selector_v3 import (
    score_runner, _horse_position, compute_suitability_score, get_params,
)

# Components that SHOULD contribute for most runners. ~all-zero ⇒ broken.
CRITICAL = ["form_score", "suitability_score", "context_score", "trainer_score"]
# Legitimately zero for many runners (draw only on flat sprints; market is
# penalties-only) — reported, never flagged on zero alone.
INFO_ONLY = ["draw_score", "market_score"]
DEAD_ZERO_PCT = 80.0   # critical component zero for >= this % ⇒ SUSPECT


def _pct(n, d):
    return 100.0 * n / d if d else 0.0


def _dist_parses(result: dict) -> bool:
    raw = str(result.get("dist_f") or result.get("distance_f")
              or result.get("dist") or result.get("distance") or "")
    try:
        return float(raw) > 0
    except ValueError:
        from src.helpers import distance_to_furlongs
        return distance_to_furlongs(raw) > 0


def main() -> int:
    date = sys.argv[1] if len(sys.argv) > 1 else today_str()
    doc = load_racecard(date)
    races = (doc or {}).get("racecards") or []
    if not races:
        print(f"No racecard data for {date} (file missing or wrong shape). "
              f"Run where the daily pipeline wrote racecards_{date}.json.")
        return 1

    full_form        = safe_load_json(data_path(f"full_form_{date}.json"))
    market_movers    = safe_load_json(data_path(f"market_movers_{date}.json"))
    trainer_profiles = safe_load_json(data_path(f"trainer_profiles_{date}.json"))
    form_read        = safe_load_json(data_path(f"form_read_{date}.json"))
    race_shape       = safe_load_json(data_path(f"race_shape_{date}.json"))

    comps = {k: [] for k in CRITICAL + INFO_ONLY}
    totals: list[float] = []
    runners_seen = scored = failed = 0

    for race in races:
        all_runners = race.get("runners") or []
        for runner in all_runners:
            runners_seen += 1
            try:
                s = score_runner(runner, race, all_runners, full_form,
                                 market_movers, trainer_profiles, form_read, race_shape)
            except Exception as exc:  # noqa: BLE001 — keep auditing
                failed += 1
                if failed <= 3:
                    log(f"scoring_healthcheck: score_runner failed — {exc}", "WARNING")
                continue
            scored += 1
            for k in comps:
                comps[k].append(float(s.get(k) or 0.0))
            totals.append(float(s.get("score") or 0.0))

    print("=" * 74)
    print(f"SCORING HEALTH-CHECK — {date}")
    print("=" * 74)
    print(f"Races: {len(races)}  Runners: {runners_seen}  Scored: {scored}  Failed: {failed}\n")

    # A scorer that raises for most runners is the loudest failure of all — the
    # whole card silently produces no usable scores. Flag it before anything else.
    if runners_seen and _pct(failed, runners_seen) >= 50.0:
        flags_fatal = (f"score_runner raised for {_pct(failed, runners_seen):.0f}% of "
                       f"runners — scoring is broken for this card (see WARNING log above)")
        print("=" * 74)
        print("VERDICT: PROBLEMS FOUND")
        print(f"  ✗ {flags_fatal}")
        print("=" * 74)
        return 1

    # --- Component distributions ------------------------------------------------
    print(f"{'Component':<20}{'n':>5}{'zero%':>8}{'mean':>8}{'p50':>7}{'max':>7}   flag")
    print("-" * 74)
    flags: list[str] = []
    for k in CRITICAL + INFO_ONLY:
        vals = comps[k]
        if not vals:
            continue
        zpct = _pct(sum(1 for v in vals if v == 0.0), len(vals))
        flag = ""
        if k in CRITICAL and zpct >= DEAD_ZERO_PCT:
            flag = "<<< DEAD/DEGRADED"
            flags.append(f"{k}: zero for {zpct:.0f}% of runners")
        elif k in INFO_ONLY:
            flag = "(info — zero is normal)"
        print(f"{k:<20}{len(vals):>5}{zpct:>7.0f}%{statistics.mean(vals):>8.1f}"
              f"{statistics.median(vals):>7.1f}{max(vals):>7.1f}   {flag}")
    print()

    # --- Data-source health + contracts ----------------------------------------
    print("DATA SOURCES")
    print("-" * 74)
    runner_ids = [str(r.get("horse_id") or "") for race in races for r in (race.get("runners") or [])]
    n_runners = max(1, len(runner_ids))

    # full_form + the exact contract the suitability bug violated
    horses = (full_form or {}).get("horses") or {}
    with_hist = [h for h in runner_ids if (horses.get(h) or [])]
    print(f"full_form: {'present' if full_form else 'MISSING'}  "
          f"horses={len(horses)}  runners_with_history={_pct(len(with_hist), n_runners):.0f}%")
    if with_hist:
        pos_ok = sum(1 for h in with_hist if _horse_position((horses[h] or [{}])[0], h))
        dist_ok = sum(1 for h in with_hist if _dist_parses((horses[h] or [{}])[0]))
        pos_pct, dist_pct = _pct(pos_ok, len(with_hist)), _pct(dist_ok, len(with_hist))
        print(f"  contract: position readable {pos_pct:.0f}%  |  distance parses {dist_pct:.0f}%")
        if pos_pct < 50:
            flags.append("full_form: finishing position unreadable for most history "
                         "(suitability will be 0 — the classic bug)")
        if dist_pct < 50:
            flags.append("full_form: past-race distance unparseable for most history")

    tp = trainer_profiles or {}
    tprof = tp.get("trainers") or {}
    tcov = _pct(sum(1 for race in races for r in (race.get("runners") or [])
                    if str(r.get("trainer_id") or "") in tprof), n_runners)
    print(f"trainer_profiles: {'present' if trainer_profiles else 'MISSING'}  "
          f"trainers={len(tprof)}  runner_trainer_coverage={tcov:.0f}%")
    if trainer_profiles and tcov < 20:
        flags.append("trainer_profiles present but covers <20% of runners' trainers")

    mv = (market_movers or {}).get("movements") or []
    print(f"market_movers: {'present' if market_movers else 'absent (normal pre-13:00)'}  movements={len(mv)}")

    fr = form_read or {}
    fr_cov = _pct(sum(1 for h in runner_ids if isinstance((fr.get(h) or {}).get("rating"), (int, float))), n_runners)
    print(f"form_read (AI): {'present' if form_read else 'MISSING'}  rating_coverage={fr_cov:.0f}%")

    rs = (race_shape or {})
    rs_races = sum(1 for race in races if (rs.get(str(race.get('race_id') or '')) or {}).get('horses'))
    print(f"race_shape (AI): {'present' if race_shape else 'MISSING'}  races_with_pace={_pct(rs_races, max(1,len(races))):.0f}%")
    print()

    # --- Score distribution vs confidence thresholds ---------------------------
    if totals:
        cb = get_params().get("confidence_bands", {})
        hi, mh, med = cb.get("high", 70), cb.get("medium_high", 60), cb.get("medium", 55)
        print("SCORE DISTRIBUTION (top scorer logic aside — all runners here)")
        print("-" * 74)
        print(f"  mean={statistics.mean(totals):.1f}  median={statistics.median(totals):.1f}  "
              f"max={max(totals):.1f}")
        print(f"  reaching MEDIUM (>={med:.0f}): {_pct(sum(t>=med for t in totals),len(totals)):.0f}%  |  "
              f"MEDIUM-HIGH (>={mh:.0f}): {_pct(sum(t>=mh for t in totals),len(totals)):.0f}%  |  "
              f"HIGH (>={hi:.0f}): {_pct(sum(t>=hi for t in totals),len(totals)):.0f}%")
        if _pct(sum(t >= mh for t in totals), len(totals)) < 2:
            print("  NOTE: almost no runner reaches MEDIUM-HIGH — score scale may be"
                  " mis-calibrated to the thresholds, or a component is still degraded.")
        print()

    # --- Verdict ----------------------------------------------------------------
    print("=" * 74)
    if flags:
        print("VERDICT: PROBLEMS FOUND")
        for f in flags:
            print(f"  ✗ {f}")
        print("=" * 74)
        return 1
    print("VERDICT: all components contributing, data contracts intact.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
