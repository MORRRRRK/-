from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..services import release


class ReleasePushWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        version: str,
        repo: str,
        token: str,
        notes: str,
        customer_only: bool = False,
        build_first: bool = True,
        code_repo: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.version = version
        self.repo = repo
        self.token = token
        self.notes = notes
        self.customer_only = customer_only
        self.build_first = build_first
        self.code_repo = code_repo

    def run(self) -> None:
        try:
            url = release.publish(
                self.version,
                self.repo,
                self.token,
                self.notes,
                self.customer_only,
                self.build_first,
                self.code_repo,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(url)
