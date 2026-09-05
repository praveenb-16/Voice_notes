"""
app/main.py
Entry point for Voice Notes → Action Items.

Run locally:  streamlit run app/main.py
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

import streamlit as st
from dotenv import load_dotenv

# ── Path setup so sibling modules import correctly ─────────────────────────────
_APP_DIR = os.path.dirname(__file__)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

load_dotenv(os.path.join(_APP_DIR, "..", ".env"))

import auth
import extraction
import storage
import transcription

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Voice Notes → Action Items",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS injection ─────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Pill-shaped primary buttons */
    .stButton > button {
        border-radius: 999px !important;
        border: none !important;
        padding: 0.5rem 1.5rem !important;
        font-weight: 500 !important;
        transition: box-shadow 0.2s ease, transform 0.1s ease !important;
    }
    .stButton > button:hover {
        box-shadow: 0 2px 8px rgba(26, 115, 232, 0.4) !important;
        transform: translateY(-1px) !important;
    }
    .stButton > button:active {
        transform: translateY(0) !important;
    }

    /* Card-style containers */
    div[data-testid="stContainer"] {
        background: #FFFFFF;
        border-radius: 12px;
        box-shadow: 0 1px 2px rgba(60,64,67,.30), 0 1px 3px 1px rgba(60,64,67,.15);
        padding: 1.5rem;
        margin-bottom: 1rem;
        transition: box-shadow 0.2s ease;
    }
    div[data-testid="stContainer"]:hover {
        box-shadow: 0 2px 6px rgba(60,64,67,.30), 0 2px 8px 2px rgba(60,64,67,.15);
    }

    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: #F8F9FA;
        border-right: 1px solid #E8EAED;
    }

    /* Status badge helpers */
    .badge-ready    { color: #1E8E3E; background: #E6F4EA; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .badge-failed   { color: #C5221F; background: #FCE8E6; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .badge-progress { color: #B45309; background: #FEF3C7; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .badge-uploaded { color: #1A73E8; background: #E8F0FE; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }

    /* Priority dots */
    .dot-high   { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #C5221F; margin-right: 6px; }
    .dot-medium { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #B45309; margin-right: 6px; }
    .dot-low    { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #80868B; margin-right: 6px; }

    /* Highlighted transcript segment */
    .seg-highlight {
        background: #FFF3E0;
        border-left: 4px solid #1A73E8;
        padding: 4px 8px;
        border-radius: 4px;
        margin: 2px 0;
    }
    .seg-normal {
        padding: 4px 8px;
        margin: 2px 0;
        border-radius: 4px;
    }
    .seg-ts {
        font-size: 0.72rem;
        color: #80868B;
        font-weight: 500;
        margin-right: 6px;
        cursor: pointer;
    }

    /* Hero section */
    .hero-title {
        font-size: 2rem;
        font-weight: 700;
        color: #202124;
        letter-spacing: -0.5px;
    }
    .hero-sub {
        color: #5F6368;
        font-size: 1.05rem;
        margin-top: 0.25rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Helper utilities ──────────────────────────────────────────────────────────


def _fmt_duration(secs: float | None) -> str:
    if secs is None:
        return "—"
    m, s = divmod(int(secs), 60)
    return f"{m}:{s:02d}"


def _fmt_ms(ms: int) -> str:
    total_s = ms // 1000
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}"


def _relative_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        delta = datetime.now(dt.tzinfo) - dt
        if delta.days == 0:
            return "Today"
        elif delta.days == 1:
            return "Yesterday"
        elif delta.days < 7:
            return f"{delta.days} days ago"
        else:
            return dt.strftime("%b %d, %Y")
    except Exception:
        return iso


def _status_badge(status: str) -> str:
    if status == "ready":
        return '<span class="badge-ready">✓ Ready</span>'
    elif status == "failed":
        return '<span class="badge-failed">✗ Failed</span>'
    elif status in ("transcribing", "extracting"):
        return f'<span class="badge-progress">⏳ {status.capitalize()}</span>'
    else:
        return '<span class="badge-uploaded">↑ Uploaded</span>'


def _priority_dot(priority: str) -> str:
    cls = f"dot-{priority}" if priority in ("high", "medium", "low") else "dot-low"
    return f'<span class="{cls}"></span>'


def _priority_label(p: str) -> str:
    return {"high": "🔴 High", "medium": "🟡 Medium", "low": "⚪ Low"}.get(p, p)


# ── Section: Login / Signup ───────────────────────────────────────────────────


def render_auth() -> None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            '<p class="hero-title">🎙️ Voice Notes</p>'
            '<p class="hero-sub">Turn spoken notes into trackable action items.</p>',
            unsafe_allow_html=True,
        )
        st.divider()
        tab_login, tab_signup = st.tabs(["Sign in", "Create account"])
        with tab_login:
            auth.login_form()
        with tab_signup:
            auth.signup_form()


# ── Section: Record ───────────────────────────────────────────────────────────


def render_record() -> None:
    user = st.session_state["user"]

    st.markdown('<p class="hero-title">🎙️ New Voice Note</p>', unsafe_allow_html=True)
    st.caption("Record using your microphone or upload an existing audio file.")
    st.divider()

    with st.container(border=True):
        title = st.text_input(
            "Note title",
            placeholder="e.g. Weekly standup – 5 Sep",
            help="Give this recording a short, descriptive name.",
        )

        st.markdown("**Record from microphone**")
        mic_audio = st.audio_input("Click the mic to start recording")

        st.markdown("— or —")
        st.markdown("**Upload an audio file**")
        uploaded_file = st.file_uploader(
            "Upload audio",
            type=["wav", "mp3", "m4a", "ogg", "flac", "webm"],
            label_visibility="collapsed",
        )

        submit = st.button("✨ Transcribe & Extract", use_container_width=True, type="primary")

    if submit:
        if not title.strip():
            st.error("Please enter a note title.")
            return
        audio_data = mic_audio or uploaded_file
        if audio_data is None:
            st.error("Please record or upload an audio file.")
            return
        _run_pipeline(user["id"], title.strip(), audio_data)


def _detect_audio_format(audio_bytes: bytes) -> tuple:

    """
    Detect the real audio format from magic bytes.
    Returns (ext, mime_type) — ignores whatever the filename says.

    st.audio_input on Chrome records WebM/Opus regardless of the .name
    attribute that Streamlit sets to 'audio.wav', so we must detect from
    the actual byte content.
    """
    if len(audio_bytes) < 12:
        return ".webm", "audio/webm"
    h = audio_bytes[:12]
    if h[:4] == b"RIFF":
        return ".wav", "audio/wav"
    # WebM / Matroska EBML header
    if h[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm", "audio/webm"
    # OGG container
    if h[:4] == b"OggS":
        return ".ogg", "audio/ogg"
    # FLAC
    if h[:4] == b"fLaC":
        return ".flac", "audio/flac"
    # MP3 – ID3 tag or sync word
    if h[:3] == b"ID3" or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3", "audio/mpeg"
    # M4A / MP4 — 'ftyp' at offset 4
    if h[4:8] == b"ftyp":
        return ".m4a", "audio/mp4"
    # Default: assume WebM (Chrome browser mic recording)
    return ".webm", "audio/webm"


def _run_pipeline(user_id: int, title: str, audio_data: Any) -> None:
    """Save audio → transcribe → extract → store, with spinners."""
    audio_dir = storage.audio_dir()

    # ── Read audio bytes safely ────────────────────────────────────────────
    # st.audio_input / st.file_uploader both return BytesIO-like objects.
    # getvalue() is safest: returns the full buffer regardless of cursor pos.
    if hasattr(audio_data, "getvalue"):
        audio_bytes = audio_data.getvalue()
    elif hasattr(audio_data, "read"):
        try:
            audio_data.seek(0)
        except Exception:
            pass
        audio_bytes = audio_data.read()
    else:
        audio_bytes = bytes(audio_data)

    if not audio_bytes:
        st.error(
            "The recorded audio appears to be empty. "
            "Please record again or upload a different file."
        )
        return

    # ── Detect actual audio format from magic bytes ────────────────────────
    # st.audio_input names the file 'audio.wav' but Chrome records WebM/Opus.
    # We detect the real format so Groq receives the correct MIME type.
    ext, _mime = _detect_audio_format(audio_bytes)

    filename = f"{uuid.uuid4().hex}{ext}"
    audio_abs = os.path.join(audio_dir, filename)
    audio_rel = os.path.join("audio", filename)  # relative to data/

    # Save to disk with the correct extension
    with open(audio_abs, "wb") as f:
        f.write(audio_bytes)

    # Create DB row
    note_id = storage.create_note(user_id, title, audio_rel, duration=None)



    try:
        # ── Step 1: Transcribe ─────────────────────────────────────────────
        with st.spinner("🎧 Transcribing your audio… (this may take ~10s)"):
            storage.update_note_status(note_id, "transcribing")
            try:
                segments = transcription.transcribe(audio_abs)
            except Exception as transcribe_exc:
                storage.update_note_status(note_id, "failed")
                st.error(f"Transcription error: {transcribe_exc}")
                return

        if not segments:
            storage.update_note_status(note_id, "failed")
            st.error(
                "Groq returned no text for this audio. "
                f"File saved as `{os.path.basename(audio_abs)}` "
                f"({os.path.getsize(audio_abs):,} bytes). "
                "This usually means the audio is silent or in an unsupported format."
            )
            return


        storage.save_transcript(note_id, segments)
        storage.update_note_status(note_id, "extracting")

        # ── Step 2: Extract ────────────────────────────────────────────────
        with st.spinner("🤖 Finding action items…"):
            items = extraction.extract_action_items(segments)

        if items:
            storage.insert_action_items(note_id, user_id, items)

        storage.update_note_status(note_id, "ready")

        # Success feedback
        if items:
            st.success(
                f"✅ Done! Found **{len(items)} action item{'s' if len(items) != 1 else ''}**. "
                "Opening your note…"
            )
        else:
            st.info("✅ Transcription complete. No action items were found in this recording.")

        # Navigate to note detail
        st.session_state["active_note_id"] = note_id
        st.session_state["nav"] = "📄 Note Detail"
        st.rerun()

    except Exception as exc:
        storage.update_note_status(note_id, "failed")
        st.error(f"Pipeline error: {exc}")


# ── Section: Notes library ────────────────────────────────────────────────────


def render_notes() -> None:
    user = st.session_state["user"]
    notes = storage.list_notes(user["id"])

    st.markdown('<p class="hero-title">📋 My Notes</p>', unsafe_allow_html=True)
    st.caption(f"{len(notes)} recording{'s' if len(notes) != 1 else ''}")
    st.divider()

    if not notes:
        st.info("No notes yet. Head to **🎙️ Record** to create your first one!")
        return

    for note in notes:
        with st.container(border=True):
            col_info, col_actions = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"**{note['title']}** &nbsp; {_status_badge(note['status'])}",
                    unsafe_allow_html=True,
                )
                task_count = note.get("open_task_count", 0)
                task_label = (
                    f"🔲 {task_count} open task{'s' if task_count != 1 else ''}"
                    if task_count
                    else "✅ No open tasks"
                )
                st.caption(
                    f"⏱ {_fmt_duration(note.get('duration_seconds'))}  ·  "
                    f"🗓 {_relative_date(note['created_at'])}  ·  {task_label}"
                )
            with col_actions:
                if st.button("Open", key=f"open_{note['id']}", use_container_width=True):
                    st.session_state["active_note_id"] = note["id"]
                    st.session_state["nav"] = "📄 Note Detail"
                    st.rerun()
                if st.button("🗑", key=f"del_{note['id']}", help="Delete this note"):
                    storage.delete_note(note["id"], user["id"])
                    st.success("Note deleted.")
                    st.rerun()


# ── Section: Note detail ──────────────────────────────────────────────────────


def render_note_detail() -> None:
    user = st.session_state["user"]
    note_id = st.session_state.get("active_note_id")

    if not note_id:
        st.info("Select a note from **📋 Notes** first.")
        return

    note = storage.get_note(note_id, user["id"])
    if not note:
        st.error("Note not found.")
        return

    # ── Header ─────────────────────────────────────────────────────────────
    col_title, col_back = st.columns([5, 1])
    with col_title:
        st.markdown(
            f'<p class="hero-title">📄 {note["title"]}</p>',
            unsafe_allow_html=True,
        )
        st.markdown(_status_badge(note["status"]), unsafe_allow_html=True)
    with col_back:
        if st.button("← Notes", use_container_width=True):
            st.session_state["nav"] = "📋 Notes"
            st.rerun()

    st.divider()

    # ── Audio player ────────────────────────────────────────────────────────
    audio_abs = os.path.join(
        os.path.dirname(__file__), "..", "data", note["audio_path"]
    )
    if os.path.exists(audio_abs):
        with st.container(border=True):
            st.markdown("**🎧 Playback**")
            st.audio(audio_abs)
    else:
        st.warning("Audio file not found on disk.")

    # ── Transcript ──────────────────────────────────────────────────────────
    segments = []
    if note.get("transcript_json"):
        try:
            segments = json.loads(note["transcript_json"])
        except Exception:
            pass

    # Active (highlighted) segment from clicking a timestamp
    highlighted_ms = st.session_state.get(f"highlight_ms_{note_id}", -1)

    if segments:
        with st.container(border=True):
            st.markdown("**📝 Transcript**")
            for seg in segments:
                ts_label = _fmt_ms(seg["start_ms"])
                is_hl = (highlighted_ms != -1 and
                         seg["start_ms"] <= highlighted_ms <= seg["end_ms"])
                css_class = "seg-highlight" if is_hl else "seg-normal"
                st.markdown(
                    f'<div class="{css_class}">'
                    f'<span class="seg-ts">[{ts_label}]</span>{seg["text"]}'
                    f"</div>",
                    unsafe_allow_html=True,
                )
    elif note["status"] == "ready":
        with st.container(border=True):
            st.info("No transcript available for this note.")

    # ── Action-item checklist ───────────────────────────────────────────────
    items = storage.list_action_items(user["id"], note_id=note_id)

    with st.container(border=True):
        st.markdown("**✅ Action Items**")

        if not items:
            if note["status"] == "ready":
                st.info("No action items were found in this recording.")
            else:
                st.info(f"Status: **{note['status']}** — check back after transcription.")
        else:
            for item in items:
                col_check, col_desc, col_ts, col_edit = st.columns([1, 6, 2, 1])

                # Done checkbox
                with col_check:
                    done = item["status"] == "done"
                    toggled = st.checkbox(
                        "done",
                        value=done,
                        key=f"chk_{item['id']}",
                        label_visibility="collapsed",
                    )
                    if toggled != done:
                        storage.update_action_item(
                            item["id"],
                            user["id"],
                            status="done" if toggled else "open",
                        )
                        st.rerun()

                # Description + priority dot
                with col_desc:
                    desc_style = "text-decoration: line-through; color: #80868B;" if item["status"] == "done" else ""
                    st.markdown(
                        f'<div style="{desc_style}">'
                        f'{_priority_dot(item["priority"])}'
                        f"{item['description']}"
                        + (f"<br><small>👤 {item['assignee']}</small>" if item.get("assignee") else "")
                        + (f"<br><small>📅 {item['due_date']}</small>" if item.get("due_date") else "")
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                # Timestamp jump button
                with col_ts:
                    ts_str = f"{_fmt_ms(item['source_start_ms'])} – {_fmt_ms(item['source_end_ms'])}"
                    if st.button(ts_str, key=f"ts_{item['id']}", help="Jump to this moment"):
                        st.session_state[f"highlight_ms_{note_id}"] = item["source_start_ms"]
                        st.rerun()

                # Edit popover
                with col_edit:
                    with st.popover("✏️", help="Edit this action item"):
                        with st.form(f"edit_{item['id']}"):
                            new_desc = st.text_area("Description", value=item["description"])
                            new_assignee = st.text_input("Assignee", value=item.get("assignee") or "")
                            new_due = st.text_input(
                                "Due date (YYYY-MM-DD)", value=item.get("due_date") or ""
                            )
                            new_priority = st.selectbox(
                                "Priority",
                                ["low", "medium", "high"],
                                index=["low", "medium", "high"].index(item.get("priority", "medium")),
                            )
                            save = st.form_submit_button("Save", use_container_width=True)
                            if save:
                                storage.update_action_item(
                                    item["id"],
                                    user["id"],
                                    description=new_desc.strip(),
                                    assignee=new_assignee.strip() or None,
                                    due_date=new_due.strip() or None,
                                    priority=new_priority,
                                )
                                st.success("Saved!")
                                st.rerun()

                st.divider()


# ── Section: Tasks (cross-note) ───────────────────────────────────────────────


def render_tasks() -> None:
    user = st.session_state["user"]

    st.markdown('<p class="hero-title">✅ All Tasks</p>', unsafe_allow_html=True)
    st.caption("Every action item across all your notes.")
    st.divider()

    # Filters
    col_p, col_s = st.columns(2)
    with col_p:
        priority_filter = st.multiselect(
            "Filter by priority",
            options=["high", "medium", "low"],
            default=[],
            format_func=_priority_label,
        )
    with col_s:
        status_filter = st.selectbox(
            "Filter by status",
            options=["all", "open", "done"],
            index=0,
        )

    status_arg = None if status_filter == "all" else status_filter
    all_items = storage.list_action_items(user["id"], status=status_arg)

    if priority_filter:
        all_items = [i for i in all_items if i["priority"] in priority_filter]

    if not all_items:
        st.info("No tasks match the current filters.")
        return

    st.caption(f"{len(all_items)} task{'s' if len(all_items) != 1 else ''} found")

    # Group by due_date (None → "No due date")
    groups: Any = defaultdict(list)
    for item in all_items:
        key = item.get("due_date") or "No due date"
        groups[key].append(item)

    # Sort: real dates first, then "No due date"
    sorted_keys = sorted(
        groups.keys(),
        key=lambda k: (k == "No due date", k),
    )

    for group_key in sorted_keys:
        st.markdown(f"### 📅 {group_key}")
        for item in groups[group_key]:
            with st.container(border=True):
                col_chk, col_info, col_note, col_pri = st.columns([1, 5, 3, 1])

                with col_chk:
                    done = item["status"] == "done"
                    toggled = st.checkbox(
                        "done",
                        value=done,
                        key=f"task_chk_{item['id']}",
                        label_visibility="collapsed",
                    )
                    if toggled != done:
                        storage.update_action_item(
                            item["id"],
                            user["id"],
                            status="done" if toggled else "open",
                        )
                        st.rerun()

                with col_info:
                    desc_style = "text-decoration: line-through; color: #80868B;" if item["status"] == "done" else ""
                    st.markdown(
                        f'<div style="{desc_style}">{item["description"]}</div>'
                        + (f"<br><small>👤 {item['assignee']}</small>" if item.get("assignee") else ""),
                        unsafe_allow_html=True,
                    )

                with col_note:
                    note_title = item.get("note_title", "Unknown note")
                    if st.button(
                        f"📄 {note_title[:28]}{'…' if len(note_title) > 28 else ''}",
                        key=f"goto_{item['id']}",
                        help="Open this note",
                    ):
                        st.session_state["active_note_id"] = item["note_id"]
                        st.session_state["nav"] = "📄 Note Detail"
                        st.rerun()

                with col_pri:
                    st.markdown(
                        _priority_dot(item["priority"]),
                        unsafe_allow_html=True,
                    )


# ── Sidebar navigation ────────────────────────────────────────────────────────


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown("## 🎙️ Voice Notes")
        st.divider()

        if "user" in st.session_state:
            user = st.session_state["user"]
            st.markdown(f"👤 **{user['name']}**")
            st.caption(user["email"])
            st.divider()

            nav_options = ["🎙️ Record", "📋 Notes", "📄 Note Detail", "✅ Tasks"]
            default_nav = st.session_state.get("nav", "🎙️ Record")
            default_idx = nav_options.index(default_nav) if default_nav in nav_options else 0

            selected = st.radio(
                "Navigate",
                nav_options,
                index=default_idx,
                label_visibility="collapsed",
            )

            st.divider()
            if st.button("Sign out", use_container_width=True):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

            return selected
        else:
            return "Login / Signup"


# ── Main entry ────────────────────────────────────────────────────────────────


def main() -> None:
    section = render_sidebar()

    # Store nav selection in session state for cross-section redirects
    if "nav" not in st.session_state:
        st.session_state["nav"] = section
    elif section != st.session_state.get("nav"):
        # User clicked sidebar — update nav
        st.session_state["nav"] = section

    current = st.session_state.get("nav", section)

    if "user" not in st.session_state:
        render_auth()
        return

    if current == "🎙️ Record":
        render_record()
    elif current == "📋 Notes":
        render_notes()
    elif current == "📄 Note Detail":
        render_note_detail()
    elif current == "✅ Tasks":
        render_tasks()
    else:
        render_auth()


if __name__ == "__main__":
    main()
