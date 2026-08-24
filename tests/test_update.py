from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services import updater


class UpdateBackupTest(unittest.TestCase):
    def test_backup_with_pending_transaction(self) -> None:
        temp = Path(tempfile.mkdtemp())
        src = temp / "src.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (x)")
        conn.execute("INSERT INTO t VALUES (1)")

        backup_dir = temp / "backups"
        target = updater._backup_database(backup_dir, db_path=src)

        check = sqlite3.connect(str(target))
        count = check.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        self.assertIn(count, (0, 1))
        check.close()
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    unittest.main()
