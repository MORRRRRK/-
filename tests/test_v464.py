from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.core import repository
from app.core.schema import apply_schema
from app.services import salary as salary_service
from app.services import tax as tax_service
from app.ui.pages.insurance import SalaryProfileTab
from app.ui.pages.spending_plans import SpendingPlansPage
from app.ui.widgets import make_save_button


class V464Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(tempfile.mkdtemp()) / "test.db")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(conn)
        return conn

    def test_default_monthly_pretax_from_salary(self) -> None:
        payload = salary_service.default_payload(2026)
        payload["params"]["monthly_salary"] = 10000.0
        payload["salary_items"] = [
            {"item_type": "subsidy", "name": "餐补", "amount": 500.0, "frequency": "monthly"},
            {"item_type": "performance", "name": "季度奖", "amount": 3000.0, "frequency": "quarterly"},
        ]
        self.assertAlmostEqual(
            salary_service.default_monthly_pretax(payload), 10500.0
        )

    def test_bonus_method_changes_tax(self) -> None:
        conn = self._conn()
        payload = salary_service.default_payload(2026)
        payload["params"]["monthly_salary"] = 10000.0
        separate = tax_service.monthly_schedule_profile(
            conn, 2026, payload, "separate"
        )
        combined = tax_service.monthly_schedule_profile(
            conn, 2026, payload, "combined"
        )
        self.assertGreater(separate["bonus_tax"], 0.0)
        self.assertNotAlmostEqual(
            separate["bonus_tax"], combined["bonus_tax"]
        )
        conn.close()

    def test_salary_tab_dirty_flag(self) -> None:
        conn = self._conn()
        payload = salary_service.default_payload(2026)
        profile_id = repository.add_salary_profile(
            conn, "方案", 2026, payload
        )
        conn.commit()
        profile = repository.get_salary_profile(conn, profile_id)
        tab = SalaryProfileTab(conn, profile, lambda: None)
        tab.show()
        self.app.processEvents()
        self.assertFalse(tab.is_dirty())
        tab.base_spin.setValue(12000.0)
        self.app.processEvents()
        self.assertTrue(tab.is_dirty())
        tab._save_payload()
        self.assertFalse(tab.is_dirty())
        conn.close()

    def test_spending_reorder_rows_persists_order(self) -> None:
        conn = self._conn()
        plan_id = repository.add_spending_plan(conn, "排序")
        first = repository.list_spending_plan_items(conn, plan_id)[0]
        repository.update_spending_plan_item(conn, first["id"], "第一个")
        second_id = repository.add_spending_plan_item(conn, plan_id, "第二个")
        third_id = repository.add_spending_plan_item(conn, plan_id, "第三个")
        conn.commit()
        page = SpendingPlansPage(conn, lambda: None)
        page.show()
        self.app.processEvents()
        page.plan_combo.setCurrentIndex(page.plan_combo.findData(plan_id))
        self.app.processEvents()
        page._reorder_rows(0, 2)
        self.app.processEvents()
        page._save_items()
        self.app.processEvents()
        ordered = repository.list_spending_plan_items(conn, plan_id)
        self.assertEqual([i["name"] for i in ordered], ["第二个", "第三个", "第一个"])
        conn.close()

    def test_reorder_preserves_edited_cells(self) -> None:
        conn = self._conn()
        plan_id = repository.add_spending_plan(conn, "保留编辑")
        first = repository.list_spending_plan_items(conn, plan_id)[0]
        repository.update_spending_plan_item(conn, first["id"], "第一个")
        second_id = repository.add_spending_plan_item(conn, plan_id, "第二个")
        conn.commit()
        page = SpendingPlansPage(conn, lambda: None)
        page.show()
        self.app.processEvents()
        page.plan_combo.setCurrentIndex(page.plan_combo.findData(plan_id))
        self.app.processEvents()
        page.items_table.item(0, 1).setText("第一个（已编辑）")
        page.items_table.item(0, 2).setText("100.00")
        page.items_table.item(0, 3).setText("200.00")
        page.items_table.item(0, 6).setText("备注内容")
        page._reorder_rows(0, 1)
        self.app.processEvents()
        self.assertEqual(page.items_table.item(0, 1).text(), "第二个")
        self.assertEqual(page.items_table.item(1, 1).text(), "第一个（已编辑）")
        self.assertEqual(page.items_table.item(1, 2).text(), "100.00")
        self.assertEqual(page.items_table.item(1, 6).text(), "备注内容")
        conn.close()

    def test_save_button_is_large(self) -> None:
        button = make_save_button("保存测试")
        self.assertGreaterEqual(button.minimumHeight(), 24)
        self.assertGreaterEqual(button.font().pointSize(), 9)


if __name__ == "__main__":
    unittest.main()
