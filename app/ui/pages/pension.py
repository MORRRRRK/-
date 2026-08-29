from __future__ import annotations

from PySide6.QtWidgets import (
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..pension_widget import PensionWidget


class PensionPage(QScrollArea):
    """退休金测算：独立页面，全部数据手动填写。"""

    def __init__(self, conn, on_change=None):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self.pension_widget = PensionWidget(conn, on_change)
        layout.addWidget(self.pension_widget)

    def refresh(self) -> None:
        self.pension_widget.refresh()

    def save(self) -> None:
        self.pension_widget.save()

    def undo(self) -> None:
        self.pension_widget.undo()
