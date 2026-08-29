from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core import repository
from app.core.schema import SCHEMA_VERSION, apply_schema
from app.services import pension as pension_service
from app.services import tax as tax_service


class V463SchemaTest(unittest.TestCase):
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(tempfile.mkdtemp()) / "test.db")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def test_new_columns_are_added_to_old_db(self) -> None:
        conn = self._conn()
        conn.executescript(
            """
            CREATE TABLE tax_params (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              year_id INTEGER NOT NULL UNIQUE,
              custom_deduction REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE pension_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              province TEXT NOT NULL DEFAULT '',
              start_year INTEGER NOT NULL,
              end_year INTEGER NOT NULL,
              monthly_base REAL NOT NULL DEFAULT 0,
              note TEXT NOT NULL DEFAULT ''
            );
            """
        )
        apply_schema(conn)
        tax_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(tax_params)")
        }
        pension_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(pension_jobs)")
        }
        self.assertIn("personal_pension_annual", tax_cols)
        self.assertIn("personal_rate", pension_cols)
        self.assertIn("company_rate", pension_cols)
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0],
            SCHEMA_VERSION,
        )
        conn.close()

    def test_personal_pension_tax_deduction(self) -> None:
        monthly = tax_service.special_deductions_monthly(
            {"personal_pension_annual": 12000, "elderly_option": "none"}
        )
        self.assertAlmostEqual(monthly, 1000.0)
        capped = tax_service.special_deductions_monthly(
            {"personal_pension_annual": 20000, "elderly_option": "none"}
        )
        self.assertAlmostEqual(capped, 1000.0)

    def test_pension_uses_per_job_rate(self) -> None:
        job = {
            "name": "A公司",
            "province": "北京",
            "start_year": 2010,
            "end_year": 2024,
            "monthly_base": 10000,
            "personal_rate": 0.12,
            "company_rate": 0.20,
        }
        result = pension_service.calculate_pension(job, retire_age=60)
        self.assertAlmostEqual(result["personal_rate"], 0.12)
        self.assertAlmostEqual(result["company_rate"], 0.20)
        self.assertAlmostEqual(
            result["personal_savings"], 10000 * 0.12 * 12 * 15
        )
        self.assertAlmostEqual(
            result["personal_pension"],
            result["personal_savings"] / 139,
        )

    def test_personal_pension_monthly_payout(self) -> None:
        result = pension_service.calculate_personal_pension(
            enabled=True,
            annual=12000,
            return_rate=0.0,
            start_year=2024,
            end_year=2033,
            retire_age=60,
        )
        self.assertEqual(result["years"], 10)
        self.assertAlmostEqual(result["contributed"], 120000)
        self.assertAlmostEqual(result["balance"], 120000)
        self.assertAlmostEqual(result["monthly"], 120000 / 139)
        self.assertAlmostEqual(result["monthly_after_tax"], result["monthly"] * 0.97)

    def test_spending_item_sort_persists(self) -> None:
        conn = self._conn()
        apply_schema(conn)
        plan_id = repository.add_spending_plan(conn, "旅行")
        first = repository.list_spending_plan_items(conn, plan_id)[0]
        second_id = repository.add_spending_plan_item(conn, plan_id, "机票")
        repository.update_spending_plan_item_sort(conn, first["id"], 1)
        repository.update_spending_plan_item_sort(conn, second_id, 0)
        conn.commit()
        ordered = repository.list_spending_plan_items(conn, plan_id)
        self.assertEqual(ordered[0]["name"], "机票")
        self.assertEqual(ordered[1]["name"], first["name"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
