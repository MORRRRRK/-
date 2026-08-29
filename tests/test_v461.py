from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core import repository
from app.core.schema import apply_schema
from app.ui.pages.spending_plans import LinkTransactionsDialog, SpendingPlansPage
from app.ui.widgets import PageShortcutFilter


class V461GuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(tempfile.mkdtemp()) / "test.db")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(conn)
        return conn

    def test_link_dialog_defaults_to_recent_three_months(self) -> None:
        conn = self._conn()
        plan_id = repository.add_spending_plan(conn, "旅行")
        item_id = repository.list_spending_plan_items(conn, plan_id)[0]["id"]
        dialog = LinkTransactionsDialog(conn, plan_id, item_id)
        self.assertEqual(
            dialog.start_edit.date(), QDate.currentDate().addMonths(-3)
        )
        self.assertEqual(dialog.end_edit.date(), QDate.currentDate())
        conn.close()

    def test_enter_saves_plan_info(self) -> None:
        conn = self._conn()
        plan_id = repository.add_spending_plan(conn, "旧名称")
        conn.commit()
        page = SpendingPlansPage(conn, lambda: None)
        page.plan_combo.setCurrentIndex(
            page.plan_combo.findData(plan_id)
        )
        page.show()
        self.app.processEvents()
        filt = PageShortcutFilter(lambda: page)
        self.app.installEventFilter(filt)
        edit = page.plan_name_edit
        edit.setText("回车保存的新名称")
        edit.setFocus()
        self.app.processEvents()
        QTest.keyClick(edit, Qt.Key_Return)
        self.app.processEvents()
        saved = repository.get_spending_plan(conn, plan_id)
        self.assertEqual(saved["name"], "回车保存的新名称")
        conn.close()

    def test_ctrl_z_restores_deleted_item(self) -> None:
        conn = self._conn()
        plan_id = repository.add_spending_plan(conn, "买相机")
        conn.commit()
        page = SpendingPlansPage(conn, lambda: None)
        page.show()
        self.app.processEvents()
        filt = PageShortcutFilter(lambda: page)
        self.app.installEventFilter(filt)
        item = dict(
            repository.list_spending_plan_items(conn, plan_id)[0]
        )
        repository.delete_spending_plan_item(conn, item["id"])
        conn.commit()
        page._deleted_items.append(item)
        page.items_table.setFocus()
        self.app.processEvents()
        QTest.keyClick(page.items_table, Qt.Key_Z, Qt.ControlModifier)
        self.app.processEvents()
        restored = repository.list_spending_plan_items(conn, plan_id)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["name"], item["name"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
