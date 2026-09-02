"""RE-STUDY a finished race off the FULL FORM — the real learning loop (#27, #29).

The master's actual loop: when a result comes in, go BACK to the full form and study
the whole race again, knowing who won, to see what you MISSED. This lays out every
runner against the result, richest-first on the data the window really gives —
the mark (well-in vs raised), the form figures, the OFFICIAL rating, and the horse's
last runs WITH their in-running comments (how it ran) — so the clue that pointed to
the winner is on the page to find, not invented.

Honest by construction: every field is what the API returned. A blank is printed OWED,
never guessed — that is the whole point of going through the window without lying.

Pure: a race (card) + its result + each runner's history in, a readout out.
"""

from __future__ import annotations

from racing_edge.domain.manner import nap_verdict, run_style
from racing_edge.domain.courses import handedness
from racing_edge.domain.mark import mark_read, same_code_runs
from racing_edge.domain.models import PastRun, Race, RaceResult, RunnerResult


def _move(morning: float | None, sp: float | None) -> str:
    """Morning price -> SP: the one market signal the window gives. OWED if missing."""
    if not (morning and sp and morning > 1 and sp > 1):
        return "move OWED"
    if sp <= morning * 0.92:
        return f"BACKED {morning:.1f}->{sp:.1f}"
    if sp >= morning * 1.08:
        return f"drifted {morning:.1f}->{sp:.1f}"
    return f"steady {sp:.1f}"


def _past_line(h: PastRun) -> str:
    """One past run, with the COMMENT — the how-it-ran door the old code dropped.
    The race TYPE prints too (2026-07-21 audit: without it, the model shown an or107
    hurdles win against today's flat or61 happily re-derives by eye the cross-code
    'WELL-IN -46lb' fantasy that mark_read no longer computes)."""
    pos = str(h.position) if h.position else "—"
    cls = f"c{h.race_class}" if h.race_class else "c?"
    org = f"or{h.official_rating}" if h.official_rating else "or?"
    d = f"{h.distance_f:.0f}f" if h.distance_f else "?f"
    typ = (h.race_type or "?")[:6]
    where = f"{h.course[:10]} {typ} {d} {h.going[:6] or '?'} {cls} {org}".strip()
    comment = h.comment.strip() if h.comment.strip() else "OWED — no comment through the window"
    rid = f"  [race {h.race_id}]" if h.race_id else ""       # thread id for the investigator
    return f"        {h.date}  {pos:>2}  {where:<34}  {comment}{rid}"


def delta_line(r, race, hist) -> str:
    """TODAY v THE LAST SAME-CODE RUN, in facts (the SWOT 2026-09-02: 'the
    Post's picture, mechanically' — class move, mark move, trip move, going
    move — from fields the card already holds; the master: read the form,
    join the dots). Empty when there is no prior run to compare."""
    prev = same_code_runs(hist, race.code)
    if not prev:
        return ""
    lp = prev[0]
    parts = []
    if race.race_class and lp.race_class:
        d = lp.race_class - race.race_class            # Cl5 -> Cl4 is UP in class
        parts.append(f"class Cl{race.race_class} v Cl{lp.race_class} last "
                     + (f"(UP {d})" if d > 0 else f"(down {-d})" if d < 0 else "(same)"))
    if r.official_rating and lp.official_rating:
        d = r.official_rating - lp.official_rating
        parts.append(f"mark {r.official_rating} v {lp.official_rating} last ({d:+d}lb)")
    if race.distance_f and lp.distance_f:
        d = race.distance_f - lp.distance_f
        parts.append(f"trip {race.distance_f:g}f v {lp.distance_f:g}f last "
                     + (f"(UP {d:g}f)" if d > 0.4 else f"(DOWN {-d:g}f)" if d < -0.4
                        else "(same)"))
    if race.going and lp.going and race.going.lower() != lp.going.lower():
        parts.append(f"going {race.going} v {lp.going} last")
    if lp.course and race.course and lp.course.lower() == race.course.lower():
        parts.append("same course as last time")
    return ("today v last run (the delta line): " + "; ".join(parts)) if parts else ""


def render_preread(race: Race, histories: dict[str, tuple[PastRun, ...]],
                   past_n: int = 4) -> str:
    """The PRE-RACE full-form readout — same honest layout as the re-study, no result.
    This is what the morning deep-read (the nap picker) reasons over: mark, form,
    manner read, each contender's past runs WITH comments, market rank off the morning
    prices. Blanks say OWED. Contenders ordered by market."""
    priced = sorted([r for r in race.runners if r.odds.consensus and r.odds.consensus > 1],
                    key=lambda r: r.odds.consensus)  # type: ignore[arg-type,return-value]
    mkt_rank = {r.horse_id: i + 1 for i, r in enumerate(priced)}
    ordered = priced + [r for r in race.runners if r.horse_id not in mkt_rank]
    hcap = "Handicap " if race.is_handicap else ""
    head = f"{race.course} {race.off_time} — {hcap}{race.race_type}"
    if race.race_class:
        head += f" (Cl{race.race_class})"
    lines = [f"  PRE-RACE CARD: {head}  ({race.field_size} declared)"]
    # THE PACE MAP (#20 — the master, 2026-07-26: fixed as one of 'the silliest
    # things'): who is likely to LEAD, read from the comments already in hand.
    # No leader = muddling-pace risk; several = a contested, honest gallop.
    _leaders = []
    for r in ordered:
        _h = same_code_runs(histories.get(r.horse_id, ()), race.code)[:4]
        if run_style([x.comment for x in _h])[0] == "front":
            _leaders.append(r.horse)
    if _leaders:
        lines.append(f"  PACE MAP (#20): likely leader(s): {', '.join(_leaders[:4])}"
                     + (" — contested pace likely" if len(_leaders) >= 2 else ""))
    else:
        lines.append("  PACE MAP (#20): no established front-runner found in the "
                     "comments — muddling-pace risk, finishers may be inconvenienced")
    # THE SCALES (the master: 'giving a horse that much weight at 3 miles is crazy'
    # — the dot that decided Uttoxeter 07-26, previously invisible to every lens)
    _wts = [r.weight_lbs for r in race.runners if r.weight_lbs]
    _top = max(_wts) if _wts else None
    for r in ordered:
        hist = histories.get(r.horse_id, ())
        mark = mark_read(r.official_rating, hist, code=race.code)
        marktxt = mark.verdict or "mark OWED (no prior win / no today mark)"
        rank = (f"mkt {mkt_rank[r.horse_id]}/{len(priced)} @{r.odds.consensus}"
                if r.horse_id in mkt_rank else "price OWED")
        gear = f" | headgear {r.headgear}{'(1st time)' if r.headgear_first_time else ''}" \
            if r.headgear else ""
        lines.append("")
        tid = (f" trainer {r.trainer or '?'} [tid {r.trainer_id}]"
               + (f" ({r.trainer_location})" if r.trainer_location else "")) \
            if r.trainer_id else ""
        lines.append(f"  {r.horse:22} {rank}  [id {r.horse_id}]{tid}")
        wt = ""
        if r.weight_lbs and _top:
            st, lb = divmod(r.weight_lbs, 14)
            gap = _top - r.weight_lbs
            wt = (f" | carries {st}-{lb}"
                  + (f" ({gap}lb less than top weight)" if gap > 0 else " (TOP WEIGHT)"))
        # the draw reaches the reader (third audit, bot P5: parsed, read by nobody)
        drw = f" | draw {r.draw}" if r.draw is not None else ""
        lines.append(f"        mark: {marktxt}  | form {r.form or '?'} "
                     f"| OR {r.official_rating or '?'} RPR {r.rpr or '?'}{gear}{wt}{drw}")
        _dl = delta_line(r, race, hist)
        if _dl:
            lines.append(f"        {_dl}")
        _mh = same_code_runs(hist, race.code)[:4]
        mv = nap_verdict([h.comment for h in _mh],
                         positions=[h.position for h in _mh])
        if mv.recommendation != "neutral" or mv.finisher_runs or mv.non_finisher_runs:
            lines.append(f"        manner read (#1): {mv.recommendation} — {mv.reason}")
        _st, _f, _hd = run_style([x.comment for x in _mh])
        if _st != "mixed/unknown":
            lines.append(f"        run-style (#20): {_st} "
                         f"({_f if _st == 'front' else _hd} of last {len(_mh)} runs)")
        # THE FINDING-TOOLS LINE (the master, 2026-07-26: 'how many races has the
        # horse won at this distance, how many wins at that track, how many going
        # left- or right-handed') — counted in code from same-code wins, so the
        # reader judges facts, not impressions. Unknown handedness prints OWED.
        _sc = same_code_runs(hist, race.code)
        _wins = [h for h in _sc if h.position == 1]
        if _wins:
            _tw = sum(1 for h in _wins if h.course and race.course
                      and h.course.strip().lower() == race.course.strip().lower())
            _dw = sum(1 for h in _wins if h.distance_f and race.distance_f
                      and abs(h.distance_f - race.distance_f) <= 1.0)
            _lh = sum(1 for h in _wins if handedness(h.course) == "left")
            _rh = sum(1 for h in _wins if handedness(h.course) == "right")
            _uh = len(_wins) - _lh - _rh
            _today = handedness(race.course)
            hand = f"{_lh}L/{_rh}R" + (f"/{_uh}?" if _uh else "")
            note = ""
            if _today and (_lh + _rh) >= 2:
                one_way = ("left" if _rh == 0 else "right" if _lh == 0 else "")
                if one_way and one_way != _today:
                    note = (f" ⚠ all handed wins {one_way.upper()}-handed — today "
                            f"{_today.upper()}-handed")
                elif _today:
                    note = f" (today {_today}-handed)"
            elif _today:
                note = f" (today {_today}-handed)"
            lines.append(f"        wins: {_tw} at this track | {_dw} at ~this trip | "
                         f"by hand {hand}{note}")
        spot = r.spotlight.strip()
        if spot:
            lines.append(f"        spotlight: {spot[:200]}")
        if hist:
            for h in hist[:past_n]:
                lines.append(_past_line(h))
        else:
            lines.append("        past runs: OWED — none through the window")
    return "\n".join(lines)


def render_restudy(race: Race, result: RaceResult,
                   histories: dict[str, tuple[PastRun, ...]], past_n: int = 3) -> str:
    """The full-form re-read of one finished race, ordered by finish (winner first)."""
    res_by_id: dict[str, RunnerResult] = {rr.horse_id: rr for rr in result.runners}
    runners = sorted(
        race.runners,
        key=lambda r: (res_by_id.get(r.horse_id) is None,
                       res_by_id.get(r.horse_id).position is None
                       if res_by_id.get(r.horse_id) else True,
                       (res_by_id.get(r.horse_id).position or 99)
                       if res_by_id.get(r.horse_id) else 99),
    )
    winner = next((r for r in runners
                   if res_by_id.get(r.horse_id) and res_by_id[r.horse_id].position == 1), None)
    # market rank off SP — mechanical read done in CODE, not left for the model to
    # miscount (the "only recent winner" failure was exactly this class of error)
    priced = sorted([rr for rr in result.runners if rr.sp_dec and rr.sp_dec > 1],
                    key=lambda rr: rr.sp_dec)          # type: ignore[arg-type,return-value]
    mkt_rank = {rr.horse_id: i + 1 for i, rr in enumerate(priced)}
    hcap = "Handicap " if race.is_handicap else ""
    head = f"{race.course} {race.off_time} — {hcap}{race.race_type}"
    if race.race_class:
        head += f" (Cl{race.race_class})"
    lines = [
        f"  RE-STUDY (full form, off the result): {head}",
        f"  Winner: {winner.horse if winner else '?'} — now go back and find what pointed to it.",
        "  " + "=" * 78,
    ]
    for r in runners:
        rr = res_by_id.get(r.horse_id)
        pos = (str(rr.position) if rr and rr.position else (rr.status if rr else "—")) or "—"
        sp = rr.sp_dec if rr else None
        star = " ★WON" if (rr and rr.position == 1) else ""
        hist = histories.get(r.horse_id, ())
        mark = mark_read(r.official_rating, hist, code=race.code)
        marktxt = mark.verdict or "mark OWED (no prior win / no today mark)"
        btn = f" btn {rr.beaten_lengths}" if rr and rr.beaten_lengths else ""
        rank = f"  mkt {mkt_rank[r.horse_id]}/{len(priced)}" if r.horse_id in mkt_rank else ""
        lines.append("")
        lines.append(f"  {pos:>3}{star}  {r.horse:22} SP {sp or '?':<6} "
                     f"{_move(r.odds.morning, sp)}{rank}{btn}  [id {r.horse_id}]")
        gear = f" | headgear {r.headgear}{'(1st time)' if r.headgear_first_time else ''}" \
            if r.headgear else ""
        lines.append(f"        mark: {marktxt}  | form {r.form or '?'} "
                     f"| OR {r.official_rating or '?'} RPR {r.rpr or '?'}{gear}")
        # HOW THE RACE UNFOLDED (design audit 2026-07-25: today's in-running comments
        # were fetched, stored and then dropped — the study model was analysing a
        # race it never saw run, and the toolless sceptic judged pace claims blind)
        if rr and rr.comment.strip():
            lines.append(f"        ran TODAY: {rr.comment.strip()[:220]}")
        # the manner read, done in code from the comments (rule #1) — the model reasons
        # over the verdict instead of re-classifying prose (where it slips)
        _mh = same_code_runs(hist, race.code)[:4]
        mv = nap_verdict([h.comment for h in _mh],
                         positions=[h.position for h in _mh])
        if mv.recommendation != "neutral" or mv.finisher_runs or mv.non_finisher_runs:
            lines.append(f"        manner read (#1): {mv.recommendation} — {mv.reason}")
        spot = r.spotlight.strip()
        if spot:
            lines.append(f"        spotlight: {spot[:200]}")
        hist = histories.get(r.horse_id, ())
        if hist:
            for h in hist[:past_n]:
                lines.append(_past_line(h))
        else:
            lines.append("        past runs: OWED — none returned through the window")
    lines.append("")
    lines.append("  > the loop (#27/#29): read every runner's FORM first — mark, how it ran "
                 "(comments), fit — ")
    lines.append("    then ask: what said the winner BEFORE the price/result did? Bank the "
                 "clue you missed.")
    return "\n".join(lines)
