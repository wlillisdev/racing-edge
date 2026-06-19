"""
dynamic_bet.py — the daily bet ARCHITECT (turn the 3 systems' winners into money).

The honest truth a 30-year pro tells you first: a multiple is where the
bookmaker's margin COMPOUNDS. A treble of three market-priced horses is more
-EV than any one of them alone — the over-round multiplies. So a multiple only
makes money if each leg genuinely beats its price. That is EXACTLY what the
scoreboard measures (does our pick beat its SP?). So we do not slap on a Lucky 15
every day. We build the multiple ONLY from legs we rate as value, we let the
DAY'S HAND pick the structure, and we PAPER-TRADE it before a penny goes on.

Dynamic structure selection (the "outside the box" bit — the bet is not fixed):
  • gather the day's selections from all 3 systems (Method, quant NAP, Shadow),
    plus the strongest Method per-race picks; dedupe by horse.
  • classify each: banker (short + confident) / value (mid-priced) / pass.
  • choose the shape from the hand you're dealt:
       0-1 strong   -> single            (EW if value-priced, else win)
       2 strong     -> double            (EW if value, else win — singles noted)
       3 strong     -> EW PATENT         (7 bets: land ONE and a single pays back)
                       or straight treble (if all three are short bankers)
       4 strong     -> LUCKY 15          (EW if value) / Yankee (short bankers)
  • WIN vs EACH-WAY is chosen per the prices: EW only where the place part
    actually pays (≈9/2+); win-only on short ones where EW is dead money.

Correct settlement: full-cover combinatorics, UK each-way place terms by field
size / handicap, and the standard Lucky-15 bonuses (one-winner double-odds,
all-winners +10%). Every day's ticket is logged to data/bet_ledger.csv and
settled against real results — we PROVE it banks before staking real money.

Usage:
  python dynamic_bet.py                  # build today's recommended ticket
  python dynamic_bet.py 2026-06-19
  python dynamic_bet.py --settle 2026-06-18   # settle a day against results
  python dynamic_bet.py --summary             # running paper-trade P/L
"""

from __future__ import annotations

import argparse
import csv
import os
from itertools import combinations
from typing import Optional

from method_pick import build as method_build
from racecard_loader import load_racecard
from src.api_client import get_client
from src.helpers import data_path, log, safe_load_json, safe_write_json, today_str

LEDGER = "bet_ledger.csv"
UNIT = 1.0                       # £ per line (the staking unit; total scales from this)
VALUE_PRICE = 4.5                # decimal odds at/above which the EACH-WAY place part earns its keep
SHORT_PRICE = 3.5                # at/below which a leg is a "banker" and EW is dead money
MIN_ODDS, MAX_ODDS = 2.0, 11.0   # bettable band for a multiple leg (wider than singles: value needs price)

# combo sizes that define each named bet (n = number of selections it consumes)
STRUCTURES = {
    "single":   [1],
    "double":   [2],
    "treble":   [3],
    "fourfold": [4],
    "trixie":   [2, 3],
    "patent":   [1, 2, 3],
    "yankee":   [2, 3, 4],
    "lucky15":  [1, 2, 3, 4],
}


# --------------------------------------------------------------------------- #
# bet maths — combinatorics, each-way place terms, settlement
# --------------------------------------------------------------------------- #
def place_terms(field_size: int, is_handicap: bool) -> tuple[float, int]:
    """UK each-way terms: (fraction_of_odds, number_of_places). (0,0) = win only."""
    if field_size <= 4:
        return 0.0, 0
    if field_size <= 7:
        return 0.25, 2
    if is_handicap:
        if field_size >= 16:
            return 0.25, 4
        return 0.25, 3                 # 8-15 runner handicap
    return 0.20, 3                     # 8+ non-handicap


def _lines(n: int, sizes: list[int]) -> list[tuple[int, ...]]:
    out: list[tuple[int, ...]] = []
    for s in sizes:
        if s <= n:
            out.extend(combinations(range(n), s))
    return out


def _stake(n_lines: int, ew: bool, unit: float) -> float:
    return round(n_lines * (2 if ew else 1) * unit, 2)


def settle_ticket(legs: list[dict], structure: str, ew: bool, unit: float) -> dict:
    """Settle a full-cover ticket. Each leg: {odds, won, placed, place_frac, place_pos}.

    Returns total stake, total return, profit/loss, and a line breakdown.
    """
    n = len(legs)
    lines = _lines(n, STRUCTURES[structure])
    stake = _stake(len(lines), ew, unit)
    total = 0.0
    won_lines = 0
    for combo in lines:
        win_ok = all(legs[i]["won"] for i in combo)
        if win_ok:
            won_lines += 1
            total += unit * _prod(legs[i]["odds"] for i in combo)
        if ew:
            # place part pays only where every leg placed AND the race offered places
            if all(legs[i].get("place_pos", 0) > 0 and legs[i]["placed"] for i in combo):
                total += unit * _prod(1 + (legs[i]["odds"] - 1) * legs[i]["place_frac"] for i in combo)

    # --- Lucky 15 bonuses (bookmaker-standard; documented assumption) ---
    bonus = 0.0
    if structure == "lucky15":
        winners = sum(1 for l in legs if l["won"])
        if winners == 1:
            # one-winner: double the odds on that single's WIN return (a single is 1 unit)
            w = next(l for l in legs if l["won"])
            bonus += unit * (w["odds"] - 1)              # extra (odds-1) on top of the single already counted
        elif winners == n:
            bonus += 0.10 * total                        # all-winners +10%
    total += bonus

    return {
        "structure": structure, "ew": ew, "n_legs": n, "n_lines": len(lines),
        "stake": stake, "return": round(total, 2), "pl": round(total - stake, 2),
        "won_lines": won_lines, "bonus": round(bonus, 2),
    }


def _prod(it) -> float:
    p = 1.0
    for x in it:
        p *= x
    return p


# --------------------------------------------------------------------------- #
# assemble the day's hand from the 3 systems
# --------------------------------------------------------------------------- #
def _race_index(doc: dict) -> dict:
    """horse_id -> {field_size, is_handicap} from the loaded racecard."""
    idx: dict[str, dict] = {}
    for race in (doc.get("racecards") or []):
        runners = race.get("runners") or []
        name = f"{race.get('race_name','')} {race.get('type','')}".lower()
        meta = {"field_size": len(runners),
                "is_handicap": "handicap" in name or "h'cap" in name}
        for r in runners:
            idx[str(r.get("horse_id") or "")] = meta
    return idx


def _price(p: dict) -> Optional[float]:
    for k in ("price", "consensus_price", "morning_price", "sp_dec"):
        v = p.get(k)
        try:
            v = float(v)
            if v > 1.0:
                return v
        except (TypeError, ValueError):
            continue
    return None


def gather(date_str: str) -> list[dict]:
    """The day's candidate legs, with ALIGNMENT: when the 3 systems land on the
    same horse, agreement is signal. Each leg carries the set of systems that
    chose it (`agree` = how many) — the anchor for conviction sizing.
    """
    doc = load_racecard(date_str) or {}
    ridx = _race_index(doc)

    # Prefer the method pick already written by the pipeline; build only if absent.
    method = safe_load_json(data_path(f"method_pick_{date_str}.json")) or method_build(date_str) or {}
    napdoc = safe_load_json(data_path(f"nap_candidates_{date_str}.json")) or {}

    raw: list[tuple[float, dict, str]] = []   # (confidence_rank, pick, source)
    # Method: the per-race picks (already vetoed-clean), strongest carry highest case
    for p in (method.get("race_picks") or []):
        if not p.get("vetoed"):
            raw.append((float(p.get("method_case") or 0), p, "METHOD"))
    # Quant NAP + Shadow #1
    if napdoc.get("nap"):
        raw.append((float(napdoc["nap"].get("score") or 0) + 100, napdoc["nap"], "NAP"))
    shadow = napdoc.get("shadow") or []
    if shadow:
        raw.append((float(shadow[0].get("score") or 0), shadow[0], "SHADOW"))

    # Aggregate by horse so a pick chosen by several systems is ONE leg that
    # records every system backing it — that overlap is the alignment edge.
    by_horse: dict[str, dict] = {}
    for rank, p, src in sorted(raw, key=lambda t: -t[0]):
        hid = str(p.get("horse_id") or "")
        if not hid:
            continue
        price = _price(p)
        if price is None or not (MIN_ODDS <= price <= MAX_ODDS):
            continue
        if hid in by_horse:
            by_horse[hid]["sources"].add(src)
            by_horse[hid]["rank"] = max(by_horse[hid]["rank"], round(rank, 1))
            continue
        meta = ridx.get(hid, {"field_size": 8, "is_handicap": False})
        frac, pos = place_terms(meta["field_size"], meta["is_handicap"])
        by_horse[hid] = {
            "horse_id": hid, "horse": p.get("horse"), "sources": {src},
            "course": p.get("course"), "off_time": p.get("off_time"),
            "odds": round(price, 2), "place_frac": frac, "place_pos": pos,
            "rank": round(rank, 1),
        }
    legs = list(by_horse.values())
    for l in legs:
        l["agree"] = len(l["sources"])
        l["source"] = "+".join(sorted(l["sources"]))
    # Alignment first (agreement is the strongest signal), then model rank.
    legs.sort(key=lambda l: (-l["agree"], -l["rank"]))
    return legs


def choose_structure(legs: list[dict]) -> dict:
    """Dynamic: the hand picks the shape, and AGREEMENT picks the conviction.

    Max output / min risk is a tension — the resolution is alignment:
      • when the systems CONVERGE on one horse it is the BANKER. It anchors
        every line (min risk: the slip can't die on a weak leg you didn't rate)
        and the stake is PRESSED (conviction sizing) for max output.
      • when they're SPREAD, do the opposite — base stake, cover the risk with
        an EW Patent / Lucky 15 so one winner still pays you back.
    """
    if not legs:
        return {"structure": None, "ew": False, "legs": [], "why": "no bettable selections today",
                "conviction": "none", "stake_mult": 0.0, "banker": None}

    legs = legs[:4]                                   # never more than a Lucky 15
    prices = [l["odds"] for l in legs]
    med = sorted(prices)[len(prices) // 2]
    n = len(legs)
    value_day = med >= VALUE_PRICE                    # prices rich enough for EW to pay
    short_day = all(p <= SHORT_PRICE for p in prices)  # all bankers

    # --- alignment / conviction (legs already sorted agree-first) ---
    top_agree = legs[0]["agree"]
    banker = legs[0] if top_agree >= 2 else None      # 2+ systems on the same horse
    # press the stake with conviction; flat when the systems disagree
    stake_mult = {3: 3.0, 2: 2.0}.get(top_agree, 1.0)
    conviction = {3: "FULL alignment — all systems agree", 2: "aligned — 2 systems agree"}.get(
        top_agree, "spread — systems disagree")

    def _ret(structure, ew, why, used=None):
        return {"structure": structure, "ew": ew, "legs": used if used is not None else legs,
                "why": why, "conviction": conviction, "stake_mult": stake_mult, "banker": banker}

    # All-systems-on-one-horse: the lowest-variance way to grow a bank is to
    # back the surest thing hard. Press the single ON THE BANKER ALONE — don't
    # dilute the conviction with legs the other systems didn't rate.
    if banker and top_agree >= 3:
        return _ret("single", banker["odds"] >= VALUE_PRICE,
                    f"all 3 systems on {banker['horse']} — max output / min risk is the "
                    f"pressed single ({stake_mult:.0f}× stake), not a diluted multiple",
                    used=[banker])

    if n == 1:
        return _ret("single", value_day,
                    f"only one strong selection — {'each-way' if value_day else 'win'} single")
    if n == 2:
        return _ret("double", value_day,
                    f"two strong selections — {'each-way ' if value_day else ''}double"
                    + (f", anchored on banker {banker['horse']}" if banker else ""))
    if n == 3:
        if short_day and not banker:
            return _ret("treble", False,
                        "three short-priced bankers — straight treble (EW would be dead money)")
        return _ret("patent", value_day,
                    "three value selections — EW Patent: land just ONE and a single pays you back"
                    + (f"; banker {banker['horse']} anchors it" if banker else ""))
    # n == 4
    if short_day and not banker:
        return _ret("yankee", False,
                    "four short bankers — Yankee (11 bets, no singles): needs two+ to land")
    return _ret("lucky15", value_day,
                "four value selections — Lucky 15: one winner returns, two+ and you're in profit"
                + (f"; banker {banker['horse']}'s single underwrites the slip" if banker else ""))


# --------------------------------------------------------------------------- #
# build / display / ledger
# --------------------------------------------------------------------------- #
def _potential(plan: dict, unit: float) -> dict:
    """What the ticket does under simple scenarios (all-win; and best single)."""
    legs = plan["legs"]
    if not legs:
        return {}
    n = len(legs)
    lines = _lines(n, STRUCTURES[plan["structure"]])
    stake = _stake(len(lines), plan["ew"], unit)
    all_win = unit * _prod(l["odds"] for l in legs) if any(len(c) == n for c in lines) else 0.0
    # return if ONLY the shortest-priced leg wins (and singles are covered)
    one_win = 0.0
    if 1 in STRUCTURES[plan["structure"]]:
        best = min(legs, key=lambda l: l["odds"])
        one_win = unit * best["odds"]
        if plan["structure"] == "lucky15":
            one_win = unit * (1 + 2 * (best["odds"] - 1))   # one-winner double-odds bonus
    return {"stake": round(stake, 2), "all_win": round(all_win, 2),
            "one_single_win": round(one_win, 2)}


def build(date_str: Optional[str] = None, unit: float = UNIT) -> dict:
    date_str = date_str or today_str()
    legs = gather(date_str)
    plan = choose_structure(legs)
    eff_unit = round(unit * plan.get("stake_mult", 1.0), 2)   # conviction sizing
    pot = _potential(plan, eff_unit)
    out = {"date": date_str, "unit": eff_unit, "base_unit": unit, **plan, "potential": pot,
           "candidates": legs}
    safe_write_json(data_path(f"dynamic_bet_{date_str}.json"), out)
    _log_pending(out)
    log(f"dynamic_bet: {date_str} -> {plan['structure']} "
        f"({len(plan['legs'])} legs, {'EW' if plan['ew'] else 'win'})")
    return out


def _logged_status(date_str: str) -> Optional[str]:
    path = data_path(LEDGER)
    if not os.path.exists(path):
        return None
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["date"] == date_str:
                return r["status"]
    return None


def _log_pending(out: dict) -> None:
    if not out["legs"] or _logged_status(out["date"]) is not None:
        return
    path = data_path(LEDGER)
    is_new = not os.path.exists(path)
    pot = out.get("potential") or {}
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "structure", "ew", "legs",
                                           "stake", "status", "return", "pl"])
        if is_new:
            w.writeheader()
        w.writerow({
            "date": out["date"], "structure": out["structure"],
            "ew": int(out["ew"]),
            "legs": " / ".join(f"{l['horse']}@{l['odds']}" for l in out["legs"]),
            "stake": pot.get("stake", 0.0), "status": "pending",
            "return": "", "pl": "",
        })


def settle(date_str: str, unit: float = UNIT) -> Optional[dict]:
    """Settle a previously-built ticket against the day's results; update the ledger."""
    out = safe_load_json(data_path(f"dynamic_bet_{date_str}.json"))
    if not out or not out.get("legs"):
        print(f"No ticket to settle for {date_str}.")
        return None
    try:
        doc = get_client().get_results_by_date(date_str) or {}
    except Exception as exc:  # noqa: BLE001
        log(f"dynamic_bet settle: results fetch failed {date_str} — {exc}", "WARNING")
        return None
    res: dict[str, dict] = {}
    for race in (doc.get("results") or []):
        for r in (race.get("runners") or []):
            hid = str(r.get("horse_id") or "")
            if hid:
                try:
                    pos = int(str(r.get("position") or "").strip())
                except (TypeError, ValueError):
                    pos = 99
                res[hid] = {"pos": pos, "sp": r.get("sp_dec") or r.get("sp")}

    legs = []
    for l in out["legs"]:
        r = res.get(l["horse_id"], {})
        pos = r.get("pos", 99)
        legs.append({**l, "won": pos == 1, "placed": pos <= l["place_pos"] if l["place_pos"] else pos == 1})
    s = settle_ticket(legs, out["structure"], out["ew"], unit)
    _update_ledger(date_str, s)
    print(f"SETTLED {date_str}: {out['structure']} "
          f"stake £{s['stake']:.2f} -> return £{s['return']:.2f}  (P/L £{s['pl']:+.2f})")
    for l in legs:
        flag = "WON" if l["won"] else ("plc" if l["placed"] else "—")
        print(f"   {flag:>3}  {l['horse']:<20} @{l['odds']}")
    return s


def _update_ledger(date_str: str, s: dict) -> None:
    path = data_path(LEDGER)
    if not os.path.exists(path):
        return
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    for r in rows:
        if r["date"] == date_str:
            r["status"] = "settled"
            r["return"] = f"{s['return']:.2f}"
            r["pl"] = f"{s['pl']:.2f}"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "structure", "ew", "legs",
                                           "stake", "status", "return", "pl"])
        w.writeheader()
        w.writerows(rows)


def summary() -> None:
    path = data_path(LEDGER)
    if not os.path.exists(path):
        print("No bet ledger yet.")
        return
    rows = [r for r in csv.DictReader(open(path, newline="", encoding="utf-8"))
            if r["status"] == "settled" and r["pl"] not in ("", None)]
    if not rows:
        print("No settled tickets yet — paper trade is still pending results.")
        return
    stake = sum(float(r["stake"]) for r in rows)
    pl = sum(float(r["pl"]) for r in rows)
    wins = sum(1 for r in rows if float(r["pl"]) > 0)
    print("=" * 58)
    print(f"PAPER-TRADE LEDGER — {len(rows)} settled day(s)")
    print("=" * 58)
    print(f"  staked £{stake:.2f}   returned £{stake + pl:.2f}   "
          f"P/L £{pl:+.2f}   ROI {100 * pl / stake if stake else 0:+.1f}%")
    print(f"  winning days: {wins}/{len(rows)}")


def _print_ticket(out: dict) -> None:
    print(f"DYNAMIC BET — {out['date']}   (paper-trade; prove it before real money)")
    print("=" * 70)
    if not out["legs"]:
        print("  No bet today — not enough in the value band. Discipline is a position.")
        return
    print(f"  STRUCTURE: {out['structure'].upper()}  "
          f"({'EACH-WAY' if out['ew'] else 'WIN'})")
    print(f"  CONVICTION: {out.get('conviction','?')}"
          + (f"   (stake ×{out.get('stake_mult',1):.0f})" if out.get('stake_mult', 1) != 1 else ""))
    if out.get("banker"):
        print(f"  BANKER: {out['banker']['horse']} @{out['banker']['odds']} "
              f"— {out['banker']['source']} all on it")
    print(f"  WHY: {out['why']}")
    print("  legs:")
    for l in out["legs"]:
        ew = f"  [EW {l['place_pos']}pl @1/{int(1/l['place_frac'])}]" if (out["ew"] and l["place_pos"]) else ""
        print(f"    · {l['horse']:<20} {str(l['course'])[:10]:<10} {l['off_time']}  "
              f"@{l['odds']}  ({l['source']}){ew}")
    pot = out["potential"]
    print(f"\n  stake £{pot['stake']:.2f} (unit £{out['unit']:.2f})")
    if pot.get("one_single_win"):
        print(f"  if just your shortest leg wins:   ~£{pot['one_single_win']:.2f} back")
    print(f"  if ALL legs win:                  £{pot['all_win']:.2f}")
    print("\n  NB: a multiple only profits long-run if each leg beats its price.")
    print("      That is what the scoreboard tests. Paper-trade banks daily.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=today_str())
    ap.add_argument("--settle", nargs="?", const="TODAY", metavar="DATE",
                    help="settle a day's ticket vs results (no date = today)")
    ap.add_argument("--summary", action="store_true", help="running paper-trade P/L")
    ap.add_argument("--unit", type=float, default=UNIT)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if args.summary:
        summary()
        return 0
    if args.settle:
        settle(today_str() if args.settle == "TODAY" else args.settle, args.unit)
        print()
        summary()
        return 0

    out = build(args.date, args.unit)
    _print_ticket(out)
    return 0


def _selftest() -> int:
    """Verify the bet maths against hand-calculated figures."""
    ok = True
    # Lucky 15, all four win @ 2.0 each (evens). 15 lines, £1 unit, WIN only.
    legs = [{"odds": 2.0, "won": True, "placed": True, "place_frac": 0.25, "place_pos": 3} for _ in range(4)]
    s = settle_ticket(legs, "lucky15", ew=False, unit=1.0)
    # 4 singles@2 =8 ; 6 doubles@4 =24 ; 4 trebles@8 =32 ; 1 four@16 =16 ; sum=80 ; +10% all-win bonus =88
    exp = 88.0
    print(f"Lucky15 4x evens all-win: return £{s['return']:.2f} (expect £{exp:.2f})  "
          f"stake £{s['stake']:.2f} (expect £15.00)")
    ok &= abs(s["return"] - exp) < 0.01 and abs(s["stake"] - 15.0) < 0.01
    # Patent, only ONE winner @ 5.0; others lose. 7 lines win-only, stake £7.
    legs = [{"odds": 5.0, "won": True, "placed": True, "place_frac": 0.25, "place_pos": 3}] + \
           [{"odds": 3.0, "won": False, "placed": False, "place_frac": 0.25, "place_pos": 3} for _ in range(2)]
    s = settle_ticket(legs, "patent", ew=False, unit=1.0)
    # only the one winning single pays: £5 ; stake £7 ; P/L -2
    print(f"Patent one-winner@5.0: return £{s['return']:.2f} (expect £5.00)  P/L £{s['pl']:+.2f}")
    ok &= abs(s["return"] - 5.0) < 0.01 and abs(s["stake"] - 7.0) < 0.01
    # Straight double both win @ 3.0 and 4.0 = 12 ; stake 1
    legs = [{"odds": 3.0, "won": True, "placed": True, "place_frac": 0.25, "place_pos": 3},
            {"odds": 4.0, "won": True, "placed": True, "place_frac": 0.25, "place_pos": 3}]
    s = settle_ticket(legs, "double", ew=False, unit=1.0)
    print(f"Double 3.0x4.0 both win: return £{s['return']:.2f} (expect £12.00)")
    ok &= abs(s["return"] - 12.0) < 0.01
    print("SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
