"""NovaAI - SQLite database backend.

Provides the low-level connection and schema management.
All data that was previously stored in JSON files (profiles.json,
profile.json, history.jsonl) now lives in data/novaai.db.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .paths import DATA_DIR

DB_PATH = DATA_DIR / "novaai.db"

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating the DB if needed."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    _local.conn = conn
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't already exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS app_state (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profiles (
            profile_id   TEXT PRIMARY KEY,
            profile_name TEXT NOT NULL DEFAULT '',
            data         TEXT NOT NULL DEFAULT '{}',
            created_at   TEXT NOT NULL DEFAULT '',
            updated_at   TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT    NOT NULL,
            role      TEXT    NOT NULL,
            content   TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_history_ts ON history(timestamp);
    """)
    conn.commit()


# ── app_state helpers ─────────────────────────────────────────────────────

def get_state(key: str, default: str = "") -> str:
    conn = get_connection()
    row = conn.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(key: str, value: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO app_state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


# ── profile helpers ───────────────────────────────────────────────────────

def upsert_profile(profile_id: str, profile: dict[str, Any]) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO profiles(profile_id, profile_name, data, created_at, updated_at) "
        "VALUES(?, ?, ?, ?, ?) "
        "ON CONFLICT(profile_id) DO UPDATE SET "
        "  profile_name=excluded.profile_name, "
        "  data=excluded.data, "
        "  created_at=excluded.created_at, "
        "  updated_at=excluded.updated_at",
        (
            profile_id,
            str(profile.get("profile_name", "")),
            json.dumps(profile, ensure_ascii=False),
            str(profile.get("created_at", "")),
            str(profile.get("updated_at", "")),
        ),
    )
    conn.commit()


def load_all_profiles() -> dict[str, dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT profile_id, data FROM profiles").fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            result[row["profile_id"]] = json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            pass
    return result


def load_single_profile(profile_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT data FROM profiles WHERE profile_id=?", (profile_id,)
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["data"])
    except (json.JSONDecodeError, TypeError):
        return None


def delete_profile_row(profile_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM profiles WHERE profile_id=?", (profile_id,))
    conn.commit()


def profile_exists(profile_id: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM profiles WHERE profile_id=?", (profile_id,)
    ).fetchone()
    return row is not None


def profile_count() -> int:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS cnt FROM profiles").fetchone()
    return row["cnt"] if row else 0


def all_profile_ids() -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT profile_id FROM profiles ORDER BY profile_id").fetchall()
    return [r["profile_id"] for r in rows]


# ── history helpers ───────────────────────────────────────────────────────

def append_history_row(timestamp: str, role: str, content: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO history(timestamp, role, content) VALUES(?, ?, ?)",
        (timestamp, role, content),
    )
    conn.commit()


def read_history_tail(max_turns: int) -> list[dict[str, str]]:
    """Return the last *max_turns* user+assistant exchanges (up to 2x rows)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM history "
        "WHERE role IN ('user', 'assistant') "
        "ORDER BY id DESC LIMIT ?",
        (max_turns * 2,),
    ).fetchall()
    # Rows come newest-first; reverse to chronological order
    messages: list[dict[str, str]] = []
    for row in reversed(rows):
        messages.append({"role": row["role"], "content": row["content"]})
    return messages


def clear_history() -> None:
    conn = get_connection()
    conn.execute("DELETE FROM history")
    conn.commit()


def history_row_count() -> int:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS cnt FROM history").fetchone()
    return row["cnt"] if row else 0


# ── migration: import from legacy JSON files ──────────────────────────────

def migrate_from_json_if_needed(
    profiles_path: Path,
    profile_path: Path,
    history_path: Path,
) -> bool:
    """
    One-time import of legacy JSON/JSONL files into SQLite.
    Returns True if any data was migrated.
    """
    migrated = False

    # Skip if we already have data
    if profile_count() > 0 and history_row_count() > 0:
        return False

    # ── Profiles ──────────────────────────────────────────────────────────
    if profile_count() == 0:
        raw_profiles: dict[str, dict[str, Any]] = {}
        active_id = ""

        if profiles_path.exists():
            try:
                with profiles_path.open("r", encoding="utf-8") as f:
                    store = json.load(f)
                raw_profiles = store.get("profiles", {})
                active_id = store.get("active_profile_id", "")
                migrated = True
            except (json.JSONDecodeError, OSError):
                pass

        if not raw_profiles and profile_path.exists():
            try:
                with profile_path.open("r", encoding="utf-8") as f:
                    single = json.load(f)
                pid = str(single.get("profile_id", "default"))
                raw_profiles = {pid: single}
                active_id = pid
                migrated = True
            except (json.JSONDecodeError, OSError):
                pass

        for pid, pdata in raw_profiles.items():
            upsert_profile(pid, pdata)
        if active_id:
            set_state("active_profile_id", active_id)

    # ── History ───────────────────────────────────────────────────────────
    if history_row_count() == 0 and history_path.exists():
        try:
            with history_path.open("r", encoding="utf-8") as f:
                conn = get_connection()
                batch: list[tuple[str, str, str]] = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    role = entry.get("role", "")
                    content = entry.get("content", "")
                    ts = entry.get("timestamp", "")
                    if role and content:
                        batch.append((ts, role, content))
                if batch:
                    conn.executemany(
                        "INSERT INTO history(timestamp, role, content) VALUES(?, ?, ?)",
                        batch,
                    )
                    conn.commit()
                    migrated = True
        except OSError:
            pass

    return migrated
