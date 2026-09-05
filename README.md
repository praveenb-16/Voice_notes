# 🎙️ Voice Notes → Action Items

Turn a spoken voice note into a transcript and a checklist of concrete, trackable action items — each traceable back to the exact moment in the recording it came from.

## Features

- **Record or upload** audio in the browser
- **Transcription** via Groq Whisper (`whisper-large-v3-turbo`) with timestamps
- **Action-item extraction** via Groq Llama (`llama-3.3-70b-versatile`), strict-fidelity mode
- **Timestamp jump** — click a task to highlight the exact transcript segment it came from
- **Full task management** — mark done, edit, delete, filter across all notes
- **Account auth** — bcrypt-hashed passwords, per-user data isolation
- **Zero cost** — Groq free tier + Streamlit Community Cloud + local SQLite

## Quick start (local)

### 1. Clone & install

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
pip install -r requirements.txt
```

### 2. Get a Groq API key

Sign up free at <https://console.groq.com/keys> — one key covers both Whisper and Llama.

### 3. Configure environment

Copy the template and fill in your key:

```bash
# The .env file is already created; just edit GROQ_API_KEY:
# GROQ_API_KEY=gsk_your_actual_key_here
```

### 4. Run

```bash
streamlit run app/main.py
```

Open <http://localhost:8501> in your browser, create an account, and start recording.

---

## Deploy to Streamlit Community Cloud (free)

1. Push this repo to GitHub (make sure `.env` is in `.gitignore` — it is).
2. Go to <https://share.streamlit.io> → **New app**.
3. Select your repo, branch `main`, entry point `app/main.py`.
4. Under **Settings → Secrets**, add:

```toml
GROQ_API_KEY = "gsk_your_key_here"
GROQ_STT_MODEL = "whisper-large-v3-turbo"
GROQ_LLM_MODEL = "llama-3.3-70b-versatile"
```

5. Click **Deploy**. Every push to `main` redeploys automatically.

> **Note:** Streamlit Community Cloud apps sleep after ~12 hours with no traffic. Visit the URL once before a demo.

---

## Project structure

```
Voice_notes/
├── app/
│   ├── main.py           # Entry point — sidebar navigation
│   ├── auth.py           # bcrypt auth, login/signup forms
│   ├── storage.py        # SQLite CRUD layer
│   ├── transcription.py  # Groq Whisper STT
│   └── extraction.py     # Groq Llama extraction, strict-fidelity prompt
├── data/
│   ├── notes.db          # Created on first run (gitignored)
│   └── audio/            # One file per note (gitignored)
├── .streamlit/
│   └── config.toml       # Light, Material-inspired theme
├── .env                  # Local secrets — never commit (gitignored)
├── .gitignore
├── requirements.txt
└── README.md
```

## Tech stack

| Layer | Choice |
|---|---|
| App framework | Streamlit ≥ 1.38 |
| Speech-to-text | Groq API — `whisper-large-v3-turbo` |
| LLM extraction | Groq API — `llama-3.3-70b-versatile` |
| Database | SQLite (`data/notes.db`) |
| Auth | bcrypt + `st.session_state` |
| Hosting | Streamlit Community Cloud |

## Limitations

- Extraction quality depends on how clearly tasks were stated in the recording.
- A note with no actionable speech produces an empty checklist — never a fabricated list.
- The SQLite database lives on the hosting container's filesystem and may be wiped on redeploy. For persistent storage, swap `app/storage.py` to MongoDB Atlas.
