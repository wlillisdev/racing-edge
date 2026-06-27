"""domain — the owner's METHOD, codified. Pure: no I/O, no DB, no network, no LLM.

Everything here is a deterministic function of a race and its runners. It is the
part that must be unit-tested to near-100% and never silently changed by the AI.
"""
