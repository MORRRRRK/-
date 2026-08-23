import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return app_root() / "data"


def exports_dir() -> Path:
    return app_root() / "exports"


def backups_dir() -> Path:
    return app_root() / "backups"


def db_path() -> Path:
    return data_dir() / "finance.db"


def ensure_dirs() -> None:
    for folder in (data_dir(), exports_dir(), backups_dir()):
        folder.mkdir(parents=True, exist_ok=True)


def asset_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", app_root()))
    return base / "app" / "assets"


def web_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", app_root()))
    return base / "app" / "web"


def images_dir() -> Path:
    return data_dir() / "images"
