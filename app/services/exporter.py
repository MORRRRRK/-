"""数据库备份与 CSV 导出。"""
from __future__ import annotations

import csv
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from ..core import repository


def backup_database(db_path: Path, backups_dir: Path) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backups_dir / f"finance_{stamp}.db"
    shutil.copy2(db_path, target)
    return target


def export_csv(conn: sqlite3.Connection, exports_dir: Path) -> list[Path]:
    exports_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    tables = {
        "years": repository.list_years(conn),
        "monthly_records": [
            dict(r)
            for r in conn.execute("SELECT * FROM monthly_records ORDER BY year_id, month")
        ],
        "large_items": [
            dict(r)
            for r in conn.execute("SELECT * FROM large_items ORDER BY year_id, id")
        ],
        "social_insurance_params": [
            dict(r)
            for r in conn.execute("SELECT * FROM social_insurance_params ORDER BY year_id")
        ],
        "tax_params": [
            dict(r)
            for r in conn.execute("SELECT * FROM tax_params ORDER BY year_id")
        ],
        "salary_items": [
            dict(r)
            for r in conn.execute("SELECT * FROM salary_items ORDER BY year_id, id")
        ],
        "holdings": repository.list_holdings(conn),
        "gold_accounts": repository.list_gold_accounts(conn),
        "goals": repository.list_goals(conn),
        "pension_jobs": repository.list_pension_jobs(conn),
        "ai_reports": repository.list_ai_reports(conn),
    }
    for name, rows in tables.items():
        path = exports_dir / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            if not rows:
                fh.write("")
                continue
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        written.append(path)
    return written


def export_transactions(
    conn: sqlite3.Connection, start_date: str, end_date: str, file_path: Path
) -> Path:
    """导出指定日期范围内的交易记录为 CSV。"""
    from . import transaction_service

    rows = transaction_service.get_transactions(conn, start_date, end_date)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", newline="", encoding="utf-8-sig") as fh:
        if not rows:
            fh.write("")
            return file_path
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return file_path


def export_accounts(conn: sqlite3.Connection, file_path: Path) -> Path:
    """导出账户列表为 CSV。"""
    from . import account_service

    rows = account_service.get_accounts(conn)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", newline="", encoding="utf-8-sig") as fh:
        if not rows:
            fh.write("")
            return file_path
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return file_path


def export_bluecoins_csv(
    conn: sqlite3.Connection, start_date: str, end_date: str, file_path: Path
) -> int:
    """按 BlueCoins 中文 CSV 格式导出交易记录。"""
    from . import account_service, transaction_service

    rows = transaction_service.get_transactions(conn, start_date, end_date)
    categories = {
        c["id"]: dict(c)
        for c in conn.execute("SELECT * FROM transaction_categories")
    }
    accounts = {
        a["id"]: a["name"] for a in account_service.get_accounts(conn)
    }
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "类型", "日期", "设置时间", "名称", "金额", "货币", "汇率",
                "类别组", "类别", "账户", "备注", "标签", "状态",
            ]
        )
        for row in rows:
            trans_type = {
                "expense": "支出",
                "income": "收入",
                "transfer": "转账",
            }.get(row["type"], row["type"])
            amount = abs(float(row["amount"] or 0))
            if trans_type == "支出":
                signed = -amount
            elif trans_type == "收入":
                signed = amount
            else:
                signed = float(row["amount"] or 0)
            category = categories.get(row["category_id"])
            group_name = ""
            if category:
                if category.get("parent_id"):
                    parent = categories.get(category["parent_id"]) or {}
                    group_name = parent.get("name", "")
                else:
                    group_name = category.get("name", "")
            writer.writerow(
                [
                    trans_type,
                    row["trans_date"],
                    row.get("created_at") or row["trans_date"],
                    row["merchant"],
                    f"{signed:.2f}",
                    "CNY",
                    "1",
                    group_name,
                    category.get("name", "") if category else "",
                    accounts.get(row["account_id"], ""),
                    row["note"],
                    "",
                    "",
                ]
            )
    return len(rows)
