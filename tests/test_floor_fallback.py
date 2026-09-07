"""THE FLOOR CAPS, IT NEVER RE-PICKS — and a capped bet is never CONFIDENT.

2026-09-07, the first morning of the inversion on the box: the class-first
key put up Venetian Prince (Winter Hill G3); the reader objected on cited
facts (top weight, 5th of 5 last time, 10f untried); the profile floor refused
him (mark OWED); and `_best_floor_fit` jumped past Morris Dancer, On Message,
Maho Bay (won the race at 5/2) and Edelak (won at 11/10F) to the first
WELL-IN survivor, Saint Polo — banked as 'CONFIDENT NAP' while the body of
the mail said 'LEAN only'. Saint Polo was 3rd at 7/4F, beaten by the engine's
own #2. The master, the same night: "apply fixes as recommended" — after a
veto the bank goes to the key's next survivor, capped at LEAN; the label
follows the cap.
"""
from types import SimpleNamespace as NS

from racing_edge.cli.nap import (_floor_refusal_fallback, _is_confident,
                                 _next_in_key_order)


def _sv(hid, *, score=4, well_in=True, mark_known=True, cls=1, price=3.0, race="r1"):
    return NS(runner=NS(horse_id=hid, horse=hid), price=price,
              race=NS(race_id=race, race_class=cls),
              conviction=NS(score=score, well_in=well_in, mark_known=mark_known,
                            confident=True, flags=(), cautions=()))


# the 2026-09-07 survivors, in the key's order — Saint Polo is the only one
# the floor likes (well-in, mark known, 4+ ticks, Cl4, anchored market)
VP = _sv("VENETIAN PRINCE", score=1, well_in=False, mark_known=False)
MD = _sv("MORRIS DANCER", score=3, well_in=False)
OM = _sv("ON MESSAGE", score=3, well_in=False)
MB = _sv("MAHO BAY", score=4, well_in=False, mark_known=False)
ED = _sv("EDELAK", score=5, well_in=False, cls=3, race="r2")
SP = _sv("SAINT POLO", score=5, well_in=True, cls=4, race="r3", price=2.5)
SURVIVORS = [VP, MD, OM, MB, ED, SP]
FIELD = [NS(race=NS(race_id="r1"), price=2.0), NS(race=NS(race_id="r1"), price=5.0),
         NS(race=NS(race_id="r1"), price=8.0),
         NS(race=NS(race_id="r3"), price=2.5), NS(race=NS(race_id="r3"), price=4.2),
         NS(race=NS(race_id="r3"), price=5.4)]


def test_after_a_veto_the_bank_goes_to_the_keys_next_survivor_not_the_floors_horse():
    pick, why = _floor_refusal_fallback(True, True, SURVIVORS, FIELD, VP)
    assert pick is MD                    # the key's next — NOT Saint Polo
    assert "next survivor" in why
    assert _next_in_key_order(SURVIVORS, SP) is None
    assert _next_in_key_order(SURVIVORS, _sv("NOBODY")) is None


def test_a_floor_refusal_without_a_veto_leaves_the_engines_pick_standing():
    pick, why = _floor_refusal_fallback(True, False, SURVIVORS, FIELD, VP)
    assert pick is VP and "never re-picks" in why
    # last in the order with a veto: nothing after it, the pick stands
    pick, why = _floor_refusal_fallback(True, True, SURVIVORS, FIELD, SP)
    assert pick is SP and "stands" in why


def test_reader_mode_still_takes_the_best_floor_fit_survivor():
    pick, why = _floor_refusal_fallback(False, False, SURVIVORS, FIELD, VP)
    assert pick is SP and "floor-fit" in why


def test_a_capped_bet_is_never_labelled_confident():
    c = NS(confident=True, flags=(), cautions=())
    assert _is_confident("", [], c, False, False, False, lean_cap=False) is True
    # the Saint Polo label: everything else says yes, the cap says LEAN
    assert _is_confident("", [], c, False, False, False, lean_cap=True) is False
    # a deep case decides its own confidence — and the cap still wins
    assert _is_confident("confident", ["case"], c, False, False, False, lean_cap=False) is True
    assert _is_confident("confident", ["case"], c, False, False, False, lean_cap=True) is False
    assert _is_confident("lean", ["case"], c, False, False, False, lean_cap=False) is False
