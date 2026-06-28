"""ai — OPTIONAL advisory overlays. Degrade to nothing without a key.

The research is explicit about where an LLM helps and where it doesn't: it is at
or below a coin-flip at PREDICTION, but genuinely strong at READING unstructured
narrative. So this layer does exactly one thing — read the race comment /
spotlight and extract structured, SOURCE-CITED reads for the human to verify. It
never scores, rates, ranks, picks, or stakes. The architecture gate forbids
domain/selection from importing it.
"""
