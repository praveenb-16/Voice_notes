# Voice Notes → Action Items — Build Specification

`Voice Notes → Action Items` turns a spoken voice note into a transcript and a checklist of
concrete, trackable action items, each traceable back to the exact moment in the recording it
came from.

**How to use this document:** this file is self-contained. It defines what the system means
semantically, exactly what to build, which technologies to use, the data model, and the visual
design system. A coding agent should be able to implement the entire application from this file
alone, end to end, without further clarification.

**This build matches a single-repo, single-app layout** — `app/`, `data/`, `.env`, `README.md`,
`requirements.txt`, no `package.json` — which means one Python app, not a separate frontend and
backend. **Streamlit** is the decisive choice: it's the framework this exact folder shape is
almost always built with, it gives you a browser mic-recording widget and a file uploader for
free, and it deploys straight from GitHub with no separate hosting account to juggle.

You can use `Voice Notes → Action Items` to:

- record or upload a spoken note and get back a transcript plus a list of tasks mentioned in it.
- jump straight to the moment in the audio where a given task was mentioned.
- track those tasks to completion, with an assignee, a due date, and a priority.

You can't use `Voice Notes → Action Items` to:

- guarantee every task a speaker intended gets captured. Extraction is only as good as what was
  said clearly enough for the speech-to-text model to transcribe and the LLM to recognize as
  actionable.
- invent tasks that weren't actually said, to make a recording look more "useful" than it was. A
  note with no actionable content should produce an empty checklist, not a fabricated one (see
  Extraction).
- replace a real project-management tool for teams. This spec is a single-owner capture tool by
  default; shared, multi-assignee workflows are Phase 2.

## Zero-cost, same-day build plan

Every piece here is free with **no credit card**: Groq (speech-to-text *and* the extraction LLM,
one account), a local SQLite file for the database, and Streamlit Community Cloud for hosting —
which deploys directly from the public GitHub repo shown in your screenshot. There's no Vercel,
no Render, no MongoDB Atlas to sign up for.

One thing to know going in: Streamlit Community Cloud apps sleep after about 12 hours with no
traffic and take a few seconds to wake — much more forgiving than most free hosts, but visit the
app once before a demo just in case.

### Step 0 — set up (~5 min)

1. You already have the GitHub repo (per the screenshot).
2. [Groq console](https://console.groq.com/keys) — sign up, generate an API key. This one key
   covers both transcription and extraction.
3. [share.streamlit.io](https://share.streamlit.io) — sign in with GitHub. You'll point it at
   your repo once the app is written.

### Suggested order, time-boxed (~5–6 focused hours)

1. **Repo skeleton + SQLite schema** (30 min) — create the folders below, write
   `app/storage.py` with the schema and connection helper.
2. **Auth** (45–60 min) — `app/auth.py`: signup/login forms with `bcrypt`-hashed passwords in
   the `users` table, session state to track the logged-in user.
3. **Record → transcribe** (45–60 min) — `st.audio_input` (mic) and `st.file_uploader` (existing
   file), save to `data/audio/`, call Groq's Whisper endpoint for a timestamped transcript.
4. **Extract** (45 min) — call Groq's LLM endpoint with a Strict-fidelity prompt, insert the
   resulting action items.
5. **Note library + note detail views** (90 min) — list past notes, and per-note: audio player,
   transcript, checklist with a mark-done toggle.
6. **Theme pass** (20–30 min) — `.streamlit/config.toml` + a small CSS injection for the light,
   Google Material look (see UI design system below).
7. **Deploy** (15–20 min) — push to GitHub, "New app" on Streamlit Community Cloud pointing at
   `app/main.py`, add `GROQ_API_KEY` under the app's **Secrets**.
8. **Buffer + demo prep** (15 min) — open the deployed URL once before you present.

**If you're behind schedule, cut in this order** before touching steps 1–4 above: drop the
cross-note "Tasks" view first (each note's own checklist still works), then drop manual
task-adding and full field editing (leave only the "mark done" toggle), then hardcode every
extracted item's priority to `medium` instead of asking the LLM to infer it.

## Feature scope

### Core (must ship)

- Record audio in the browser, or upload an existing audio file.
- Speech-to-text transcription of the recording, with timestamps.
- LLM extraction of action items from the transcript — description, optional assignee, optional
  due date, priority.
- Every action item traceable back to the transcript segment that supports it.
- Explicit "no action items found" handling instead of fabricating tasks.
- A note library: list past recordings with their transcript, status, and open-task count.
- An action-item checklist per note: mark complete, edit, delete.
- A cross-note task view: every open action item across all notes, filterable.
- Account authentication (single-user accounts).
- A deployed, working application.

### Phase 2 (defined but optional)

Multi-speaker diarization, shared notes with multiple assignees, calendar/task-manager export,
due-date reminders, manual transcript editing with re-extraction, multilingual transcription,
note tagging, an "inferred vs. stated" Permissive extraction mode, live transcription while
recording, and a daily digest email. None of these change the semantics below; they layer on top
of the Pipeline.

## Definitions

More fundamental concepts are introduced before those that build on them.

### Voice note

An audio recording, captured in-browser or uploaded, that is the raw input to the system.

----

A voice note carries metadata: duration, upload date, and an optional title. A voice note that
hasn't finished transcription has no transcript and no action items yet.

### Transcript

The text produced by converting a voice note's audio into written words via a speech-to-text
model.

#### Segment

A time-bounded span of the transcript — typically a sentence or phrase — with a start and end
timestamp.

----

Segments are the unit an action item points back to (see Source span). A transcript is stored as
an ordered list of segments, not one flat string, precisely so later steps can cite a specific
moment rather than the whole recording.

### Action item

A single, discrete task extracted from a transcript.

----

An action item has a description, an optional assignee, an optional due date, a priority, and a
status (`open` or `done`). Two action items are distinct if they describe different tasks, even
when extracted from the same sentence.

#### Extraction

The process by which an LLM reads a transcript and produces a set of action items from it.

----

Extraction must not invent an action item unsupported by the transcript. A transcript with no
actionable statements must produce zero action items, not a fabricated one.

#### Source span

The segment(s) of the transcript that support a given action item, referenced by timestamp
range.

----

Given the action item "Send the report by Friday" extracted from the segment spanning
`00:42`–`00:48`, its source span is `00:42–00:48`. An action item with no traceable source span
should not be produced at all.

### Priority

A system- or user-assigned urgency level: `low`, `medium`, or `high`. Inferred from language
cues, or defaulted to `medium` and edited manually — always editable regardless of how it was set.

### Note session

One voice note together with its transcript and the action items extracted from it. Referred to
in the data model simply as a **Note**.

### Account

An authenticated identity that owns notes and the action items extracted from them. The Core
build has a single role: every account can record, transcribe, and manage only its own notes.

## Extraction fidelity

- **Strict** (default) — the LLM may only emit an action item whose description and source span
  are directly supported by transcript text. When a segment is ambiguous, omitting the action
  item is correct; guessing is not.
- **Permissive** (Phase 2, opt-in per note) — the LLM may surface likely follow-ups that weren't
  stated outright, but every such item must be flagged `inferred: true`.

## System architecture

```
┌────────────┐        ┌───────────────────────────────┐        ┌───────────────┐
│   Browser   │◄─────►│   Streamlit Community Cloud     │◄──────►│    Groq API    │
│ (mic input, │  HTTPS │   running app/main.py           │  REST  │ Whisper (STT)  │
│  uploads)   │        │                                  │        │ + Llama (LLM)  │
└────────────┘        │  ┌────────────────────────────┐  │        └───────────────┘
                       │  │ data/notes.db (SQLite)      │  │
                       │  │ data/audio/*.wav            │  │
                       │  └────────────────────────────┘  │
                       └───────────────────────────────┘
```

Everything except the Groq calls runs inside one Python process. There is no separate backend
API and no separate database server — `data/` on Streamlit Cloud's own filesystem is the
database. **Caveat:** that filesystem is not guaranteed to survive a redeploy or a long sleep —
fine for a same-day build and demo; if you need data to persist indefinitely later, swap
`app/storage.py` to call MongoDB Atlas's free tier instead. Nothing else in this spec would need
to change.

## Tech stack (decisive)

| Layer | Choice | Free tier |
|---|---|---|
| App framework | Streamlit (Python) | — |
| Audio input | `st.audio_input` (browser mic) + `st.file_uploader` (existing file) | Built in |
| Speech-to-text | **Groq API**, `whisper-large-v3-turbo`, `response_format="verbose_json"` for segment timestamps | Free, no card, 2,000 requests/day |
| Extraction LLM | **Groq API**, `llama-3.3-70b-versatile` | Free, no card, 14,400 requests/day |
| Database | SQLite (`data/notes.db`), via Python's built-in `sqlite3` | Free, local file, zero setup |
| Audio storage | Local files under `data/audio/` | Free, local |
| Auth | Hand-rolled: `bcrypt` password hashing + a `users` table + `st.session_state` | Free |
| Hosting | Streamlit Community Cloud, deployed from the GitHub repo | Free, no card |
| Source control | GitHub | Free |

## Data model (SQLite)

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at    TEXT NOT NULL
);

CREATE TABLE notes (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id           INTEGER NOT NULL REFERENCES users(id),
  title             TEXT NOT NULL,
  audio_path        TEXT NOT NULL,   -- relative path under data/audio/
  duration_seconds  REAL,
  status            TEXT NOT NULL DEFAULT 'uploaded',
                    -- uploaded | transcribing | extracting | ready | failed
  transcript_json   TEXT,             -- JSON list of {text, start_ms, end_ms}
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE TABLE action_items (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  note_id          INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  user_id          INTEGER NOT NULL REFERENCES users(id),
  description      TEXT NOT NULL,
  assignee         TEXT,
  due_date         TEXT,
  priority         TEXT NOT NULL DEFAULT 'medium',   -- low | medium | high
  status           TEXT NOT NULL DEFAULT 'open',      -- open | done
  source_start_ms  INTEGER NOT NULL,
  source_end_ms    INTEGER NOT NULL,
  inferred         INTEGER NOT NULL DEFAULT 0,         -- 0/1, always 0 in Core (Strict-only)
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);
```

`PRAGMA foreign_keys = ON` plus `ON DELETE CASCADE` on `action_items.note_id` means deleting a
note automatically deletes its action items at the database level — `app/storage.py` still needs
to separately delete the note's file under `data/audio/`, since SQLite can't do that part.

## Pipeline

### Ingestion (runs synchronously inside one Streamlit interaction)

```
Record or upload audio → save to data/audio/, insert Note row with status="uploaded"
  → st.spinner("Transcribing…"):
      Transcribe (Groq whisper-large-v3-turbo, verbose_json) → save segments, status="extracting"
  → st.spinner("Finding action items…"):
      Extract (Groq llama-3.3-70b-versatile, Strict fidelity) → insert ActionItems
  → status="ready", st.rerun() to show the finished note
```

Unlike a client/server app, there's no background job or polling — the user just sees a spinner
for the ~5–15 seconds this takes. If either Groq call fails or raises, set `status="failed"`,
show `st.error(...)` with the reason, and don't insert partial action items.

### Editing an action item

A user can edit description, assignee, due date, priority, or status at any time; editing an
item never re-triggers Extraction.

## Module responsibilities

Since this is one app, not a client and a server, contracts are function signatures rather than
HTTP endpoints. Every function below enforces that a user can only touch their own rows — pass
`user_id` in and filter by it on every query, don't rely on the UI alone to hide other users' data.

```python
# app/storage.py
get_connection() -> sqlite3.Connection
create_user(name, email, password) -> int                       # returns user_id
verify_user(email, password) -> dict | None
create_note(user_id, title, audio_path, duration) -> int         # returns note_id
update_note_status(note_id, status)
save_transcript(note_id, segments)
list_notes(user_id) -> list[dict]
get_note(note_id, user_id) -> dict | None
delete_note(note_id, user_id)                                     # also removes the audio file
insert_action_items(note_id, user_id, items: list[dict])
list_action_items(user_id, status=None, note_id=None) -> list[dict]
update_action_item(item_id, user_id, **fields)

# app/transcription.py
transcribe(audio_path: str) -> list[dict]          # [{text, start_ms, end_ms}, ...]

# app/extraction.py
extract_action_items(segments: list[dict]) -> list[dict]
    # [{description, assignee, due_date, priority, source_start_ms, source_end_ms}, ...]
    # Strict fidelity: omit anything not directly supported by the segments

# app/auth.py
hash_password(password: str) -> str
check_password(password: str, hashed: str) -> bool
login_form()          # renders inputs, sets st.session_state["user"] on success
signup_form()          # renders inputs, calls storage.create_user
require_login()         # st.stop() if st.session_state has no "user"

# app/main.py
# Sidebar navigation (st.sidebar.radio) between: Login/Signup, Record, Notes, Note detail, Tasks
```

## App navigation

Since there's no separate frontend framework, navigation is a sidebar section switch inside
`app/main.py`, not URL routes:

| Section | Access | Purpose |
|---|---|---|
| Login / Signup | logged out | auth forms |
| Record | logged in | mic input / file upload → runs the Pipeline |
| Notes | logged in | library of past notes, click through to a note |
| Note detail | logged in | audio player + transcript + that note's checklist |
| Tasks | logged in | every open action item across notes, filterable |

## UI design system — light, Google Material–inspired, professional

Streamlit is themed globally through `.streamlit/config.toml`, topped up with a small CSS
injection for the details Streamlit's own theme options don't cover (pill buttons, card shadows).

### `.streamlit/config.toml`

```toml
[theme]
base = "light"
primaryColor = "#1A73E8"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F8F9FA"
textColor = "#202124"
font = "sans serif"
```

### CSS top-up (inject once via `st.markdown(..., unsafe_allow_html=True)` in `app/main.py`)

```css
/* Pill-shaped primary buttons, Material-style */
.stButton>button {
  border-radius: 999px;
  border: none;
  padding: 0.5rem 1.5rem;
}
/* Card-style containers */
div[data-testid="stContainer"] {
  background: #FFFFFF;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(60,64,67,.30), 0 1px 3px 1px rgba(60,64,67,.15);
  padding: 1.5rem;
}
```

### Components

- **Record section** — `st.audio_input` for the mic, `st.file_uploader` as a fallback, both
  inside a card container; a `st.spinner` during the Pipeline run.
- **Note library** — one card per note (`st.container(border=True)`), showing title, duration,
  relative date, a colored status badge (`st.badge` or `st.markdown` with inline color: green
  `ready`, amber `transcribing`/`extracting`, red `failed`), and open-task count.
- **Note detail** — `st.audio(audio_path)` for playback, the transcript rendered as a list of
  segments each prefixed with its timestamp, and the checklist below using `st.checkbox` per
  action item (checked = done). Clicking a checklist row's timestamp label re-renders the
  transcript with that segment highlighted (track the selected segment in `st.session_state`).
- **Priority** — a small colored dot before the description: red (`high`), amber (`medium`),
  gray (`low`).
- **Tasks view** — `st.dataframe` or a manual card list, grouped by due date, with
  `st.multiselect` filters for priority and status.

### Accessibility

Rely on Streamlit's own accessible defaults (semantic form labels, keyboard-navigable widgets);
don't suppress `st.audio_input`'s built-in recording indicator, since it's what tells a user
recording is actually happening.

## Requirements checklist

### Frontend (the Streamlit UI)

- [ ] Usable on both desktop and mobile browser widths (Streamlit's layout is responsive by
      default — avoid fixed-width custom CSS that breaks this).
- [ ] Navigation between Record, Notes, Note detail, and Tasks.
- [ ] `st.spinner` during transcription/extraction; `st.error` on failure.
- [ ] Action items visually distinct from the surrounding transcript text.

### Backend (the `app/` modules)

- [ ] Every function in Module responsibilities implemented and filtering by `user_id`.
- [ ] Ingestion always transcribes before extracting — never skip straight to extraction.
- [ ] Input validation: reject empty titles, unsupported audio types, and empty transcripts
      before calling Groq.
- [ ] Errors distinguish "no action items found" (empty list, not an error) from an actual Groq
      failure (`st.error` with a clear message).
- [ ] `GROQ_API_KEY` read from the environment (`.env` locally, Streamlit **Secrets** in
      production) — never hardcoded.

### Database

- [ ] Schema matches the Data model above, with `PRAGMA foreign_keys = ON` set on every
      connection.
- [ ] Full CRUD on notes and action items, including cascading deletes.
- [ ] No orphaned action items or leftover audio files under `data/audio/` after a delete.

### Authentication

- [ ] Signup, login, logout implemented.
- [ ] Every `app/storage.py` read/write is scoped to `st.session_state["user"]`'s id — a user
      can never see another user's notes or action items.
- [ ] `require_login()` gates every section except Login/Signup.
- [ ] Passwords stored only as `bcrypt` hashes, never in plain text.

## Environment variables

**Locally (`.env`, loaded with `python-dotenv`):**

```
GROQ_API_KEY=gsk_...
GROQ_STT_MODEL=whisper-large-v3-turbo
GROQ_LLM_MODEL=llama-3.3-70b-versatile
```

**On Streamlit Community Cloud:** `.env` files aren't read in production — set the same keys
under your app's **Settings → Secrets** in TOML format instead:

```toml
GROQ_API_KEY = "gsk_..."
GROQ_STT_MODEL = "whisper-large-v3-turbo"
GROQ_LLM_MODEL = "llama-3.3-70b-versatile"
```

Read them in code with a small helper that checks `st.secrets` first and falls back to
`os.environ`, so the same code works locally and deployed.

## Project folder structure

```
LLMs-Meet-Speech/                  # matches the repo layout in the screenshot
├── app/
│   ├── main.py             # entry point: streamlit run app/main.py — sidebar navigation
│   ├── auth.py              # hash_password, check_password, login_form, signup_form
│   ├── storage.py            # SQLite connection + all CRUD functions
│   ├── transcription.py      # Groq Whisper call
│   └── extraction.py         # Groq Llama call, Strict-fidelity prompt
├── data/
│   ├── notes.db               # created on first run
│   └── audio/                  # one file per note
├── .streamlit/
│   └── config.toml              # light theme tokens
├── .env                          # local only — GROQ_API_KEY etc., never committed
├── .gitignore                    # .env, data/*.db, data/audio/*, __pycache__, .DS_Store
├── README.md                     # setup + `streamlit run app/main.py` instructions
└── requirements.txt
```

**`requirements.txt`:**

```
streamlit>=1.38
groq
python-dotenv
bcrypt
```

## Deployment

| Component | Platform | Cost |
|---|---|---|
| Source code | GitHub (public repo) | Free |
| App hosting | Streamlit Community Cloud | Free, no card, sleeps after ~12h idle |
| Speech-to-text + LLM | Groq API | Free, no card, rate-limited |
| Database + audio | Local filesystem on the hosting container | Free, not guaranteed persistent across redeploys |

To deploy: push to GitHub → on share.streamlit.io choose **New app** → select the repo, branch
`main`, and entry point `app/main.py` → add `GROQ_API_KEY` (and the two model-name variables)
under **Secrets** → deploy. Every push to `main` redeploys automatically.

## Acceptance checklist

- [ ] A user can sign up, log in, record or upload a voice note, and watch it move through
      `uploaded` → `transcribing` → `extracting` → `ready` via the spinner.
- [ ] A note with no actionable speech produces an empty checklist, not a fabricated task.
- [ ] Clicking an action item highlights its source segment in the transcript.
- [ ] Marking an action item done persists after a page refresh.
- [ ] Deleting a note removes its action items and its audio file under `data/audio/`.
- [ ] A user cannot see another user's notes or action items.
- [ ] The app is reachable at its `*.streamlit.app` URL, not just `localhost`.