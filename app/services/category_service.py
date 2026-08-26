"""交易分类管理。"""
from __future__ import annotations

import sqlite3
from typing import Any


def get_categories(
    conn: sqlite3.Connection, category_type: str | None = None
) -> list[dict[str, Any]]:
    """获取分类，支持按类型筛选，返回树形结构。"""
    if category_type:
        rows = conn.execute(
            "SELECT * FROM transaction_categories WHERE type = ? ORDER BY sort_order, id",
            (category_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM transaction_categories ORDER BY type, sort_order, id"
        ).fetchall()
    items = [dict(row) for row in rows]
    by_id = {item["id"]: item for item in items}
    roots = []
    for item in items:
        item["children"] = []
    for item in items:
        parent = by_id.get(item["parent_id"])
        if parent is not None:
            parent["children"].append(item)
        else:
            roots.append(item)
    return roots


def add_category(
    conn: sqlite3.Connection,
    name: str,
    category_type: str,
    parent_id: int | None = None,
    icon: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO transaction_categories(name, type, parent_id, icon, sort_order)
        VALUES (?, ?, ?, ?, COALESCE((SELECT MAX(sort_order)+1 FROM transaction_categories), 1))
        """,
        (name, category_type, parent_id, icon),
    )
    return int(cur.lastrowid)


def update_category(conn: sqlite3.Connection, category_id: int, **kwargs: Any) -> None:
    allowed = {"name", "type", "parent_id", "icon", "sort_order"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{key} = ?" for key in fields)
    conn.execute(
        f"UPDATE transaction_categories SET {sets} WHERE id = ?",
        (*fields.values(), category_id),
    )


def delete_category(conn: sqlite3.Connection, category_id: int) -> None:
    """删除分类；系统内置分类不可删除。"""
    row = conn.execute(
        "SELECT is_system FROM transaction_categories WHERE id = ?", (category_id,)
    ).fetchone()
    if row and row["is_system"]:
        raise ValueError("系统内置分类不可删除")
    conn.execute("DELETE FROM transaction_categories WHERE id = ?", (category_id,))
