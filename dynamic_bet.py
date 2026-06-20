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
# Conviction press: ON only once the paper-trade ledger shows a real edge.
# Flat staking is the honest default — pressing on faith (and pressing the
# shortest price, which is anti-Kelly) is how edges get given back.
PRESS_ENABLED = False
PRESS_FACTOR = 1.5               # modest, capped; NOT a 3x vote-count multiplier
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
    # Void legs (non-runners) are settled at odds 1.0 and excluded from the
    # winner count so they don't spuriously trigger the one-/all-winner bonuses.
    bonus = 0.0
    if structure == "lucky15":
        live = [l for l in legs if not l.get("void")]
        winners = sum(1 for l in live if l["won"])
        if winners == 1:
            # one-winner: double the odds on that single's WIN return (a single is 1 unit)
            w = next(l for l in live if l["won"])
            bonus += unit * (w["odds"] - 1)              # extra (odds-1) on top of the single already counted
        elif live and winners == len(live):
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
        # Keep handicap detection in step with the NAP scorer's keywords — a
        # wrong call flips the each-way place terms (real-money impact).
        is_hcap = any(k in name for k in ("handicap", "hcap", "h'cap", "nursery"))
        meta = {"field_size": len(runners), "is_handicap": is_hcap}
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


# source priority for ordering (NAP is the primary read; Method overlay is the
# only genuinely NEW lens on top of it; Shadow is the quant's second string).
SRC_PRIORITY = {"NAP": 3, "METHOD": 2, "SHADOW": 1}


def gather(date_str: str) -> list[dict]:
    """The day's candidate legs.

    A blunt vote-count across the 3 systems is misleading: Method is the NAP
    score PLUS your overlay, and the Shadow is built by excluding the NAP — so
    NAP and Shadow can never coincide, and "Method agrees with NAP" is mostly
    the overlay leaving the NAP's pick alone. The genuinely independent lens is
    the OVERLAY itself. So each leg carries `overlay` (your read's contribution)
    and a `two_lens` flag — the NAP pick that your overlay ALSO pushes up — which
    is real, if modest, confirmation rather than re-counting one model's number.
    """
    doc = load_racecard(date_str) or {}
    ridx = _race_index(doc)

    # Prefer the method pick already written by the pipeline; build only if absent.
    method = safe_load_json(data_path(f"method_pick_{date_str}.json")) or method_build(date_str) or {}
    napdoc = safe_load_json(data_path(f"nap_candidates_{date_str}.json")) or {}

    raw: list[tuple[dict, str, Optional[float]]] = []     # (pick, source, overlay)
    for p in (method.get("race_picks") or []):
        if not p.get("vetoed"):
            raw.append((p, "METHOD", p.get("overlay")))
    if napdoc.get("nap"):
        raw.append((napdoc["nap"], "NAP", None))
    shadow = napdoc.get("shadow") or []
    if shadow:
        raw.append((shadow[0], "SHADOW", None))

    by_horse: dict[str, dict] = {}
    for p, src, overlay in raw:
        hid = str(p.get("horse_id") or "")
        if not hid:
            continue
        price = _price(p)
        if price is None or not (MIN_ODDS <= price <= MAX_ODDS):
            continue
        if hid in by_horse:
            by_horse[hid]["sources"].add(src)
            if overlay is not None:
                by_horse[hid]["overlay"] = float(overlay)
            continue
        meta = ridx.get(hid)
        if meta is None:
            # Not found in the racecard (ID mismatch / non-runner): don't invent
            # each-way terms — settle win-only rather than fabricate places.
            frac, pos = 0.0, 0
            log(f"dynamic_bet: {p.get('horse')} not in racecard index — win-only terms", "WARNING")
        else:
            frac, pos = place_terms(meta["field_size"], meta["is_handicap"])
        by_horse[hid] = {
            "horse_id": hid, "horse": p.get("horse"), "sources": {src},
            "course": p.get("course"), "off_time": p.get("off_time"),
            "odds": round(price, 2), "place_frac": frac, "place_pos": pos,
            "overlay": float(overlay) if overlay is not None else None,
        }
    legs = list(by_horse.values())
    for l in legs:
        l["agree"] = len(l["sources"])
        l["source"] = "+".join(sorted(l["sources"]))
        # two genuine lenses: the NAP's pick that your overlay ALSO rates up.
        l["two_lens"] = ("NAP" in l["sources"] and "METHOD" in l["sources"]
                         and (l.get("overlay") or 0) > 0)
        l["prio"] = max(SRC_PRIORITY[s] for s in l["sources"])
        l["sources"] = sorted(l["sources"])   # JSON-serialisable (sets are not)
    # Genuine two-lens first, then source priority (NAP>Method>Shadow), then price.
    legs.sort(key=lambda l: (-int(l["two_lens"]), -l["prio"], l["odds"]))
    return legs


def choose_structure(legs: list[dict]) -> dict:
    """The hand picks the shape; the genuine two-lens read picks the conviction.

    Honest conviction (the audit's correction): the 3 systems are NOT
    independent — Method = NAP + overlay, and Shadow excludes the NAP — so a
    vote-count over-states confirmation. The one real cross-check is the NAP's
    pick that your OVERLAY also rates up (`two_lens`). That earns a BANKER tag
    and a modest press — but staking stays FLAT until the paper-trade ledger
    actually shows an edge (PRESS_ENABLED). Pressing the shortest price hardest
    is anti-Kelly; we don't do it on faith.

    Each-way is offered only when EVERY leg is value-priced AND offers places —
    no dead place stakes on short or small-field legs.
    """
    if not legs:
        return {"structure": None, "ew": False, "legs": [], "why": "no bettable selections today",
                "conviction": "none", "stake_mult": 0.0, "banker": None}

    legs = legs[:4]                                   # never more than a Lucky 15
    prices = [l["odds"] for l in legs]
    n = len(legs)
    # EW only when the place part earns its keep on EVERY leg (lowest price in
    # the value band) and every leg actually offers places.
    ew_ok = min(prices) >= VALUE_PRICE and all(l["place_pos"] > 0 for l in legs)
    short_day = all(p <= SHORT_PRICE for p in prices)

    # --- genuine two-lens conviction (NAP pick your overlay also likes) ---
    banker = legs[0] if legs[0].get("two_lens") else None
    press = PRESS_FACTOR if (banker and PRESS_ENABLED) else 1.0
    if banker:
        conviction = (f"two-lens — quant NAP + your overlay both on {banker['horse']}"
                      + ("" if PRESS_ENABLED else " (staking flat until the ledger earns the press)"))
    else:
        conviction = "single-lens — no independent confirmation"

    def _ret(structure, ew, why, used=None):
        return {"structure": structure, "ew": ew, "legs": used if used is not None else legs,
                "why": why, "conviction": conviction, "stake_mult": press, "banker": banker}

    def _kind(ew):
        return "each-way" if ew else "win"

    if n == 1:
        return _ret("single", ew_ok, f"one strong selection — {_kind(ew_ok)} single")
    if n == 2:
        return _ret("double", ew_ok,
                    f"two selections — {_kind(ew_ok)} double"
                    + (f", anchored on banker {banker['horse']}" if banker else ""))
    if n == 3:
        if short_day and not banker:
            return _ret("treble", False,
                        "three short-priced bankers — straight win treble (EW would be dead money)")
        return _ret("patent", ew_ok,
                    f"three selections — {_kind(ew_ok)} Patent: land just ONE and a single pays you back"
                    + (f"; banker {banker['horse']} anchors it" if banker else ""))
    # n == 4
    if short_day and not banker:
        return _ret("yankee", False,
                    "four short bankers — win Yankee (11 bets, no singles): needs two+ to land")
    return _ret("lucky15", ew_ok,
                f"four selections — {_kind(ew_ok)} Lucky 15: one winner returns, two+ and you're in profit"
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
    """Settle a previously-built ticket against the day's results; update the ledger.

    Settles at the SAME (pressed) unit the ticket was logged with — never the
    base unit — so the ledger ROI is internally consistent. Won't settle until
    the day's results are actually in; a leg whose horse never appears in a
    non-empty result set is treated as a NON-RUNNER (void leg @ 1.0), not a loser.
    """
    out = safe_load_json(data_path(f"dynamic_bet_{date_str}.json"))
    if not out or not out.get("legs"):
        print(f"No ticket to settle for {date_str}.")
        return None
    staked_unit = float(out.get("unit") or unit)      # the pressed unit, as logged
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

    if not res:                                       # results not published yet
        print(f"Results not available yet for {date_str} — leaving ticket pending.")
        return None

    legs = []
    for l in out["legs"]:
        r = res.get(l["horse_id"])
        if r is None:
            # day's results are in but this horse isn't in them -> non-runner.
            # Void leg: settled at 1.0, passes through any multiple (correct rule).
            legs.append({**l, "odds": 1.0, "won": True, "placed": True, "void": True})
        else:
            pos = r["pos"]
            legs.append({**l, "won": pos == 1,
                         "placed": pos <= l["place_pos"] if l["place_pos"] else pos == 1,
                         "void": False})
    s = settle_ticket(legs, out["structure"], out["ew"], staked_unit)
    _update_ledger(date_str, s)
    print(f"SETTLED {date_str}: {out['structure']} "
          f"stake £{s['stake']:.2f} -> return £{s['return']:.2f}  (P/L £{s['pl']:+.2f})")
    for l in legs:
        flag = "VOID" if l.get("void") else ("WON" if l["won"] else ("plc" if l["placed"] else "—"))
        print(f"   {flag:>4}  {l['horse']:<20} @{l['odds']}")
    return s


def _update_ledger(date_str: str, s: dict) -> None:
    """Mark a day settled — atomic rewrite (temp file + os.replace) so a crash
    or an overlapping run can never truncate the whole ledger."""
    path = data_path(LEDGER)
    if not os.path.exists(path):
        return
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["date"] == date_str:
            r["status"] = "settled"
            r["return"] = f"{s['return']:.2f}"
            r["pl"] = f"{s['pl']:.2f}"
    tmp = f"{path}.tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "structure", "ew", "legs",
                                           "stake", "status", "return", "pl"])
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


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
    roi = 100 * pl / stake if stake else 0.0
    n = len(rows)
    print("=" * 58)
    print(f"PAPER-TRADE LEDGER — {n} settled day(s)")
    print("=" * 58)
    print(f"  staked £{stake:.2f}   returned £{stake + pl:.2f}   "
          f"P/L £{pl:+.2f}   ROI {roi:+.1f}%")
    print(f"  winning days: {wins}/{n}")
    # --- honesty guard: don't trust a small sample, and don't press on faith ---
    print(_trust_verdict(n, roi))


# Minimum settled days before the ledger ROI means anything (multiples are
# high-variance — a handful of days is noise, not signal).
TRUST_SAMPLE = 40
# ...and the flat baseline must be PROFITABLE over that sample before we'd ever
# switch the conviction press on. Pressing into an unproven edge is how you lose.
PRESS_UNLOCK_ROI = 5.0


def _trust_verdict(n: int, roi: float) -> str:
    if n < TRUST_SAMPLE:
        return (f"  → SAMPLE TOO SMALL ({n}/{TRUST_SAMPLE} days): treat this ROI as noise. "
                f"Keep banking flat-staked; do not tune, do not press yet.")
    if roi < PRESS_UNLOCK_ROI:
        return (f"  → SAMPLE OK ({n} days) but edge unproven (ROI {roi:+.1f}% < "
                f"{PRESS_UNLOCK_ROI:.0f}%): stay flat. No real edge to press.")
    return (f"  → EDGE CONFIRMED ({n} days, ROI {roi:+.1f}%): the flat baseline pays. "
            f"Now it's defensible to enable the conviction press (PRESS_ENABLED=True).")


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
