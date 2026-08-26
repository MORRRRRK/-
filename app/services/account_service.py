"""账户管理：账户 CRUD、余额重算与资产汇总。"""
from __future__ import annotations

import sqlite3
from typing import Any


def get_accounts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """获取所有账户，按 sort_order 排序。"""
    rows = conn.execute(
        "SELECT * FROM accounts ORDER BY sort_order, id"
    ).fetchall()
    return [dict(row) for row in rows]


def get_account(conn: sqlite3.Connection, account_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    return dict(row) if row else None


def add_account(
    conn: sqlite3.Connection,
    name: str,
    account_type: str,
    institution: str = "",
    initial_balance: float = 0.0,
    is_liability: bool = False,
    note: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO accounts(
          name, type, institution, initial_balance, current_balance,
          is_liability, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            account_type,
            institution,
            initial_balance,
            initial_balance,
            1 if is_liability else 0,
            note,
        ),
    )
    return int(cur.lastrowid)


def update_account(conn: sqlite3.Connection, account_id: int, **kwargs: Any) -> None:
    allowed = {
        "name", "type", "institution", "initial_balance", "is_liability",
        "sort_order", "note",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{key} = ?" for key in fields)
    conn.execute(
        f"UPDATE accounts SET {sets} WHERE id = ?",
        (*fields.values(), account_id),
    )


def delete_account(conn: sqlite3.Connection, account_id: int) -> None:
    """删除账户；有关联交易时禁止删除。"""
    if conn.execute(
        "SELECT 1 FROM transactions WHERE account_id = ? OR to_account_id = ? LIMIT 1",
        (account_id, account_id),
    ).fetchone():
        raise ValueError("该账户存在交易记录，无法删除")
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


def recalculate_balance(conn: sqlite3.Connection, account_id: int) -> None:
    """根据交易记录重新计算账户当前余额。"""
    account = get_account(conn, account_id)
    if not account:
        return
    balance = float(account["initial_balance"] or 0)
    rows = conn.execute(
        """
        SELECT type, amount, account_id, to_account_id FROM transactions
        WHERE account_id = ? OR to_account_id = ?
        """,
        (account_id, account_id),
    ).fetchall()
    for row in rows:
        amount = float(row["amount"] or 0)
        if row["type"] == "expense" and row["account_id"] == account_id:
            balance -= amount
        elif row["type"] == "income" and row["account_id"] == account_id:
            balance += amount
        elif row["type"] == "transfer":
            if row["account_id"] == account_id:
                balance -= amount
            if row["to_account_id"] == account_id:
                balance += amount
    conn.execute(
        "UPDATE accounts SET current_balance = ? WHERE id = ?",
        (balance, account_id),
    )


def get_account_summary(conn: sqlite3.Connection) -> dict[str, float]:
    """资产汇总：总资产、总负债、净资产。"""
    rows = conn.execute("SELECT is_liability, current_balance FROM accounts").fetchall()
    assets = sum(float(r["current_balance"] or 0) for r in rows if not r["is_liability"])
    liabilities = sum(
        abs(float(r["current_balance"] or 0)) for r in rows if r["is_liability"]
    )
    return {
        "total_assets": assets,
        "total_liabilities": liabilities,
        "net_worth": assets - liabilities,
    }
