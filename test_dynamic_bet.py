"""
Test suite for dynamic_bet.py pure settlement / structure functions.

Run as:
  RACING_API_USERNAME=x RACING_API_PASSWORD=x DB_HOST=x DB_NAME=x DB_USER=x \
  DB_PASS=x EMAIL_SENDER=x EMAIL_PASSWORD=x EMAIL_RECIPIENT=x \
  python test_dynamic_bet.py

No pytest dependency. Prints PASS/FAIL per test and a final count.
Only pure functions are exercised: place_terms, _lines, _stake, settle_ticket,
_prod, choose_structure, _potential. Nothing touches the network/filesystem.
"""

import os

# Ensure the config-load on import succeeds even if the runner forgot env vars.
for _k in ("RACING_API_USERNAME", "RACING_API_PASSWORD", "DB_HOST", "DB_NAME",
           "DB_USER", "DB_PASS", "EMAIL_SENDER", "EMAIL_PASSWORD",
           "EMAIL_RECIPIENT"):
    os.environ.setdefault(_k, "x")

import dynamic_bet as db
from dynamic_bet import (
    place_terms, _lines, _stake, settle_ticket, _prod,
    choose_structure, _potential,
)

# --------------------------------------------------------------------------- #
# tiny test harness
# --------------------------------------------------------------------------- #
_PASS = 0
_FAIL = 0
_FAILURES = []


def check(name, fn):
    global _PASS, _FAIL
    try:
        fn()
    except AssertionError as exc:
        _FAIL += 1
        _FAILURES.append((name, str(exc)))
        print(f"FAIL  {name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        _FAIL += 1
        _FAILURES.append((name, f"ERROR {type(exc).__name__}: {exc}"))
        print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    else:
        _PASS += 1
        print(f"PASS  {name}")


def approx(a, b, tol=0.01):
    assert abs(a - b) < tol, f"expected {b}, got {a} (diff {abs(a-b)})"


# --------------------------------------------------------------------------- #
# leg builders
# --------------------------------------------------------------------------- #
def win_leg(odds, won=True, place_frac=0.25, place_pos=3, placed=None):
    return {
        "odds": odds,
        "won": won,
        "placed": won if placed is None else placed,
        "place_frac": place_frac,
        "place_pos": place_pos,
    }


def cand(horse_id, odds, agree, rank, place_pos=3, place_frac=0.25,
         course="Ascot", off_time="14:00", horse=None, source="METHOD"):
    """A candidate leg for choose_structure (already 'gathered')."""
    return {
        "horse_id": horse_id,
        "horse": horse or f"H{horse_id}",
        "sources": {source},
        "source": source,
        "odds": odds,
        "place_frac": place_frac,
        "place_pos": place_pos,
        "rank": rank,
        "agree": agree,
        "course": course,
        "off_time": off_time,
    }


def sorted_cands(legs):
    """Mirror gather()'s sort: agree-first then rank, both descending."""
    return sorted(legs, key=lambda l: (-l["agree"], -l["rank"]))


# =========================================================================== #
# SETTLEMENT — win-only, all legs win @ 2.0 (evens)
# =========================================================================== #
def t_trixie_allwin():
    legs = [win_leg(2.0) for _ in range(3)]
    s = settle_ticket(legs, "trixie", ew=False, unit=1.0)
    approx(s["stake"], 4.0)
    approx(s["return"], 20.0)   # 3 doubles@4=12 + 1 treble@8=8


def t_patent_allwin():
    legs = [win_leg(2.0) for _ in range(3)]
    s = settle_ticket(legs, "patent", ew=False, unit=1.0)
    approx(s["stake"], 7.0)
    approx(s["return"], 26.0)   # 3 singles@2=6 + 3 doubles@4=12 + 1 treble@8=8
    approx(s["bonus"], 0.0)     # patent has no bonus


def t_yankee_allwin():
    legs = [win_leg(2.0) for _ in range(4)]
    s = settle_ticket(legs, "yankee", ew=False, unit=1.0)
    approx(s["stake"], 11.0)
    approx(s["return"], 72.0)   # 6 dbl@4=24 + 4 trbl@8=32 + 1 four@16=16


def t_lucky15_allwin_evens():
    legs = [win_leg(2.0) for _ in range(4)]
    s = settle_ticket(legs, "lucky15", ew=False, unit=1.0)
    approx(s["stake"], 15.0)
    approx(s["return"], 88.0)   # yankee 72 + 4 singles@2=8 = 80, +10% = 88
    approx(s["bonus"], 8.0)


def t_double_allwin():
    legs = [win_leg(3.0), win_leg(4.0)]
    s = settle_ticket(legs, "double", ew=False, unit=1.0)
    approx(s["stake"], 1.0)
    approx(s["return"], 12.0)


def t_single_win():
    legs = [win_leg(5.0)]
    s = settle_ticket(legs, "single", ew=False, unit=1.0)
    approx(s["stake"], 1.0)
    approx(s["return"], 5.0)


# =========================================================================== #
# LUCKY 15 BONUSES
# =========================================================================== #
def t_lucky15_one_winner():
    # exactly one winner @ 6.0; one-winner double-odds single returns
    # 1 + 2*(6-1) = 11 units. stake 15, return 11.
    legs = [win_leg(6.0, won=True)] + [win_leg(4.0, won=False) for _ in range(3)]
    s = settle_ticket(legs, "lucky15", ew=False, unit=1.0)
    approx(s["stake"], 15.0)
    approx(s["return"], 11.0)


def t_lucky15_allwin_treble_odds():
    # all 4 win @ 3.0: base = 4*3 + 6*9 + 4*27 + 1*81 = 255, +10% = 280.5
    legs = [win_leg(3.0) for _ in range(4)]
    s = settle_ticket(legs, "lucky15", ew=False, unit=1.0)
    approx(s["return"], 280.5)


# =========================================================================== #
# EACH-WAY settlement
# =========================================================================== #
def t_ew_single_places_only():
    # @5.0, frac 0.25, pos 3. Horse PLACES (placed True, won False).
    # return = place part only = 1 + (5-1)*0.25 = 2.0. stake 2 -> P/L 0.
    legs = [win_leg(5.0, won=False, placed=True, place_frac=0.25, place_pos=3)]
    s = settle_ticket(legs, "single", ew=True, unit=1.0)
    approx(s["stake"], 2.0)
    approx(s["return"], 2.0)
    approx(s["pl"], 0.0)


def t_ew_single_wins():
    # won and placed: return = win 5 + place 2 = 7. stake 2.
    legs = [win_leg(5.0, won=True, placed=True, place_frac=0.25, place_pos=3)]
    s = settle_ticket(legs, "single", ew=True, unit=1.0)
    approx(s["stake"], 2.0)
    approx(s["return"], 7.0)


def t_ew_double_both_win():
    # @5.0 & 5.0 both win, frac 0.25.
    # win part = 5*5 = 25 ; place part = 2.0*2.0 = 4 ; return 29 ; stake 2.
    legs = [win_leg(5.0, won=True, placed=True), win_leg(5.0, won=True, placed=True)]
    s = settle_ticket(legs, "double", ew=True, unit=1.0)
    approx(s["stake"], 2.0)
    approx(s["return"], 29.0)


def t_ew_place_pos_zero_no_place_pay():
    # place_pos = 0 (win-only race, <=4 runners): place part must NOT pay even
    # if placed=True. A win-only single with place_pos 0: only win side counts.
    legs = [win_leg(5.0, won=True, placed=True, place_frac=0.25, place_pos=0)]
    s = settle_ticket(legs, "single", ew=True, unit=1.0)
    # stake still doubled for EW, win pays 5, place pays nothing.
    approx(s["stake"], 2.0)
    approx(s["return"], 5.0)


def t_ew_place_pos_zero_placed_not_won():
    # placed but place_pos 0 and not won -> nothing at all.
    legs = [win_leg(5.0, won=False, placed=True, place_frac=0.25, place_pos=0)]
    s = settle_ticket(legs, "single", ew=True, unit=1.0)
    approx(s["return"], 0.0)
    approx(s["pl"], -2.0)


# =========================================================================== #
# PLACE TERMS
# =========================================================================== #
def t_place_terms():
    cases = {
        (4, False): (0.0, 0),
        (5, False): (0.25, 2),
        (7, True): (0.25, 2),
        (8, False): (0.20, 3),
        (8, True): (0.25, 3),
        (15, True): (0.25, 3),
        (16, True): (0.25, 4),
        (16, False): (0.20, 3),
    }
    for (fs, hcap), (efrac, epos) in cases.items():
        frac, pos = place_terms(fs, hcap)
        approx(frac, efrac)
        assert pos == epos, f"({fs},{hcap}) pos expected {epos} got {pos}"


# =========================================================================== #
# _lines / _stake
# =========================================================================== #
def t_lines_counts():
    assert len(_lines(3, [1, 2, 3])) == 7, _lines(3, [1, 2, 3])
    assert len(_lines(4, [1, 2, 3, 4])) == 15
    assert len(_lines(4, [2, 3, 4])) == 11


def t_lines_composition():
    # 3 sel patent: 3 singles, 3 doubles, 1 treble
    lines = _lines(3, [1, 2, 3])
    sizes = sorted(len(c) for c in lines)
    assert sizes == [1, 1, 1, 2, 2, 2, 3], sizes
    # size guard: s > n is skipped
    assert _lines(2, [3]) == []


def t_stake():
    assert _stake(15, ew=True, unit=1.0) == 30
    assert _stake(7, ew=False, unit=1.0) == 7
    assert _stake(15, ew=False, unit=1.0) == 15
    assert _stake(11, ew=True, unit=2.0) == 44


def t_prod():
    approx(_prod([2.0, 3.0, 4.0]), 24.0)
    approx(_prod([]), 1.0)
    approx(_prod([5.0]), 5.0)


# =========================================================================== #
# CHOOSE_STRUCTURE
# =========================================================================== #
def t_cs_empty():
    plan = choose_structure([])
    assert plan["structure"] is None, plan
    assert plan["legs"] == []
    assert plan["banker"] is None
    approx(plan["stake_mult"], 0.0)


def t_cs_full_alignment_single():
    # top has agree=3 -> single on the banker only, mult 3.0
    legs = sorted_cands([
        cand("A", 5.0, agree=3, rank=120),
        cand("B", 6.0, agree=1, rank=50),
        cand("C", 7.0, agree=1, rank=40),
    ])
    plan = choose_structure(legs)
    assert plan["structure"] == "single", plan["structure"]
    assert len(plan["legs"]) == 1 and plan["legs"][0]["horse_id"] == "A", plan["legs"]
    approx(plan["stake_mult"], 3.0)
    assert plan["banker"]["horse_id"] == "A"


def t_cs_patent_aligned():
    # top agree=2, 3 value legs (odds 5-7) -> patent, mult 2.0, banker set
    legs = sorted_cands([
        cand("A", 5.0, agree=2, rank=120),
        cand("B", 6.0, agree=1, rank=50),
        cand("C", 7.0, agree=1, rank=40),
    ])
    plan = choose_structure(legs)
    assert plan["structure"] == "patent", plan["structure"]
    approx(plan["stake_mult"], 2.0)
    assert plan["banker"] is not None and plan["banker"]["horse_id"] == "A"
    assert plan["ew"] is True  # value_day (median 6 >= 4.5)


def t_cs_treble_short():
    # 3 short legs (odds <= 3.5), all agree=1 -> treble, ew False, mult 1.0, banker None
    legs = sorted_cands([
        cand("A", 3.0, agree=1, rank=30),
        cand("B", 3.5, agree=1, rank=20),
        cand("C", 2.5, agree=1, rank=10),
    ])
    plan = choose_structure(legs)
    assert plan["structure"] == "treble", plan["structure"]
    assert plan["ew"] is False
    approx(plan["stake_mult"], 1.0)
    assert plan["banker"] is None


def t_cs_lucky15_value():
    # 4 value legs agree=1 -> lucky15, ew True
    legs = sorted_cands([
        cand("A", 5.0, agree=1, rank=40),
        cand("B", 6.0, agree=1, rank=30),
        cand("C", 7.0, agree=1, rank=20),
        cand("D", 5.5, agree=1, rank=10),
    ])
    plan = choose_structure(legs)
    assert plan["structure"] == "lucky15", plan["structure"]
    assert plan["ew"] is True


def t_cs_caps_at_four():
    legs = sorted_cands([cand(str(i), 6.0, agree=1, rank=50 - i) for i in range(6)])
    plan = choose_structure(legs)
    assert len(plan["legs"]) == 4, len(plan["legs"])


# =========================================================================== #
# _potential
# =========================================================================== #
def t_potential_lucky15():
    legs = [cand("A", 5.0, 1, 40), cand("B", 6.0, 1, 30),
            cand("C", 7.0, 1, 20), cand("D", 8.0, 1, 10)]
    plan = {"structure": "lucky15", "ew": True, "legs": legs}
    pot = _potential(plan, 1.0)
    approx(pot["stake"], 30.0)  # 15 lines * 2 (ew) * 1
    approx(pot["all_win"], 5.0 * 6.0 * 7.0 * 8.0)
    # one single win: shortest leg @5 -> 1 + 2*(5-1) = 9
    approx(pot["one_single_win"], 9.0)


def t_potential_empty():
    assert _potential({"structure": "single", "ew": False, "legs": []}, 1.0) == {}


def t_potential_treble_no_single():
    legs = [cand("A", 3.0, 1, 40), cand("B", 3.5, 1, 30), cand("C", 2.5, 1, 20)]
    plan = {"structure": "treble", "ew": False, "legs": legs}
    pot = _potential(plan, 1.0)
    approx(pot["all_win"], 3.0 * 3.5 * 2.5)
    approx(pot["one_single_win"], 0.0)  # treble has no single line


# =========================================================================== #
# LOGIC / PROPERTY tests
# =========================================================================== #
def t_prop_fullcover_ge_largest_line():
    # any winning full-cover ticket: return >= the largest single line.
    legs = [win_leg(3.0), win_leg(4.0), win_leg(5.0), win_leg(6.0)]
    s = settle_ticket(legs, "lucky15", ew=False, unit=1.0)
    largest_line = 1.0 * _prod(l["odds"] for l in legs)  # the fourfold
    assert s["return"] >= largest_line, (s["return"], largest_line)


def t_prop_ew_monotonic_in_place_frac():
    # EW return non-decreasing in place_frac (all else equal, legs place).
    last = -1.0
    for frac in (0.10, 0.20, 0.25, 0.50):
        legs = [win_leg(5.0, won=True, placed=True, place_frac=frac, place_pos=3),
                win_leg(5.0, won=True, placed=True, place_frac=frac, place_pos=3)]
        s = settle_ticket(legs, "double", ew=True, unit=1.0)
        assert s["return"] >= last, (frac, s["return"], last)
        last = s["return"]


def t_prop_losing_ticket_zero():
    # all legs lose -> return 0, P/L = -stake.
    legs = [win_leg(5.0, won=False, placed=False) for _ in range(4)]
    s = settle_ticket(legs, "lucky15", ew=False, unit=1.0)
    approx(s["return"], 0.0)
    approx(s["pl"], -s["stake"])
    assert s["won_lines"] == 0


def t_prop_unit_scaling():
    # doubling the unit doubles stake and return for a deterministic ticket.
    legs = [win_leg(2.0) for _ in range(3)]
    s1 = settle_ticket(legs, "trixie", ew=False, unit=1.0)
    s2 = settle_ticket(legs, "trixie", ew=False, unit=2.0)
    approx(s2["stake"], 2 * s1["stake"])
    approx(s2["return"], 2 * s1["return"])


# =========================================================================== #
# runner
# =========================================================================== #
def main():
    tests = [
        ("trixie all-win @evens", t_trixie_allwin),
        ("patent all-win @evens (no bonus)", t_patent_allwin),
        ("yankee all-win @evens", t_yankee_allwin),
        ("lucky15 all-win @evens (+10%)", t_lucky15_allwin_evens),
        ("double both win 3.0x4.0", t_double_allwin),
        ("single win @5.0", t_single_win),
        ("lucky15 one-winner @6.0 double-odds", t_lucky15_one_winner),
        ("lucky15 all-win @3.0 = 280.5", t_lucky15_allwin_treble_odds),
        ("EW single places only", t_ew_single_places_only),
        ("EW single wins (win+place)", t_ew_single_wins),
        ("EW double both win", t_ew_double_both_win),
        ("EW place_pos=0 no place pay (won)", t_ew_place_pos_zero_no_place_pay),
        ("EW place_pos=0 placed-not-won = 0", t_ew_place_pos_zero_placed_not_won),
        ("place_terms table", t_place_terms),
        ("_lines counts", t_lines_counts),
        ("_lines composition + size guard", t_lines_composition),
        ("_stake", t_stake),
        ("_prod", t_prod),
        ("choose_structure empty -> None", t_cs_empty),
        ("choose_structure full alignment single", t_cs_full_alignment_single),
        ("choose_structure patent aligned", t_cs_patent_aligned),
        ("choose_structure treble short", t_cs_treble_short),
        ("choose_structure lucky15 value", t_cs_lucky15_value),
        ("choose_structure caps at 4", t_cs_caps_at_four),
        ("_potential lucky15", t_potential_lucky15),
        ("_potential empty", t_potential_empty),
        ("_potential treble (no single line)", t_potential_treble_no_single),
        ("property: full-cover >= largest line", t_prop_fullcover_ge_largest_line),
        ("property: EW monotonic in place_frac", t_prop_ew_monotonic_in_place_frac),
        ("property: losing ticket returns 0", t_prop_losing_ticket_zero),
        ("property: unit scaling", t_prop_unit_scaling),
    ]
    print("=" * 64)
    print("dynamic_bet.py test suite")
    print("=" * 64)
    for name, fn in tests:
        check(name, fn)
    print("=" * 64)
    print(f"TOTAL: {_PASS + _FAIL}   PASS: {_PASS}   FAIL: {_FAIL}")
    print("=" * 64)
    if _FAILURES:
        print("\nFailures:")
        for name, msg in _FAILURES:
            print(f"  - {name}: {msg}")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
