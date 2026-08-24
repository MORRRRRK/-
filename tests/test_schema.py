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
        self.assertIn("tax_params", tables)
        self.assertIn("salary_items", tables)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(monthly_records)")
        }
        self.assertIn("monthly_expense", columns)
        social_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(social_insurance_params)")
        }
        self.assertIn("thirteenth_coefficient", social_columns)
        self.assertIn("year_end_bonus_coefficient", social_columns)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        conn.close()

    def test_old_db_auto_adds_monthly_expense(self) -> None:
        path = Path(tempfile.mkdtemp()) / "old.db"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE years (id INTEGER PRIMARY KEY AUTOINCREMENT, year INTEGER NOT NULL UNIQUE, note TEXT NOT NULL DEFAULT '')")
        conn.execute(
            """
            CREATE TABLE monthly_records (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              year_id INTEGER NOT NULL REFERENCES years(id) ON DELETE CASCADE,
              month INTEGER NOT NULL,
              salary REAL NOT NULL DEFAULT 0,
              year_end_bonus REAL NOT NULL DEFAULT 0,
              subsidies REAL NOT NULL DEFAULT 0,
              reimbursements REAL NOT NULL DEFAULT 0,
              income_note TEXT NOT NULL DEFAULT '',
              rent REAL NOT NULL DEFAULT 0,
              utilities REAL NOT NULL DEFAULT 0,
              housing_note TEXT NOT NULL DEFAULT '',
              forced_deposit REAL NOT NULL DEFAULT 0,
              deposit_note TEXT NOT NULL DEFAULT '',
              UNIQUE(year_id, month)
            )
            """
        )
        conn.execute("INSERT INTO years(year) VALUES (2026)")
        year_id = conn.execute("SELECT id FROM years WHERE year = 2026").fetchone()[0]
        conn.execute(
            "INSERT INTO monthly_records(year_id, month, salary) VALUES (?, 1, 10000)",
            (year_id,),
        )
        conn.commit()

        apply_schema(conn)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(monthly_records)")
        }
        self.assertIn("monthly_expense", columns)
        row = conn.execute(
            "SELECT salary, monthly_expense FROM monthly_records WHERE month = 1"
        ).fetchone()
        self.assertEqual(row[0], 10000)
        self.assertEqual(row[1], 0)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
