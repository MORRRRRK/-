from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core import repository
from app.core.schema import SCHEMA_VERSION, apply_schema
from app.services import account_service, transaction_service


class SpendingPlansTest(unittest.TestCase):
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(tempfile.mkdtemp()) / "test.db")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(conn)
        return conn

    def _expense(
        self, conn, account_id: int, amount: float, merchant: str
    ) -> int:
        return transaction_service.add_transaction(
            conn,
            trans_date="2026-08-01",
            trans_type="expense",
            amount=amount,
            category_id=None,
            account_id=account_id,
            merchant=merchant,
        )

    def test_plan_item_link_summary(self) -> None:
        conn = self._conn()
        account_id = account_service.add_account(conn, "现金", "cash")
        t1 = self._expense(conn, account_id, 12800, "相机店")
        t2 = self._expense(conn, account_id, 3200, "镜头店")
        conn.commit()

        plan_id = repository.add_spending_plan(conn, "买相机", 20000)
        conn.commit()
        items = repository.list_spending_plan_items(conn, plan_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "未分项")

        item_id = repository.add_spending_plan_item(
            conn, plan_id, "机身", planned_amount=13000
        )
        repository.set_spending_item_links(
            conn, plan_id, item_id, [t1]
        )
        conn.commit()

        summary = repository.spending_plan_summary(conn, plan_id)
        body = next(
            item
            for item in summary["items"]
            if item["id"] == item_id
        )
        self.assertAlmostEqual(body["actual"], 12800.0)
        self.assertAlmostEqual(summary["total_actual"], 12800.0)
        self.assertAlmostEqual(summary["total_planned"], 13000.0)
        self.assertAlmostEqual(summary["remaining"], 7200.0)

        transaction_service.update_transaction(
            conn, t1, amount=13500.0
        )
        conn.commit()
        summary = repository.spending_plan_summary(conn, plan_id)
        body = next(
            item
            for item in summary["items"]
            if item["id"] == item_id
        )
        self.assertAlmostEqual(body["actual"], 13500.0)
        conn.close()

    def test_link_moves_between_items(self) -> None:
        conn = self._conn()
        account_id = account_service.add_account(conn, "现金", "cash")
        t1 = self._expense(conn, account_id, 200, "猫砂盆")
        conn.commit()
        plan_id = repository.add_spending_plan(conn, "养猫")
        item_a = repository.list_spending_plan_items(conn, plan_id)[0]["id"]
        item_b = repository.add_spending_plan_item(conn, plan_id, "猫砂盆")
        repository.set_spending_item_links(conn, plan_id, item_a, [t1])
        repository.set_spending_item_links(conn, plan_id, item_b, [t1])
        conn.commit()
        links = repository.list_spending_plan_links(conn, plan_id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["item_id"], item_b)
        conn.close()

    def test_undo_plan_restores_items_and_links(self) -> None:
        conn = self._conn()
        account_id = account_service.add_account(conn, "现金", "cash")
        t1 = self._expense(conn, account_id, 999, "机票")
        conn.commit()
        plan_id = repository.add_spending_plan(conn, "旅行")
        item_id = repository.list_spending_plan_items(conn, plan_id)[0]["id"]
        repository.set_spending_item_links(conn, plan_id, item_id, [t1])
        conn.commit()

        plan = repository.get_spending_plan(conn, plan_id)
        items = repository.list_spending_plan_items(conn, plan_id)
        links = repository.list_spending_plan_links(conn, plan_id)
        repository.delete_spending_plan(conn, plan_id)
        conn.commit()

        repository.restore_spending_plan(conn, plan)
        for item in items:
            repository.restore_spending_plan_item(conn, item)
        repository.restore_spending_plan_links(conn, links)
        conn.commit()

        restored = repository.list_spending_plan_links(conn, plan_id)
        self.assertEqual(len(restored), 1)
        self.assertAlmostEqual(
            repository.spending_plan_summary(conn, plan_id)["total_actual"],
            999.0,
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
