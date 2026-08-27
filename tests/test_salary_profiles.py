from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core import repository
from app.core.schema import apply_schema
from app.services import calculations, salary as salary_service, tax


class SalaryProfileTest(unittest.TestCase):
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(tempfile.mkdtemp()) / "test.db")
        conn.row_factory = sqlite3.Row
        apply_schema(conn)
        return conn

    def test_profile_crud_and_persistence(self) -> None:
        conn = self._conn()
        payload = salary_service.default_payload(2026)
        payload["params"]["monthly_salary"] = 12000.0
        profile_id = repository.add_salary_profile(
            conn, "新方案", 2026, payload
        )
        conn.commit()

        saved = repository.get_salary_profile(conn, profile_id)
        self.assertEqual(saved["name"], "新方案")
        self.assertEqual(saved["year"], 2026)
        decoded = salary_service.decode_payload(saved["payload"])
        self.assertAlmostEqual(
            salary_service.params(decoded)["monthly_salary"], 12000.0
        )

        repository.set_salary_profile_open(conn, profile_id, 0)
        conn.commit()
        self.assertNotIn(
            profile_id,
            [p["id"] for p in repository.list_open_salary_profiles(conn)],
        )
        repository.set_salary_profile_open(conn, profile_id, 1)
        repository.delete_salary_profile(conn, profile_id)
        conn.commit()
        self.assertIsNone(repository.get_salary_profile(conn, profile_id))
        conn.close()

    def test_profile_tax_schedule_matches_legacy(self) -> None:
        conn = self._conn()
        year_id = repository.ensure_year(conn, 2026)
        conn.execute(
            "INSERT INTO social_insurance_params(year_id, monthly_salary) "
            "VALUES (?, 10000)",
            (year_id,),
        )
        repository.upsert_monthly_records(
            conn,
            year_id,
            [{"month": 1, "salary": 10000.0}],
        )
        conn.commit()

        payload = salary_service.default_payload(2026)
        payload["params"]["monthly_salary"] = 10000.0
        from_profile = tax.monthly_schedule_profile(
            conn, 2026, payload, "separate"
        )
        from_legacy = tax.monthly_schedule_actual(conn, year_id, "separate")
        self.assertAlmostEqual(
            from_profile["total_income"], from_legacy["total_income"]
        )
        self.assertAlmostEqual(
            from_profile["total_tax"], from_legacy["total_tax"]
        )
        self.assertAlmostEqual(
            from_profile["net_income"], from_legacy["net_income"]
        )
        conn.close()

    def test_year_summary_balance_fix(self) -> None:
        conn = self._conn()
        year_id = repository.ensure_year(conn, 2026)
        repository.upsert_monthly_records(
            conn,
            year_id,
            [
                {
                    "month": 1,
                    "salary": 10000.0,
                    "rent": 1500.0,
                    "monthly_expense": 800.0,
                }
            ],
        )
        conn.commit()
        summary = calculations.year_summary(conn, year_id)
        self.assertAlmostEqual(summary["income"], 10000.0)
        self.assertAlmostEqual(summary["balance"], 7700.0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
