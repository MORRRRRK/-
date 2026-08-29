from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...services import salary as salary_service
from ..pension_widget import PensionWidget


class PensionPage(QScrollArea):
    """退休金测算：独立页面，可选择工资方案自动填充缴费基数。"""

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

        selector = QHBoxLayout()
        selector.addWidget(QLabel("工资方案"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(220)
        self.profile_combo.currentIndexChanged.connect(
            lambda _: self._apply_payload()
        )
        selector.addWidget(self.profile_combo)
        selector.addStretch(1)
        layout.addLayout(selector)

        self.pension_widget = PensionWidget(conn, on_change)
        layout.addWidget(self.pension_widget)
        self.refresh()

    def refresh(self) -> None:
        profiles = repository.list_open_salary_profiles(self.conn)
        current = self.profile_combo.currentData()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for profile in profiles:
            self.profile_combo.addItem(profile["name"], profile["id"])
        if profiles:
            index = self.profile_combo.findData(current)
            self.profile_combo.setCurrentIndex(max(0, index))
        self.profile_combo.blockSignals(False)
        self._apply_payload()
        self.pension_widget.refresh()

    def _apply_payload(self) -> None:
        profile_id = self.profile_combo.currentData()
        if profile_id is None:
            self.pension_widget.set_salary_payload(None)
            return
        profile = repository.get_salary_profile(self.conn, profile_id)
        if profile is None:
            self.pension_widget.set_salary_payload(None)
            return
        self.pension_widget.set_salary_payload(
            salary_service.decode_payload(profile.get("payload"))
        )

    def save(self) -> None:
        self.pension_widget._save_pension_jobs()

    def undo(self) -> None:
        self.pension_widget._undo_pension_delete()
