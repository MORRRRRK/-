from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core import repository
from app.core.schema import SCHEMA_VERSION, apply_schema


class V462SchemaTest(unittest.TestCase):
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(tempfile.mkdtemp()) / "test.db")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def test_old_db_gets_completed_and_voucher_columns(self) -> None:
        conn = self._conn()
        conn.executescript(
            """
            CREATE TABLE spending_plans (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              total_budget REAL NOT NULL DEFAULT 0,
              start_date TEXT NOT NULL DEFAULT '',
              end_date TEXT NOT NULL DEFAULT '',
              note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE spending_plan_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              plan_id INTEGER NOT NULL REFERENCES spending_plans(id) ON DELETE CASCADE,
              name TEXT NOT NULL DEFAULT '未分项',
              planned_amount REAL NOT NULL DEFAULT 0,
              manual_actual REAL NOT NULL DEFAULT 0,
              note TEXT NOT NULL DEFAULT '',
              sort_order INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        apply_schema(conn)
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(spending_plan_items)"
            )
        }
        self.assertIn("completed", columns)
        self.assertIn("voucher_path", columns)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0],
            SCHEMA_VERSION,
        )
        conn.close()

    def test_item_completed_and_voucher_roundtrip(self) -> None:
        conn = self._conn()
        apply_schema(conn)
        plan_id = repository.add_spending_plan(conn, "买相机")
        item_id = repository.add_spending_plan_item(
            conn,
            plan_id,
            "机身",
            planned_amount=13000,
            completed=1,
        )
        repository.update_spending_plan_item_voucher(
            conn, item_id, "voucher_test.jpg"
        )
        conn.commit()
        item = repository.get_spending_plan_item(conn, item_id)
        self.assertEqual(int(item["completed"]), 1)
        self.assertEqual(item["voucher_path"], "voucher_test.jpg")

        repository.update_spending_plan_item(
            conn,
            item_id,
            "机身+镜头",
            planned_amount=16000,
            manual_actual=12800,
            note="改主意",
            completed=0,
        )
        conn.commit()
        item = repository.get_spending_plan_item(conn, item_id)
        self.assertEqual(item["name"], "机身+镜头")
        self.assertEqual(int(item["completed"]), 0)
        self.assertEqual(item["voucher_path"], "voucher_test.jpg")
        conn.close()


if __name__ == "__main__":
    unittest.main()
