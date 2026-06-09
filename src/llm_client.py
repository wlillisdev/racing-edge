"""
llm_client.py — shared generic Anthropic client for the AI intelligence layer.

This is the common foundation used by every LLM component in the system
(race-shape projection, second-opinion arbiter, loser autopsy, briefing
writer, text extraction). The form reader has its own dedicated client
(src/form_reader_client.py); everything else should use THIS module so there
is a single, consistently-degrading call path.

Design principles (mirror src/api_client.py and src/form_reader_client.py)
--------------------------------------------------------------------------
- Every public function returns a safe type (dict, str, None). A missing API
  key, missing/old SDK, network failure, or malformed model response all
  degrade to None — callers never need try/except for normal flow.
- Module import never raises: the Anthropic SDK import is guarded.
- Callers pass their OWN frozen system prompt + JSON schema, so each component
  defines its own persona while sharing the transport, timeout, ret/parse, and
  degradation logic here.
- No temperature/top_p/top_k — the current model generation rejects them.
- The raw call is deterministic-friendly: a frozen system prompt + a strict
  json_schema response format.
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
except Exception:  # pragma: no cover - import-environment dependent
    Anthropic = None  # type: ignore
    _SDK_AVAILABLE = False


class LLMClient:
    """Thin, general-purpose wrapper around the Anthropic Messages API.

    Unlike FormReaderClient, the system prompt and schema are supplied per
    call so a single client instance serves every intelligence component.
    """

    _DEFAULT_TIMEOUT = 45        # seconds per request (whole-card reads are larger)
    _DEFAULT_MAX_TOKENS = 2048   # generous: pace/autopsy outputs are richer than a verdict

    def __init__(self, api_key: str, default_model: str) -> None:
        if not api_key:
            raise ValueError("LLMClient: api_key must not be empty")
        if not _SDK_AVAILABLE or Anthropic is None:
            raise RuntimeError("LLMClient: anthropic SDK unavailable")
        self._default_model = default_model
        self._client = Anthropic(api_key=api_key).with_options(
            timeout=float(self._DEFAULT_TIMEOUT)
        )

    @property
    def default_model(self) -> str:
        return self._default_model

    def call_structured(
        self,
        system_prompt: str,
        user_payload: dict | str,
        schema: dict,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[dict]:
        """Make one structured-output call. Returns parsed dict or None.

        Args:
            system_prompt: FROZEN persona/instructions for the component.
            user_payload:  dict (json-encoded) or pre-formatted string — the
                           volatile per-request content.
            schema:        JSON schema the response must satisfy.
            model:         override the configured default model for this call.
            max_tokens:    override the default output cap.

        Returns:
            Parsed JSON dict matching `schema`, or None on any failure.
        """
        if isinstance(user_payload, str):
            user_content = user_payload
        else:
            try:
                user_content = json.dumps(user_payload, ensure_ascii=False, default=str)
            except (TypeError, ValueError) as exc:
                log(f"llm_client: payload not serialisable — {exc}", "WARNING")
                return None

        try:
            response = self._client.messages.create(
                model=model or self._default_model,
                max_tokens=max_tokens or self._DEFAULT_MAX_TOKENS,
                system=system_prompt,
                tools=[{
                    "name": "structured_output",
                    "description": "Return a structured JSON response matching the required schema.",
                    "input_schema": schema,
                }],
                tool_choice={"type": "tool", "name": "structured_output"},
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as exc:  # never raise into the pipeline
            log(f"llm_client: API call failed — {exc}", "WARNING")
            return None

        try:
            tool_use = next(
                (b for b in response.content if getattr(b, "type", "") == "tool_use"),
                None,
            )
            if tool_use is None:
                log("llm_client: no tool_use block in response", "WARNING")
                return None
            return tool_use.input  # already a dict, no json.loads needed
        except (AttributeError, ValueError) as exc:
            log(f"llm_client: could not parse response — {exc}", "WARNING")
            return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_client(default_model: Optional[str] = None) -> Optional[LLMClient]:
    """Construct an LLMClient from environment configuration.

    Returns None (never raises) when ANTHROPIC_API_KEY is absent or the SDK is
    unavailable, so every AI component degrades to its non-LLM behaviour.

    Args:
        default_model: model id to use when a call does not specify one.
            Falls back to cfg.anthropic_model (default claude-haiku-4-5).
    """
    cfg = get_config()
    if not cfg.anthropic_api_key:
        log("get_llm_client: ANTHROPIC_API_KEY absent — LLM layer disabled", "INFO")
        return None
    if not _SDK_AVAILABLE:
        log("get_llm_client: anthropic SDK unavailable — LLM layer disabled", "WARNING")
        return None
    try:
        return LLMClient(
            api_key=cfg.anthropic_api_key,
            default_model=default_model or cfg.anthropic_model,
        )
    except Exception as exc:
        log(f"get_llm_client: client init failed — {exc}", "WARNING")
        return None


def llm_available() -> bool:
    """Cheap check: is the LLM layer usable right now? (key present + SDK)."""
    try:
        cfg = get_config()
    except Exception:
        return False
    return bool(cfg.anthropic_api_key) and _SDK_AVAILABLE
