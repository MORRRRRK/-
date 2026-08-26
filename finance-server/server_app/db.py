from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "finance-server.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS auth_tokens (
          token TEXT PRIMARY KEY,
          created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS entities (
          table_name TEXT NOT NULL,
          row_id INTEGER NOT NULL,
          data_json TEXT NOT NULL DEFAULT '{}',
          deleted INTEGER NOT NULL DEFAULT 0,
          updated_at REAL NOT NULL DEFAULT 0,
          PRIMARY KEY (table_name, row_id)
        );

        CREATE TABLE IF NOT EXISTS changes (
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          table_name TEXT NOT NULL,
          row_id INTEGER NOT NULL,
          data_json TEXT NOT NULL DEFAULT '{}',
          deleted INTEGER NOT NULL DEFAULT 0,
          updated_at REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS server_settings (
          key TEXT PRIMARY KEY,
          value TEXT
        );
        """
    )
    conn.commit()


def register_token(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("INSERT OR REPLACE INTO auth_tokens(token) VALUES (?)", (token,))
    conn.commit()


def token_exists(conn: sqlite3.Connection, token: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM auth_tokens WHERE token = ?", (token,)
    ).fetchone()
    return row is not None
