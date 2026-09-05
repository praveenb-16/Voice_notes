"""
app/extraction.py
Groq Llama action-item extraction for Voice Notes → Action Items.

Strict-fidelity mode: the LLM may ONLY emit items directly supported by
the transcript text.  An empty list is the correct output when there are
no actionable statements — fabrication is explicitly forbidden.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

# Ensure the app/ directory is on the path so sibling modules resolve
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import streamlit as st
from groq import Groq

# ── Groq client helpers ───────────────────────────────────────────────────────


def _get_client() -> Groq:
    api_key: Any = None
    try:
        api_key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        pass
    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to .env (locally) or "
            "Streamlit Secrets (deployed)."
        )
    return Groq(api_key=api_key)


def _get_model() -> str:
    model: Any = None
    try:
        model = st.secrets.get("GROQ_LLM_MODEL")
    except Exception:
        pass
    if not model:
        model = os.environ.get("GROQ_LLM_MODEL", "openai/gpt-oss-120b").strip()
    return str(model)


# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an action-item extractor operating in STRICT FIDELITY mode.

Rules:
1. Only emit an action item whose description is DIRECTLY supported by the transcript text.
2. If a segment is ambiguous, OMIT the item — do not guess.
3. If there are NO actionable statements, return an EMPTY JSON array [].
4. NEVER invent tasks that were not explicitly stated.
5. Each item must reference the exact segment timestamps (start_ms, end_ms in milliseconds).

Output format — return ONLY a valid JSON array, nothing else:
[
  {
    "description": "...",
    "assignee": "..." or null,
    "due_date": "YYYY-MM-DD" or null,
    "priority": "low" | "medium" | "high",
    "source_start_ms": <integer ms>,
    "source_end_ms": <integer ms>
  }
]

Priority inference rules (from language cues):
- "high" — urgent, ASAP, critical, immediately, by today, by EOD
- "low" — eventually, someday, when you get a chance, nice to have
- "medium" — everything else (default)
"""


def _format_segments(segments: list) -> str:
    """Format segment list for the LLM user prompt."""
    lines = []
    for seg in segments:
        start_s = seg["start_ms"] / 1000
        end_s = seg["end_ms"] / 1000
        lines.append(
            f"[{start_s:.1f}s \u2013 {end_s:.1f}s | {seg['start_ms']}ms\u2013{seg['end_ms']}ms] "
            f"{seg['text']}"
        )
    return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────


def extract_action_items(segments: list) -> list:
    """
    Extract action items from transcript *segments* using Groq Llama.

    Returns a list of dicts:
        [{description, assignee, due_date, priority, source_start_ms, source_end_ms}, ...]

    Returns an empty list when no actionable content is found.
    Raises RuntimeError on API or parse errors.
    """
    if not segments:
        return []

    client = _get_client()
    model = _get_model()
    formatted = _format_segments(segments)

    user_prompt = (
        "Here is a timestamped transcript. Extract all action items following the rules above.\n"
        "Return ONLY a JSON array.\n\n"
        f"Transcript:\n{formatted}\n"
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,  # deterministic for strict fidelity
        max_tokens=2048,
    )

    raw = (response.choices[0].message.content or "").strip()

    # Strip markdown code fences if the model wrapped the JSON
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"LLM returned invalid JSON: {exc}\nRaw output:\n{raw}"
        ) from exc

    if not isinstance(items, list):
        raise RuntimeError(f"Expected a JSON array, got: {type(items).__name__}")

    # Validate and normalise each item
    validated = []
    for item in items:
        if not isinstance(item, dict):
            continue
        desc = (item.get("description") or "").strip()
        if not desc:
            continue
        priority = item.get("priority", "medium")
        if priority not in ("low", "medium", "high"):
            priority = "medium"
        validated.append(
            {
                "description": desc,
                "assignee": item.get("assignee") or None,
                "due_date": item.get("due_date") or None,
                "priority": priority,
                "source_start_ms": int(item.get("source_start_ms", 0)),
                "source_end_ms": int(item.get("source_end_ms", 0)),
            }
        )

    return validated
