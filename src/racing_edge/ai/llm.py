"""A tiny Anthropic completer — degrades to None without a key or SDK.

Used only by the narrative reader. Haiku is plenty for source-grounded text
extraction (and cheap). Nothing here ever blocks a pick: no key -> no completer
-> the narrative layer simply returns no reads.
"""

from __future__ import annotations

import os
from collections.abc import Callable

_MODEL = "claude-haiku-4-5"


def get_completer() -> Callable[[str], str] | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
    except Exception:
        # Missing SDK, or an SDK/httpx version clash (e.g. the removed `proxies`
        # arg) — the narrative is advisory, so degrade to no reads rather than
        # crash the whole pipeline. The docstring's promise: never block a pick.
        return None

    def complete(prompt: str) -> str:
        msg = client.messages.create(
            model=_MODEL, max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        block = msg.content[0]
        return getattr(block, "text", "")

    return complete
