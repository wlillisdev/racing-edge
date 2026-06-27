"""racing_edge — a winter-jumps handicapping assistant.

The owner picks; the machine fetches the legwork and keeps an honest record.
Layered, jumps-first, human-in-the-loop. Nothing here picks for the owner.

Layers (each may only depend on those above it):
    config            env -> typed Config
    domain            the owner's METHOD — pure, no I/O (units, season, signals)
    data              fetch / normalise / persist (contracts at every boundary)
    selection         turn the read into a pick or a pass — pure
    betting           stake and settle — pure
    measurement       the honest ledger: CLV-first, season-aware
    ai                OPTIONAL advisory overlays (degrade to None; never gate a pick)
"""

__version__ = "0.1.0"
