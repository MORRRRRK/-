from __future__ import annotations

import sqlite3
from pathlib import Path

from . import paths
from .schema import SCHEMA_VERSION, apply_schema


class Database:
    """应用持有的 SQLite 连接，由主窗口创建并传给各页面。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else paths.db_path()
        paths.ensure_dirs()
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        apply_schema(self.conn)

    def close(self) -> None:
        self.conn.close()

    def commit(self) -> None:
        self.conn.commit()

    @property
    def version(self) -> int:
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def migrate_to(self, version: int) -> None:
        """预留：未来 schema 升级入口。"""
        if version == SCHEMA_VERSION:
            self.commit()
