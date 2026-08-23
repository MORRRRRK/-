"""开发版 / 客户版标识。客户版通过 edition.ini 启用。"""
from __future__ import annotations

from .core import paths


def is_customer() -> bool:
    ini = paths.app_root() / "edition.ini"
    if not ini.exists():
        return False
    try:
        return "customer" in ini.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def edition_label() -> str:
    return "客户版" if is_customer() else "开发版"
