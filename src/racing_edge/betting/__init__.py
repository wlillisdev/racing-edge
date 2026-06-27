"""betting — turn a pick into a bet, the honest way. Pure.

Every line here is a hard-won lesson baked in as a default, not a hard law:
  • singles only — short-priced multiples bleed even on winning days (the Yankee)
  • flat, small stakes — Kelly OFF until a real edge is proven out-of-sample
  • a value RANGE, not a floor — skip odds-on (no value) and longshots (the bleed
    zone); the exact band is a tracked hypothesis, not a hard-coded ghost
  • take the best/early price — never SP (the margin is fattest there)
"""
