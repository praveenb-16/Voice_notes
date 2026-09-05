"""
app/auth.py
Authentication helpers for Voice Notes → Action Items.

Passwords are hashed with bcrypt and never stored in plain text.
Session state key: st.session_state["user"] = {id, name, email}
"""

from __future__ import annotations

import os
import sys

# Ensure the app/ directory is on the path so sibling modules resolve
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import bcrypt
import streamlit as st

import storage


# ── Password helpers ──────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password* as a UTF-8 string."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    """Return True if *password* matches the *hashed* bcrypt digest."""
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ── Session guard ─────────────────────────────────────────────────────────────


def require_login() -> None:
    """Stop rendering if no user is logged in."""
    if "user" not in st.session_state:
        st.warning("Please log in to continue.")
        st.stop()


# ── Auth forms ────────────────────────────────────────────────────────────────


def login_form() -> None:
    """Render the login form and set session state on success."""
    st.subheader("Sign in")
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        if not email or not password:
            st.error("Please enter your email and password.")
            return
        user = storage.verify_user(email.strip().lower())
        if user and check_password(password, user["password_hash"]):
            st.session_state["user"] = {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
            }
            st.success(f"Welcome back, {user['name']}!")
            st.rerun()
        else:
            st.error("Invalid email or password.")


def signup_form() -> None:
    """Render the sign-up form and create the account on success."""
    st.subheader("Create account")
    with st.form("signup_form"):
        name = st.text_input("Name", placeholder="Your name")
        email = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password", help="At least 8 characters")
        password2 = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create account", use_container_width=True)

    if submitted:
        # Validation
        if not name or not email or not password:
            st.error("All fields are required.")
            return
        if len(password) < 8:
            st.error("Password must be at least 8 characters.")
            return
        if password != password2:
            st.error("Passwords do not match.")
            return

        try:
            hashed = hash_password(password)
            user_id = storage.create_user(name.strip(), email.strip().lower(), hashed)
            st.session_state["user"] = {
                "id": user_id,
                "name": name.strip(),
                "email": email.strip().lower(),
            }
            st.success(f"Account created! Welcome, {name.strip()}.")
            st.rerun()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                st.error("An account with that email already exists.")
            else:
                st.error(f"Could not create account: {exc}")
