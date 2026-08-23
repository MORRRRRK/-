from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..services.updater import (
    UpdaterError,
    check_for_update,
    launch_updater,
    prepare_update,
)


class UpdateCheckWorker(QThread):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, repo: str, parent=None):
        super().__init__(parent)
        self.repo = repo

    def run(self) -> None:
        try:
            info = check_for_update(self.repo)
        except UpdaterError as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(info)


class UpdateInstallWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, conn, info: dict, backup_dir: Path, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.info = info
        self.backup_dir = backup_dir

    def run(self) -> None:
        try:
            job_path, helper = prepare_update(self.conn, self.info, self.backup_dir)
            launch_updater(job_path, helper)
        except UpdaterError as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(str(self.info.get("version", "")))
