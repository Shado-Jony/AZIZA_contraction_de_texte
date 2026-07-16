"""
demo/token_manager.py — Gestion des tokens API clients
======================================================
Plans :
  free       → 100 req/j
  basic      → 500 req/j
  pro        → 5 000 req/j
  unlimited  → aucune limite
"""

import os
import sqlite3
import uuid
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "tokens.db"
_local = threading.local()

PLANS = {
    "free":       {"req_per_day": 100,  "label": "Free"},
    "basic":      {"req_per_day": 500,  "label": "Basic"},
    "pro":        {"req_per_day": 5000, "label": "Pro"},
    "unlimited":  {"req_per_day": 0,    "label": "Illimité"},
}


def _get_conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH))
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            token       TEXT    UNIQUE NOT NULL,
            client_name TEXT    NOT NULL,
            plan        TEXT    NOT NULL DEFAULT 'free',
            requests_limit   INTEGER NOT NULL DEFAULT 100,
            requests_used    INTEGER NOT NULL DEFAULT 0,
            reset_at    TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            active      INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()


def create_token(client_name: str, plan: str = "free") -> dict:
    init_db()
    if plan not in PLANS:
        raise ValueError(f"Plan inconnu : {plan}. Choisir parmi {list(PLANS)}")
    token = uuid.uuid4().hex
    limit = PLANS[plan]["req_per_day"]
    now = datetime.now(timezone.utc)
    reset_at = (now + timedelta(days=1)).isoformat()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO api_tokens (token, client_name, plan, requests_limit, reset_at) VALUES (?, ?, ?, ?, ?)",
        (token, client_name, plan, limit, reset_at),
    )
    conn.commit()
    return get_token(token)


def get_token(token: str) -> dict | None:
    init_db()
    conn = _get_conn()
    row = conn.execute("SELECT * FROM api_tokens WHERE token = ?", (token,)).fetchone()
    if row is None:
        return None
    return dict(row)


def list_tokens(only_active: bool = False) -> list[dict]:
    init_db()
    conn = _get_conn()
    query = "SELECT * FROM api_tokens"
    params = []
    if only_active:
        query += " WHERE active = 1"
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def deactivate_token(token: str) -> bool:
    init_db()
    conn = _get_conn()
    cur = conn.execute("UPDATE api_tokens SET active = 0 WHERE token = ?", (token,))
    conn.commit()
    return cur.rowcount > 0


def _maybe_reset(token_row: dict) -> dict:
    now = datetime.now(timezone.utc)
    reset_at = datetime.fromisoformat(token_row["reset_at"])
    if now >= reset_at:
        limit = PLANS.get(token_row["plan"], {}).get("req_per_day", 100)
        new_reset = (now + timedelta(days=1)).isoformat()
        conn = _get_conn()
        conn.execute(
            "UPDATE api_tokens SET requests_used = 0, reset_at = ? WHERE id = ?",
            (new_reset, token_row["id"]),
        )
        conn.commit()
        token_row["requests_used"] = 0
        token_row["reset_at"] = new_reset
    return token_row


def validate_token(token: str) -> dict:
    init_db()
    row = get_token(token)
    if row is None:
        return {"ok": False, "error": "Token invalide", "status": 401}
    if not row["active"]:
        return {"ok": False, "error": "Token désactivé", "status": 403}
    row = _maybe_reset(row)
    limit = row["requests_limit"]
    if limit > 0 and row["requests_used"] >= limit:
        reset_at = datetime.fromisoformat(row["reset_at"])
        retour = reset_at.strftime("%d/%m/%Y %H:%M UTC")
        return {
            "ok": False,
            "error": f"Quota épuisé ({row['requests_used']}/{limit} req/j). Retour le {retour}",
            "status": 429,
            "plan": row["plan"],
            "limit": limit,
            "used": row["requests_used"],
        }
    return {
        "ok": True,
        "token": row["token"],
        "client_name": row["client_name"],
        "plan": row["plan"],
        "limit": limit,
        "used": row["requests_used"],
        "remaining": max(0, limit - row["requests_used"]) if limit > 0 else -1,
    }


def increment_usage(token: str) -> bool:
    init_db()
    conn = _get_conn()
    row = conn.execute("SELECT * FROM api_tokens WHERE token = ?", (token,)).fetchone()
    if row is None:
        return False
    row = _maybe_reset(dict(row))
    conn.execute(
        "UPDATE api_tokens SET requests_used = requests_used + 1 WHERE id = ?",
        (row["id"],),
    )
    conn.commit()
    return True


def change_plan(token: str, new_plan: str) -> dict | None:
    if new_plan not in PLANS:
        raise ValueError(f"Plan inconnu : {new_plan}")
    init_db()
    conn = _get_conn()
    limit = PLANS[new_plan]["req_per_day"]
    cur = conn.execute(
        "UPDATE api_tokens SET plan = ?, requests_limit = ? WHERE token = ?",
        (new_plan, limit, token),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_token(token)
