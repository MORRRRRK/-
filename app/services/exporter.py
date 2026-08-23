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
        "holdings": repository.list_holdings(conn),
        "gold_accounts": repository.list_gold_accounts(conn),
        "goals": repository.list_goals(conn),
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
