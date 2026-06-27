"""data — fetch, normalise, persist. Typed contracts at every boundary.

The audits found results had NO canonical normaliser (~20 consumers each
reshaped raw API dicts), and everything spoke bare dict[str, Any]. Here the
boundaries speak the frozen dataclasses in `schemas`, normalised once.
"""
