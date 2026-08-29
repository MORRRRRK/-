from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from . import paths
from .schema import SCHEMA_VERSION, apply_schema


def backup_before_migration(
    path: Path,
    conn: sqlite3.Connection,
    backups_target: Path | None = None,
) -> Path | None:
    """升级数据库前自动备份旧库，保证更新后数据可回滚。"""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        old = int(conn.execute("PRAGMA user_version").fetchone()[0])
    except Exception:
        return None
    if old >= SCHEMA_VERSION:
        return None
    target_dir = backups_target or paths.backups_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = target_dir / f"pre_migration_v{old}_to_v{SCHEMA_VERSION}_{stamp}.db"
    shutil.copy2(path, target)
    return target


class Database:
    """应用持有的 SQLite 连接，由主窗口创建并传给各页面。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else paths.db_path()
        paths.ensure_dirs()
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        try:
            self.conn.execute("PRAGMA wal_checkpoint(FULL)")
        except sqlite3.Error:
            pass
        backup_before_migration(self.path, self.conn)
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
