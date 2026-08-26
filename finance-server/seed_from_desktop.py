"""把桌面端 data/finance.db 的现有数据一次性导入服务端。"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_DB = PROJECT_ROOT / "data" / "finance.db"
SERVER_DB = Path(__file__).resolve().parent / "finance-server.db"


def _rows(conn: sqlite3.Connection, sql: str) -> list[dict]:
    return [dict(r) for r in conn.execute(sql)]


def _insert(
    conn: sqlite3.Connection,
    table: str,
    row_id: int,
    data: dict,
    updated_at: float,
) -> None:
    conn.execute(
        """
        INSERT INTO entities(table_name, row_id, data_json, deleted, updated_at)
        VALUES (?, ?, ?, 0, ?)
        ON CONFLICT(table_name, row_id) DO UPDATE SET
          data_json = excluded.data_json, updated_at = excluded.updated_at
        """,
        (table, row_id, json.dumps(data, ensure_ascii=False), updated_at),
    )
    conn.execute(
        """
        INSERT INTO changes(table_name, row_id, data_json, deleted, updated_at)
        VALUES (?, ?, ?, 0, ?)
        """,
        (table, row_id, json.dumps(data, ensure_ascii=False), updated_at),
    )


def main() -> None:
    if not DESKTOP_DB.exists():
        raise SystemExit(f"找不到桌面数据库：{DESKTOP_DB}")
    src = sqlite3.connect(str(DESKTOP_DB))
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(str(SERVER_DB))
    dst.execute("DELETE FROM changes")
    dst.execute("DELETE FROM entities")
    now = time.time()

    years = _rows(src, "SELECT * FROM years ORDER BY year")
    for record in _rows(src, "SELECT * FROM monthly_records"):
        year_row = next(
            (y for y in years if y["id"] == record["year_id"]), None
        )
        year = year_row["year"] if year_row else 0
        row_id = year * 100 + int(record["month"])
        _insert(
            dst,
            "monthly_records",
            row_id,
            {
                "year": year,
                "month": record["month"],
                "salary": record["salary"],
                "year_end_bonus": record["year_end_bonus"],
                "subsidies": record["subsidies"],
                "reimbursements": record["reimbursements"],
                "income_note": record["income_note"],
                "rent": record["rent"],
                "utilities": record["utilities"],
                "housing_note": record["housing_note"],
                "monthly_expense": record["monthly_expense"],
                "forced_deposit": record["forced_deposit"],
                "deposit_note": record["deposit_note"],
            },
            now,
        )

    for item in _rows(src, "SELECT * FROM large_items"):
        _insert(
            dst,
            "large_items",
            int(item["id"]),
            {
                "item_type": item["item_type"],
                "item_date": item["item_date"],
                "name": item["name"],
                "amount": item["amount"],
                "note": item["note"],
            },
            now,
        )

    for holding in _rows(src, "SELECT * FROM holdings"):
        _insert(
            dst,
            "holdings",
            int(holding["id"]),
            {
                "category": holding["category"],
                "channel": holding["channel"],
                "name": holding["name"],
                "symbol": holding["symbol"],
                "asset_type": holding["asset_type"],
                "shares": holding["shares"],
                "holding_value": holding["holding_value"],
                "holding_profit": holding["holding_profit"],
                "cumulative_profit": holding["cumulative_profit"],
                "return_rate": holding["return_rate"],
                "cost_basis": holding["cost_basis"],
                "last_price": holding["last_price"],
                "price_time": holding["price_time"],
                "invest_plan": holding["invest_plan"],
                "invest_time": holding["invest_time"],
            },
            now,
        )

    for account in _rows(src, "SELECT * FROM gold_accounts"):
        _insert(
            dst,
            "gold_accounts",
            int(account["id"]),
            {
                "name": account["name"],
                "channel": account["channel"],
                "grams": account["grams"],
                "cost_basis": account["cost_basis"],
                "last_price": account["last_price"],
                "price_time": account["price_time"],
                "note": account["note"],
            },
            now,
        )

    for goal in _rows(src, "SELECT * FROM goals"):
        _insert(
            dst,
            "goals",
            int(goal["id"]),
            {
                "name": goal["name"],
                "target_amount": goal["target_amount"],
                "target_date": goal["target_date"],
                "current_amount": goal["current_amount"],
                "monthly_saving": goal["monthly_saving"],
                "note": goal["note"],
            },
            now,
        )

    dst.commit()
    count = dst.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    print(f"导入完成：{count} 条记录")
    src.close()
    dst.close()


if __name__ == "__main__":
    main()
