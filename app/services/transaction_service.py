"""日常逐笔记账核心业务。"""
from __future__ import annotations

import sqlite3
from typing import Any


def get_transactions(
    conn: sqlite3.Connection,
    start_date: str | None = None,
    end_date: str | None = None,
    category_id: int | None = None,
    account_id: int | None = None,
    trans_type: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """查询交易列表，按日期倒序，支持多条件筛选。"""
    sql = "SELECT * FROM transactions WHERE 1=1"
    params: list[Any] = []
    if start_date:
        sql += " AND trans_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND trans_date <= ?"
        params.append(end_date)
    if category_id:
        sql += " AND category_id = ?"
        params.append(category_id)
    if account_id:
        sql += " AND (account_id = ? OR to_account_id = ?)"
        params.extend([account_id, account_id])
    if trans_type:
        sql += " AND type = ?"
        params.append(trans_type)
    if keyword:
        sql += " AND (merchant LIKE ? OR note LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    sql += " ORDER BY trans_date DESC, id DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_transaction(conn: sqlite3.Connection, transaction_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()
    return dict(row) if row else None


def _adjust_balance(conn: sqlite3.Connection, trans: dict[str, Any], sign: int) -> None:
    amount = float(trans["amount"] or 0) * sign
    if trans["type"] == "expense":
        conn.execute(
            "UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?",
            (amount, trans["account_id"]),
        )
    elif trans["type"] == "income":
        conn.execute(
            "UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?",
            (amount, trans["account_id"]),
        )
    elif trans["type"] == "transfer":
        conn.execute(
            "UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?",
            (amount, trans["account_id"]),
        )
        if trans.get("to_account_id"):
            conn.execute(
                "UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?",
                (amount, trans["to_account_id"]),
            )


def add_transaction(
    conn: sqlite3.Connection,
    trans_date: str,
    trans_type: str,
    amount: float,
    category_id: int | None,
    account_id: int,
    to_account_id: int | None = None,
    merchant: str = "",
    note: str = "",
    image_path: str = "",
    is_reimbursable: int = 0,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO transactions(
          trans_date, type, amount, category_id, account_id, to_account_id,
          merchant, note, image_path, is_reimbursable
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trans_date, trans_type, amount, category_id, account_id, to_account_id,
            merchant, note, image_path, is_reimbursable,
        ),
    )
    trans = {
        "type": trans_type,
        "amount": amount,
        "account_id": account_id,
        "to_account_id": to_account_id,
    }
    _adjust_balance(conn, trans, 1)
    return int(cur.lastrowid)


def update_transaction(
    conn: sqlite3.Connection, transaction_id: int, **kwargs: Any
) -> None:
    """更新交易：先回滚旧交易余额影响，再应用新交易。"""
    old = get_transaction(conn, transaction_id)
    if not old:
        raise ValueError("交易不存在")
    _adjust_balance(conn, old, -1)
    allowed = {
        "trans_date", "type", "amount", "category_id", "account_id",
        "to_account_id", "merchant", "note", "image_path", "is_reimbursable",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{key} = ?" for key in fields)
    conn.execute(
        f"UPDATE transactions SET {sets} WHERE id = ?",
        (*fields.values(), transaction_id),
    )
    new = get_transaction(conn, transaction_id)
    if new:
        _adjust_balance(conn, new, 1)


def delete_transaction(conn: sqlite3.Connection, transaction_id: int) -> None:
    """删除交易并回滚余额影响。"""
    trans = get_transaction(conn, transaction_id)
    if not trans:
        return
    _adjust_balance(conn, trans, -1)
    conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


def get_monthly_summary(
    conn: sqlite3.Connection, year: int, month: int
) -> dict[str, float]:
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year:04d}-{month:02d}-31"
    rows = get_transactions(conn, start, end)
    income = sum(r["amount"] for r in rows if r["type"] == "income")
    expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    return {"income": income, "expense": expense, "balance": income - expense}


def get_yearly_summary(conn: sqlite3.Connection, year: int) -> dict[str, float]:
    start = f"{year:04d}-01-01"
    end = f"{year:04d}-12-31"
    rows = get_transactions(conn, start, end)
    income = sum(r["amount"] for r in rows if r["type"] == "income")
    expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    return {"income": income, "expense": expense, "balance": income - expense}


def get_category_summary(
    conn: sqlite3.Connection, start_date: str, end_date: str, trans_type: str = "expense"
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.name, COALESCE(SUM(t.amount), 0) AS total
        FROM transactions t
        LEFT JOIN transaction_categories c ON t.category_id = c.id
        WHERE t.type = ? AND t.trans_date BETWEEN ? AND ?
        GROUP BY c.name ORDER BY total DESC
        """,
        (trans_type, start_date, end_date),
    ).fetchall()
    return [dict(r) for r in rows]


def get_daily_trend(
    conn: sqlite3.Connection, start_date: str, end_date: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT trans_date,
          COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END), 0) AS income,
          COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expense
        FROM transactions
        WHERE trans_date BETWEEN ? AND ?
        GROUP BY trans_date ORDER BY trans_date
        """,
        (start_date, end_date),
    ).fetchall()
    return [dict(r) for r in rows]


def search_transactions(
    conn: sqlite3.Connection, keyword: str
) -> list[dict[str, Any]]:
    return get_transactions(conn, keyword=keyword)
