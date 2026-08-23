"""一次性迁移工具：将 gongzi.xlsx 导入 data/finance.db。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import Database
from app.core.paths import backups_dir
from app.services.importer import MigrationError, import_xlsx


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Z:/04文件/gongzi.xlsx")
    if not source.exists():
        print(f"错误：找不到 {source}")
        return 1

    backup_target = backups_dir() / source.name
    backups_dir().mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, backup_target)
    print(f"已备份 Excel 到 {backup_target}")

    db = Database()
    try:
        report = import_xlsx(db.conn, source)
    except MigrationError as exc:
        print("迁移失败：", exc)
        return 1
    finally:
        db.close()
    print("迁移完成，对账通过：", report["verified"])
    for key, value in report["anchors"].items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
