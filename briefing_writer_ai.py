"""
briefing_writer_ai.py — AI "Briefing Writer" pipeline stage.

Turns the structured daily pick (the NAP, its confidence/stake, top reasons and
the alternatives) into a punchy, natural-language morning briefing written in
the voice of a sharp but honest UK racing tipster.

This is an OPTIONAL, ADDITIVE layer. The templated briefing produced by
morning_briefing_report.py remains the source of truth; this writer only adds a
human-sounding narrative on top. When the LLM layer is unavailable, or there is
no NAP to write about, it degrades to a stub note and returns 0 — nothing
downstream breaks.

Inputs:
    data/nap_candidates_YYYY-MM-DD.json   (from nap_selector_v3 + cluster_review)
        keys used: nap {horse, course, off_time, score, grade, confidence,
                        stake_recommendation, morning_price, reasons, warnings,
                        ai_verdict, ai_read}, watchlist[], day_verdict
    data/arbiter_YYYY-MM-DD.json          (OPTIONAL — AI second opinion; merged
                                           into the payload as a hint if present)

Outputs:
    reports/ai_briefing_YYYY-MM-DD.txt    (formatted, readable narrative)
    data/ai_briefing_YYYY-MM-DD.json      (structured result + model id)

Structured schema requested from the model:
    {headline: str, nap_writeup: str, confidence_note: str, alternatives_note: str}

Degrades gracefully: if ANTHROPIC_API_KEY is absent or the SDK/network is
unavailable, OR there is no NAP, write a short stub note and a stub JSON, log a
clear WARNING, and return 0. The templated briefing is unaffected either way.

Exit codes:
    0  — success (INCLUDING every degraded case: no LLM, no NAP, model returned
         nothing)
    1  — only on a write error

================================================================================
INTEGRATION — for the orchestrator to wire in.
(Do NOT implement here; this is documentation only. The files referenced below
are read-only for this component.)

1. daily_pipeline.py — ONE-LINE insertion into PIPELINE_STEPS, placed AFTER
   morning_briefing_report and BEFORE email_report so the AI narrative exists
   before the email is assembled:

       ("morning_briefing_report","morning_briefing_report.py",[]),
       ("briefing_writer_ai",      "briefing_writer_ai.py",     []),   # <-- add this line
       ("email_report",           "email_report.py",          []),

   It is non-critical: if it fails or degrades it returns 0, and the email step
   (which already always runs) falls back to the templated briefing.

2. email_report.py / morning_briefing_report.py — PREPEND the AI briefing when
   present, fall back to the templated briefing when absent. email_report.py's
   _load_briefing() already returns the templated text; wrap it so the AI
   narrative is stitched on top when the file exists and is non-empty:

       from src.helpers import report_path, today_str

       def _ai_briefing_prefix(date_str: str) -> str:
           # Read reports/ai_briefing_YYYY-MM-DD.txt if present & non-empty.
           p = Path(report_path(f"ai_briefing_{date_str}.txt"))
           if p.exists():
               try:
                   text = p.read_text(encoding="utf-8").strip()
                   if text:
                       return text + "\n\n" + ("─" * 60) + "\n\n"
               except OSError:
                   pass
           return ""   # absent/empty/unreadable => no prefix, templated briefing stands

   Then in main(), after body_text is loaded:

       body_text = _ai_briefing_prefix(date_str) + body_text

   The AI narrative reads first; the full templated briefing follows beneath it
   unchanged. When ai_briefing_*.txt is missing (degraded run) the prefix is ""
   and the email is exactly today's templated briefing — zero behaviour change.
   morning_briefing_report.py could prepend identically inside _build_briefing()
   if the operator prefers the narrative baked into the briefing file itself.
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from src.helpers import (
    data_path,
    format_odds,
    log,
    report_path,
    safe_load_json,
    safe_write_json,
    today_str,
)
from src.llm_client import get_llm_client

SEP = "═" * 60

# How many alternative bets to feed the writer (keep the payload tight).
MAX_ALTERNATIVES: int = 4
# How many of the NAP's reasons to surface to the writer.
MAX_REASONS: int = 6

# ---------------------------------------------------------------------------
# FROZEN system prompt — the tipster persona. Volatile per-day content is
# supplied separately as the JSON user payload.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT: str = (
    "You are a sharp but scrupulously honest UK horse racing tipster writing a "
    "short morning briefing for a serious punter. Your job is to turn a "
    "structured daily pick into natural, confident, readable prose in a "
    "professional tipster's voice.\n\n"
    "HARD RULES:\n"
    "- NEVER overstate confidence. Your tone must track the supplied "
    "confidence level exactly. If confidence is LOW, say so plainly and frame "
    "the pick as speculative or watch-only — do not dress it up.\n"
    "- Only use facts present in the payload. Never invent prices, form, "
    "trainers, jockeys, results, or reasons. If a field is missing, omit it.\n"
    "- Respect any warnings (e.g. clustered race, below-score-floor): mention "
    "them honestly rather than glossing over them.\n"
    "- Keep every section tight — a few sentences each, no padding, no hype, "
    "no betting guarantees. This is analysis, not a sales pitch.\n"
    "- British racing idiom and spelling. Refer to the pick as the NAP.\n\n"
    "Return ONLY the requested JSON object: a punchy one-line headline, a NAP "
    "write-up, a confidence/stake note, and a short note on the alternatives."
)

# ---------------------------------------------------------------------------
# Structured output schema.
# ---------------------------------------------------------------------------
SCHEMA: dict = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "A punchy one-line headline for the day's NAP.",
        },
        "nap_writeup": {
            "type": "string",
            "description": "A few-sentence write-up of the NAP and why it stands out.",
        },
        "confidence_note": {
            "type": "string",
            "description": (
                "A plain, honest note on confidence and stake. If confidence is "
                "LOW, say so clearly."
            ),
        },
        "alternatives_note": {
            "type": "string",
            "description": "A short note on the alternative bets / watchlist.",
        },
    },
    "required": ["headline", "nap_writeup", "confidence_note", "alternatives_note"],
    "additionalProperties": False,
}


def _price_str(price: object) -> str:
    """Best-effort fractional odds string for the payload/report."""
    try:
        p = float(price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "no price"
    return format_odds(p) if p > 1.0 else "no price"


def _build_payload(data: dict, arbiter: dict | None) -> dict:
    """Assemble the compact JSON payload sent to the briefing writer.

    Summarises the NAP (confidence/stake/top reasons/warnings), the day verdict,
    and the alternative bets, plus the optional AI second opinion if present.
    """
    nap = data.get("nap") or {}

    alternatives: list[dict] = []
    for h in (data.get("watchlist") or [])[:MAX_ALTERNATIVES]:
        alternatives.append(
            {
                "horse": h.get("horse"),
                "course": h.get("course"),
                "off_time": h.get("off_time"),
                "confidence": h.get("confidence") or "",
                "price": _price_str(h.get("morning_price")),
            }
        )

    payload: dict = {
        "day_verdict": data.get("day_verdict") or "UNKNOWN",
        "nap": {
            "horse": nap.get("horse"),
            "course": nap.get("course"),
            "off_time": nap.get("off_time"),
            "score": nap.get("score"),
            "grade": nap.get("grade"),
            "confidence": nap.get("confidence") or "",
            "stake_recommendation": nap.get("stake_recommendation") or "",
            "price": _price_str(nap.get("morning_price")),
            "top_reasons": [str(r) for r in (nap.get("reasons") or [])[:MAX_REASONS]],
            "warnings": [str(w) for w in (nap.get("warnings") or [])],
            "ai_verdict": nap.get("ai_verdict") or "",
            "ai_read": nap.get("ai_read") or "",
        },
        "alternatives": alternatives,
    }

    # Optional AI second opinion — surfaced as a hint, never authoritative.
    # The arbiter file (nap_arbiter_ai.py) nests its read under "result":
    #   {ai_nap: {horse, course, off_time, reason}, agreement, agreement_note,
    #    confidence, note}. A missing/degraded arbiter yields nulls — skip then.
    if isinstance(arbiter, dict) and isinstance(arbiter.get("result"), dict):
        res = arbiter["result"]
        ai_nap = res.get("ai_nap") if isinstance(res.get("ai_nap"), dict) else {}
        agreement = res.get("agreement")
        if agreement or (ai_nap and ai_nap.get("horse")):
            payload["ai_second_opinion"] = {
                "ai_nap_horse": (ai_nap or {}).get("horse") or "",
                "ai_nap_reason": (ai_nap or {}).get("reason") or "",
                "agreement": agreement or "",
                "agreement_note": res.get("agreement_note") or "",
                "confidence": res.get("confidence"),
            }

    return payload


def _format_report(date_str: str, result: dict, model: str) -> str:
    """Render the structured result into a readable .txt briefing."""
    now = datetime.now().strftime("%H:%M")
    lines: list[str] = [
        SEP,
        "  AI MORNING BRIEFING — TIPSTER'S READ",
        f"  {date_str}  |  Generated: {now}",
        SEP,
        "",
        (result.get("headline") or "").strip(),
        "",
        "■ THE NAP",
        (result.get("nap_writeup") or "").strip(),
        "",
        "■ CONFIDENCE & STAKE",
        (result.get("confidence_note") or "").strip(),
        "",
        "■ ALTERNATIVES",
        (result.get("alternatives_note") or "").strip(),
        "",
        SEP,
        f"  AI narrative — model: {model}. Templated briefing remains authoritative.",
        SEP,
    ]
    return "\n".join(lines)


def _stub_report(date_str: str, reason: str) -> str:
    """A short stub used when the writer degrades (no LLM / no NAP)."""
    now = datetime.now().strftime("%H:%M")
    return "\n".join(
        [
            SEP,
            "  AI MORNING BRIEFING — NOT GENERATED",
            f"  {date_str}  |  Generated: {now}",
            SEP,
            "",
            f"  {reason}",
            "  The templated morning briefing remains the source of truth.",
            "",
            SEP,
        ]
    )


def _write_outputs(date_str: str, report_text: str, json_doc: dict) -> int:
    """Write both the .txt report and the .json doc. 0 on success, 1 on error."""
    txt_dest = report_path(f"ai_briefing_{date_str}.txt")
    json_dest = data_path(f"ai_briefing_{date_str}.json")

    try:
        with open(txt_dest, "w", encoding="utf-8") as fh:
            fh.write(report_text)
    except OSError as exc:
        log(f"briefing_writer_ai: failed to write {txt_dest} — {exc}", "ERROR")
        return 1

    if not safe_write_json(json_dest, json_doc):
        log(f"briefing_writer_ai: failed to write {json_dest}", "ERROR")
        return 1

    log(f"briefing_writer_ai: outputs saved to {txt_dest} and {json_dest}")
    return 0


def _write_stub(date_str: str, reason: str) -> int:
    """Write the degraded stub outputs and return its exit code (0 / 1 on write error)."""
    log(f"briefing_writer_ai: degraded — {reason}", "WARNING")
    json_doc = {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": None,
        "status": "STUB",
        "reason": reason,
        "result": None,
    }
    return _write_outputs(date_str, _stub_report(date_str, reason), json_doc)


def main() -> int:
    log("briefing_writer_ai.py started")
    date_str = today_str()

    # Degrade gracefully: no LLM client => stub + success.
    client = get_llm_client()
    if client is None:
        return _write_stub(
            date_str,
            "AI briefing writer unavailable (no API key / SDK / network).",
        )

    data = safe_load_json(data_path(f"nap_candidates_{date_str}.json"))
    if not data:
        return _write_stub(
            date_str,
            "No nap_candidates file found — nothing to write up.",
        )

    nap = data.get("nap")
    if not nap:
        day_verdict = data.get("day_verdict") or "NO BET"
        return _write_stub(
            date_str,
            f"No NAP selected today ({day_verdict}) — no write-up needed.",
        )

    # Optional AI second opinion.
    arbiter = safe_load_json(data_path(f"arbiter_{date_str}.json"))
    if arbiter is not None and not isinstance(arbiter, dict):
        arbiter = None

    payload = _build_payload(data, arbiter)

    result = client.call_structured(
        system_prompt=SYSTEM_PROMPT,
        user_payload=payload,
        schema=SCHEMA,
    )

    if not result:
        return _write_stub(
            date_str,
            "AI briefing writer returned no usable output — model unavailable "
            "or response unparseable.",
        )

    model = client.default_model
    report_text = _format_report(date_str, result, model)
    json_doc = {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "status": "OK",
        "result": result,
    }

    rc = _write_outputs(date_str, report_text, json_doc)
    if rc == 0:
        summary = (
            f"briefing_writer_ai: SUCCESS — AI briefing for "
            f"{nap.get('horse', '?')} ({date_str}) written"
        )
        log(summary)
        print(summary)
    return rc


if __name__ == "__main__":
    sys.exit(main())
