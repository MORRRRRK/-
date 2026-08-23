from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..services import cloud_sync


class CloudSyncWorker(QThread):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        mode: str,
        db_path: Path,
        config: dict[str, str],
        backup_dir: Path,
        parent=None,
    ):
        super().__init__(parent)
        self.mode = mode
        self.db_path = db_path
        self.config = config
        self.backup_dir = backup_dir

    def run(self) -> None:
        try:
            if self.mode == "push":
                result = cloud_sync.push_sync(
                    self.db_path,
                    self.config.get("base_url", ""),
                    self.config.get("username", ""),
                    self.config.get("password", ""),
                    self.config.get("sync_password", ""),
                    self.backup_dir,
                )
            elif self.mode == "pull":
                path = cloud_sync.pull_sync(
                    self.db_path,
                    self.config.get("base_url", ""),
                    self.config.get("username", ""),
                    self.config.get("password", ""),
                    self.config.get("sync_password", ""),
                )
                result = {"restore_path": str(path)}
            elif self.mode == "test":
                message = cloud_sync.test_connection(
                    self.config.get("base_url", ""),
                    self.config.get("username", ""),
                    self.config.get("password", ""),
                )
                result = {"message": message}
            else:
                raise ValueError(f"未知同步模式：{self.mode}")
        except cloud_sync.CloudSyncError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"云同步失败：{exc}")
            return
        self.finished.emit(result)
