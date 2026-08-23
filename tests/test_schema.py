from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core.schema import SCHEMA_VERSION, apply_schema


class SchemaTest(unittest.TestCase):
    def test_apply_schema_creates_all_tables(self) -> None:
        path = Path(tempfile.mkdtemp()) / "test.db"
        conn = sqlite3.connect(path)
        apply_schema(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("pension_jobs", tables)
        self.assertIn("ai_reports", tables)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
