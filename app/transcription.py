"""
app/transcription.py
Groq Whisper speech-to-text transcription for Voice Notes → Action Items.

Returns a list of segment dicts: [{text, start_ms, end_ms}, ...]
"""

from __future__ import annotations

import os
import sys
from typing import Any

# Ensure the app/ directory is on the path so sibling modules resolve
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import streamlit as st
from groq import Groq


def _get_client() -> Groq:
    """Build a Groq client, preferring st.secrets over os.environ."""
    api_key: Any = None
    try:
        api_key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        pass
    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to .env (locally) or "
            "Streamlit Secrets (deployed)."
        )
    return Groq(api_key=api_key)


def _get_model() -> str:
    model: Any = None
    try:
        model = st.secrets.get("GROQ_STT_MODEL")
    except Exception:
        pass
    if not model:
        model = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo").strip()
    return str(model)


def _detect_mime(audio_bytes: bytes) -> tuple:
    """
    Detect real audio format from magic bytes.
    Returns (filename_hint, mime_type).

    st.audio_input on Chrome records WebM/Opus regardless of the .name
    attribute (which Streamlit sets to 'audio.wav'), so we always detect
    from actual byte content.
    """
    h = audio_bytes[:12] if len(audio_bytes) >= 12 else audio_bytes
    if h[:4] == b"RIFF":
        return "audio.wav", "audio/wav"
    if h[:4] == b"\x1a\x45\xdf\xa3":
        return "audio.webm", "audio/webm"
    if h[:4] == b"OggS":
        return "audio.ogg", "audio/ogg"
    if h[:4] == b"fLaC":
        return "audio.flac", "audio/flac"
    if h[:3] == b"ID3" or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio.mp3", "audio/mpeg"
    if len(h) >= 8 and h[4:8] == b"ftyp":
        return "audio.m4a", "audio/mp4"
    # Default: WebM (Chrome browser mic recording)
    return "audio.webm", "audio/webm"


def _seg_attr(seg: Any, key: str, default: Any = None) -> Any:
    """Get a field from a segment whether it's an object or a dict."""
    if isinstance(seg, dict):
        return seg.get(key, default)
    return getattr(seg, key, default)


def transcribe(audio_path: str) -> list:
    """
    Transcribe the audio file at *audio_path* using Groq Whisper.

    Returns a list of segment dicts:
        [{"text": str, "start_ms": int, "end_ms": int}, ...]

    Raises RuntimeError on API or file errors.
    Returns [] only if the audio genuinely contains no speech.
    """
    if not os.path.exists(audio_path):
        raise RuntimeError(f"Audio file not found: {audio_path}")

    file_size = os.path.getsize(audio_path)
    if file_size == 0:
        raise RuntimeError(
            "Audio file is empty (0 bytes). The recording did not save correctly."
        )

    client = _get_client()
    model = _get_model()

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    filename_hint, mime = _detect_mime(audio_bytes)

    # ── Try verbose_json for segment timestamps ────────────────────────────
    try:
        response = client.audio.transcriptions.create(
            file=(filename_hint, audio_bytes, mime),
            model=model,
            response_format="verbose_json",
            language="en",         # explicit language hint speeds up transcription
        )

        raw_segments = getattr(response, "segments", None)

        if raw_segments:
            segments = []
            for seg in raw_segments:
                start_ms = int(float(_seg_attr(seg, "start", 0)) * 1000)
                end_ms   = int(float(_seg_attr(seg, "end",   0)) * 1000)
                text     = (_seg_attr(seg, "text", "") or "").strip()
                if text:
                    segments.append({"text": text, "start_ms": start_ms, "end_ms": end_ms})
            if segments:
                return segments

        # Fallback: use top-level text if segments are empty
        full_text = (getattr(response, "text", "") or "").strip()
        if full_text:
            return [{"text": full_text, "start_ms": 0, "end_ms": 0}]

    except Exception as e:
        # verbose_json failed — fall through to plain json fallback
        err_str = str(e)
        # Re-raise auth errors immediately (bad API key, rate limit etc.)
        if any(kw in err_str.lower() for kw in ("auth", "401", "403", "rate", "429")):
            raise RuntimeError(f"Groq API error: {e}") from e

    # ── Fallback: plain json (no timestamps, single segment) ───────────────
    try:
        response2 = client.audio.transcriptions.create(
            file=(filename_hint, audio_bytes, mime),
            model=model,
            response_format="json",
            language="en",
        )
        text2 = (getattr(response2, "text", "") or "").strip()
        if text2:
            return [{"text": text2, "start_ms": 0, "end_ms": 0}]
    except Exception as e2:
        raise RuntimeError(f"Groq transcription failed: {e2}") from e2

    # Nothing worked — audio has no detectable speech
    return []
