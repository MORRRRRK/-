"""把旧 large_items/monthly_images 数据迁移到新的 transactions 表。"""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.core import paths, repository
from app.services import account_service, category_service, transaction_service


def backup_database() -> Path:
    source = paths.db_path()
    backup_dir = paths.backups_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"pre_transactions_migrate_{stamp}.db"
    shutil.copy2(source, target)
    return target


def migrate(conn: sqlite3.Connection) -> dict:
    stats = {"large_items": 0, "images": 0}
    accounts = account_service.get_accounts(conn)
    if not accounts:
        account_id = account_service.add_account(
            conn, "默认账户", "other", initial_balance=0.0
        )
    else:
        account_id = accounts[0]["id"]

    categories = category_service.get_categories(conn, "expense")
    other_id = None
    for category in categories:
        if category["name"] == "其他支出":
            other_id = category["id"]
            break
    if other_id is None:
        other_id = category_service.add_category(conn, "其他支出", "expense")

    years = {year["id"]: year["year"] for year in repository.list_years(conn)}
    for item in conn.execute("SELECT * FROM large_items").fetchall():
        item = dict(item)
        year = years.get(item["year_id"], datetime.now().year)
        trans_type = "income" if item["item_type"] == "income" else "expense"
        trans_date = item["item_date"] or f"{year}-01-01"
        transaction_service.add_transaction(
            conn,
            trans_date=trans_date,
            trans_type=trans_type,
            amount=abs(float(item["amount"] or 0)),
            category_id=other_id,
            account_id=account_id,
            merchant=item["name"],
            note=item["note"],
        )
        stats["large_items"] += 1

    image_rows = conn.execute("SELECT * FROM monthly_images").fetchall()
    for image in image_rows:
        image = dict(image)
        year = years.get(image["year_id"])
        month = image["month"]
        if not year:
            continue
        start = f"{year:04d}-{month:02d}-01"
        end = f"{year:04d}-{month:02d}-31"
        rows = transaction_service.get_transactions(conn, start, end)
        if rows:
            transaction_service.update_transaction(
                conn, rows[-1]["id"], image_path=image["file_path"]
            )
            stats["images"] += 1
    conn.commit()
    return stats


def main() -> None:
    backup = backup_database()
    conn = sqlite3.connect(str(paths.db_path()))
    conn.row_factory = sqlite3.Row
    stats = migrate(conn)
    conn.close()
    print(f"迁移完成：large_items {stats['large_items']} 条，图片 {stats['images']} 条")
    print(f"备份文件：{backup}")


if __name__ == "__main__":
    main()
