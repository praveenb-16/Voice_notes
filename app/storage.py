"""
app/storage.py
SQLite database layer for Voice Notes → Action Items.

All read/write functions require a user_id and filter by it so no user
can ever touch another user's data.  PRAGMA foreign_keys is enabled on
every connection; ON DELETE CASCADE in action_items.note_id handles
cascading deletes at the DB level.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

# ── Path helpers ──────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_HERE, "..", "data")
_DB_PATH = os.path.join(_DATA_DIR, "notes.db")
_AUDIO_DIR = os.path.join(_DATA_DIR, "audio")


def _ensure_dirs() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    os.makedirs(_AUDIO_DIR, exist_ok=True)


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id),
    title             TEXT NOT NULL,
    audio_path        TEXT NOT NULL,
    duration_seconds  REAL,
    status            TEXT NOT NULL DEFAULT 'uploaded',
    transcript_json   TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id          INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    user_id          INTEGER NOT NULL REFERENCES users(id),
    description      TEXT NOT NULL,
    assignee         TEXT,
    due_date         TEXT,
    priority         TEXT NOT NULL DEFAULT 'medium',
    status           TEXT NOT NULL DEFAULT 'open',
    source_start_ms  INTEGER NOT NULL,
    source_end_ms    INTEGER NOT NULL,
    inferred         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
"""


# ── Connection ────────────────────────────────────────────────────────────────


def get_connection() -> sqlite3.Connection:
    """Return a sqlite3 connection with foreign keys enabled and row factory set."""
    _ensure_dirs()
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Users ─────────────────────────────────────────────────────────────────────


def create_user(name: str, email: str, password_hash: str) -> int:
    """Insert a new user and return the new user_id.  Raises on duplicate email."""
    conn = get_connection()
    with conn:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?,?,?,?)",
            (name, email, password_hash, _now()),
        )
    return cur.lastrowid  # type: ignore[return-value]


def verify_user(email: str) -> Optional[dict]:
    """Return the user row for *email*, or None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, name, email, password_hash FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    return dict(row) if row else None


# ── Notes ─────────────────────────────────────────────────────────────────────


def create_note(
    user_id: int,
    title: str,
    audio_path: str,
    duration: Optional[float],
) -> int:
    """Insert a Note row and return the new note_id."""
    now = _now()
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """INSERT INTO notes
               (user_id, title, audio_path, duration_seconds, status, created_at, updated_at)
               VALUES (?,?,?,?,'uploaded',?,?)""",
            (user_id, title, audio_path, duration, now, now),
        )
    return cur.lastrowid  # type: ignore[return-value]


def update_note_status(note_id: int, status: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE notes SET status=?, updated_at=? WHERE id=?",
            (status, _now(), note_id),
        )


def save_transcript(note_id: int, segments: list) -> None:
    """Persist transcript segments as JSON on the note row."""
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE notes SET transcript_json=?, updated_at=? WHERE id=?",
            (json.dumps(segments), _now(), note_id),
        )


def list_notes(user_id: int) -> list:
    """Return all notes for *user_id*, newest first, with open-task count."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT n.*, COUNT(a.id) AS open_task_count
        FROM notes n
        LEFT JOIN action_items a ON a.note_id = n.id AND a.status = 'open'
        WHERE n.user_id = ?
        GROUP BY n.id
        ORDER BY n.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_note(note_id: int, user_id: int) -> Optional[dict]:
    """Return a single note that belongs to *user_id*, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM notes WHERE id=? AND user_id=?",
        (note_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def delete_note(note_id: int, user_id: int) -> None:
    """Delete the note (cascades to action_items) and remove the audio file."""
    note = get_note(note_id, user_id)
    if note is None:
        return
    # Remove audio file
    audio_abs = os.path.join(_DATA_DIR, note["audio_path"])
    if os.path.exists(audio_abs):
        os.remove(audio_abs)
    # Delete row (cascade removes action_items)
    conn = get_connection()
    with conn:
        conn.execute(
            "DELETE FROM notes WHERE id=? AND user_id=?",
            (note_id, user_id),
        )


# ── Action items ──────────────────────────────────────────────────────────────


def insert_action_items(note_id: int, user_id: int, items: list) -> None:
    """Bulk-insert extracted action items for a note."""
    now = _now()
    conn = get_connection()
    with conn:
        conn.executemany(
            """INSERT INTO action_items
               (note_id, user_id, description, assignee, due_date, priority,
                status, source_start_ms, source_end_ms, inferred, created_at, updated_at)
               VALUES (?,?,?,?,?,?,  'open',?,?,0,?,?)""",
            [
                (
                    note_id,
                    user_id,
                    it["description"],
                    it.get("assignee"),
                    it.get("due_date"),
                    it.get("priority", "medium"),
                    it["source_start_ms"],
                    it["source_end_ms"],
                    now,
                    now,
                )
                for it in items
            ],
        )


def list_action_items(
    user_id: int,
    status: Optional[str] = None,
    note_id: Optional[int] = None,
) -> list:
    """Return action items for *user_id*, optionally filtered by status and/or note."""
    query = (
        "SELECT a.*, n.title AS note_title "
        "FROM action_items a JOIN notes n ON n.id = a.note_id "
        "WHERE a.user_id=?"
    )
    params: list = [user_id]
    if status:
        query += " AND a.status=?"
        params.append(status)
    if note_id is not None:
        query += " AND a.note_id=?"
        params.append(note_id)
    query += " ORDER BY a.created_at ASC"
    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_action_item(item_id: int, user_id: int, **fields: object) -> None:
    """Update any subset of editable fields on an action item owned by *user_id*."""
    allowed = {"description", "assignee", "due_date", "priority", "status"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [item_id, user_id]
    conn = get_connection()
    with conn:
        conn.execute(
            f"UPDATE action_items SET {set_clause} WHERE id=? AND user_id=?",
            values,
        )


def audio_dir() -> str:
    """Return the absolute path to the audio storage directory."""
    _ensure_dirs()
    return os.path.abspath(_AUDIO_DIR)
