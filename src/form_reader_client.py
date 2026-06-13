"""
form_reader_client.py — thin Anthropic client for the AI "Form Reader" layer.

Design principles (mirrors src/api_client.py)
---------------------------------------------
- All public methods return safe types (dict, None) — callers never need to
  catch exceptions for normal flow. A missing API key, a missing/old SDK, a
  network failure, or a malformed model response all degrade to None.
- The module import never raises: the Anthropic SDK import is guarded so an
  absent or outdated `anthropic` package degrades the factory to None rather
  than crashing the pipeline at import time.
- The system prompt is FROZEN (a module constant) — it defines the persona of
  a professional UK form analyst and never varies per request, which keeps
  behaviour deterministic and prompt-cache friendly.
- Structured JSON output is requested via the tool-use pattern (input_schema)
  so the response is guaranteed to parse against the verdict schema.
- No temperature/top_p/top_k parameters are sent — Opus 4.x and the current
  Haiku/Sonnet generation reject them.
"""

from __future__ import annotations

import json
from typing import Optional

from src.config import get_config
from src.helpers import log

# ---------------------------------------------------------------------------
# Guarded SDK import — a missing or too-old `anthropic` degrades to None.
# ---------------------------------------------------------------------------
try:
    from anthropic import Anthropic  # type: ignore
    _SDK_AVAILABLE = True
except Exception as _exc:  # pragma: no cover - import-environment dependent
    Anthropic = None  # type: ignore
    _SDK_AVAILABLE = False


# ---------------------------------------------------------------------------
# Frozen system prompt + output schema
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a professional UK horse racing form analyst with decades of "
    "experience reading the Racing Post and trade press. You are given the "
    "form data for a single runner in a single race: its ratings, recent form, "
    "race context, and — most importantly — the tipster-language narrative "
    "(spotlight, in-running comment, connections' quotes, and stable tour "
    "remarks). Read that narrative the way a sharp professional would: weigh "
    "what is genuinely positive against hype, spot negative signals that the "
    "raw numbers miss (excuses, doubts about trip/ground, stable out of form, "
    "market drift), and discount empty boilerplate. Be calibrated and "
    "sceptical — most runners are not strong bets. Return ONLY a structured "
    "verdict in the required JSON schema. Do not add commentary outside the "
    "schema.\n\n"
    "Field guidance:\n"
    "- verdict: STRONG_NAP (stand-out, bet with confidence) | SOLID (clear "
    "claims, reliable) | EACH_WAY (place rather than win interest) | MARGINAL "
    "(some appeal but flawed) | AVOID (steer clear).\n"
    "- rating: 0-100 integer confidence in this runner as a win bet today.\n"
    "- one_line_read: a single crisp sentence summarising the read.\n"
    "- key_positives / key_negatives: short factual bullet phrases drawn from "
    "the data, not invented.\n"
    "- narrative_signal: BULLISH | NEUTRAL | BEARISH — the overall tone of the "
    "tipster-language narrative once hype is discounted."
)

_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["STRONG_NAP", "SOLID", "EACH_WAY", "MARGINAL", "AVOID"],
        },
        "rating": {"type": "integer"},
        "one_line_read": {"type": "string"},
        "key_positives": {"type": "array", "items": {"type": "string"}},
        "key_negatives": {"type": "array", "items": {"type": "string"}},
        "narrative_signal": {
            "type": "string",
            "enum": ["BULLISH", "NEUTRAL", "BEARISH"],
        },
    },
    "required": [
        "verdict",
        "rating",
        "one_line_read",
        "key_positives",
        "key_negatives",
        "narrative_signal",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class FormReaderClient:
    """Thin wrapper around the Anthropic Messages API for form reading."""

    _TIMEOUT = 30          # seconds per request
    _MAX_TOKENS = 1024     # the verdict is small; cap output tightly
    _MAX_RETRIES = 8       # auto-retry 429/5xx with backoff (honours retry-after)

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("FormReaderClient: api_key must not be empty")
        if not _SDK_AVAILABLE or Anthropic is None:
            raise RuntimeError("FormReaderClient: anthropic SDK unavailable")
        self._model = model
        # max_retries lets the SDK ride out rate-limit (429) bursts by backing
        # off and honouring the retry-after header instead of dropping the call.
        # with_options gives a hard per-attempt timeout without mutating later.
        self._client = Anthropic(
            api_key=api_key, max_retries=self._MAX_RETRIES
        ).with_options(timeout=float(self._TIMEOUT))

    @property
    def model(self) -> str:
        return self._model

    def read_form(self, payload: dict) -> Optional[dict]:
        """Read a single runner's form payload and return a structured verdict.

        Args:
            payload: Per-runner JSON-serialisable dict (horse, ratings, form,
                narrative, etc.) — sent verbatim as the user turn.

        Returns:
            Parsed verdict dict matching the verdict schema, or None on any
            failure (no exception ever propagates to the caller).
        """
        try:
            user_content = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            log(f"form_reader_client: payload not serialisable — {exc}", "WARNING")
            return None

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                tools=[{
                    "name": "structured_output",
                    "description": "Return a structured verdict matching the required JSON schema.",
                    "input_schema": _VERDICT_SCHEMA,
                }],
                tool_choice={"type": "tool", "name": "structured_output"},
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as exc:  # never raise into the pipeline
            log(f"form_reader_client: API call failed — {exc}", "WARNING")
            return None

        try:
            tool_use = next(
                (b for b in response.content if getattr(b, "type", "") == "tool_use"),
                None,
            )
            if tool_use is None:
                log("form_reader_client: no tool_use block in response", "WARNING")
                return None
            return tool_use.input  # already a dict, no json.loads needed
        except (AttributeError, ValueError) as exc:
            log(f"form_reader_client: could not parse verdict — {exc}", "WARNING")
            return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_form_reader() -> Optional[FormReaderClient]:
    """Construct a FormReaderClient from environment configuration.

    Returns None (never raises) if the API key is absent or the Anthropic SDK
    is unavailable, so callers degrade gracefully.
    """
    cfg = get_config()
    if not cfg.anthropic_api_key:
        log("get_form_reader: ANTHROPIC_API_KEY absent — form reader disabled", "INFO")
        return None
    if not _SDK_AVAILABLE:
        log("get_form_reader: anthropic SDK unavailable — form reader disabled", "WARNING")
        return None
    try:
        return FormReaderClient(
            api_key=cfg.anthropic_api_key,
            model=cfg.anthropic_model,
        )
    except Exception as exc:
        log(f"get_form_reader: client init failed — {exc}", "WARNING")
        return None
