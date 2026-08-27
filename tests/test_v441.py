from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core import repository
from app.core.schema import _migrate_holdings_accounts, apply_schema
from app.services import account_service, exporter


class V441SchemaTest(unittest.TestCase):
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(Path(tempfile.mkdtemp()) / "test.db")
        conn.row_factory = sqlite3.Row
        apply_schema(conn)
        return conn

    def test_new_tables_and_account_columns(self) -> None:
        conn = self._conn()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("ai_chat_messages", tables)
        self.assertIn("ai_chat_state", tables)
        holding_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(holdings)")
        }
        gold_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(gold_accounts)")
        }
        self.assertIn("account_id", holding_columns)
        self.assertIn("account_id", gold_columns)
        conn.close()

    def test_holdings_channel_migrates_to_account(self) -> None:
        conn = self._conn()
        holding_id = repository.add_holding(
            conn,
            {
                "category": "基金",
                "channel": "华泰证券",
                "name": "测试基金",
                "holding_value": 1000.0,
                "holding_profit": 0.0,
                "cumulative_profit": 0.0,
                "symbol": "510300.SH",
                "asset_type": "fund_exchange",
                "shares": 100.0,
                "last_price": 10.0,
            },
        )
        conn.commit()
        _migrate_holdings_accounts(conn)
        conn.commit()
        holding = repository.get_holding(conn, holding_id)
        self.assertIsNotNone(holding)
        self.assertIsNotNone(holding["account_id"])
        account = account_service.get_account(conn, holding["account_id"])
        self.assertEqual(account["name"], "华泰证券")
        conn.close()

    def test_chat_messages_and_summary(self) -> None:
        conn = self._conn()
        repository.add_chat_message(conn, "user", "我的持仓健康吗")
        repository.add_chat_message(conn, "assistant", "比较健康")
        repository.save_chat_summary(conn, "压缩摘要")
        conn.commit()
        self.assertEqual(len(repository.list_chat_messages(conn)), 2)
        self.assertEqual(repository.get_chat_summary(conn), "压缩摘要")
        repository.clear_chat_messages(conn)
        conn.commit()
        self.assertEqual(len(repository.list_chat_messages(conn)), 0)
        self.assertEqual(repository.get_chat_summary(conn), "")
        conn.close()

    def test_bluecoins_export_format(self) -> None:
        conn = self._conn()
        account_id = account_service.add_account(conn, "现金", "cash")
        category_id = conn.execute(
            "SELECT id FROM transaction_categories WHERE name = '餐饮' "
            "AND parent_id IS NULL LIMIT 1"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO transactions(
              trans_date, type, amount, category_id, account_id,
              merchant, note, created_at
            ) VALUES ('2026-08-01', 'expense', 25.5, ?, ?, '午餐', '公司楼下', ?)
            """,
            (category_id, account_id, "2026-08-01 12:00:00"),
        )
        conn.commit()
        path = Path(tempfile.mkdtemp()) / "bluecoins.csv"
        count = exporter.export_bluecoins_csv(
            conn, "2026-08-01", "2026-08-31", path
        )
        self.assertEqual(count, 1)
        text = path.read_text(encoding="utf-8-sig")
        self.assertIn("类型,日期,设置时间,名称,金额,货币,汇率", text)
        self.assertIn("支出,2026-08-01,2026-08-01 12:00:00,午餐,-25.50,CNY,1", text)
        conn.close()


if __name__ == "__main__":
    unittest.main()
