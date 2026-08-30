from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ..widgets import (
    Section,
    flash_saved,
    make_button,
    make_money_spin,
    make_save_button,
    make_year_combo,
)


class DepositsPage(QScrollArea):
    """每月强制存款：独立维护，表面按支出记录，实际计入累计存款。"""

    def __init__(self, conn, on_change=None):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()
        self._load_deposits()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.deposit_save_button = make_save_button("保存强制存款")
        self.deposit_save_button.clicked.connect(self._save_deposits)
        section = Section(
            "每月强制存款",
            info="独立维护，表面按支出记录，实际计入累计存款",
            save_actions=[self.deposit_save_button],
        )
        top = QHBoxLayout()
        top.addWidget(QLabel("年份"))
        years = sorted(
            {
                int(y["year"])
                for y in repository.list_years(self.conn)
                if int(y["year"]) >= 2000
            }
            | {QDate.currentDate().year()}
        )
        self.deposit_year_combo = (
            make_year_combo(years) if years else QComboBox()
        )
        self.deposit_year_combo.currentIndexChanged.connect(
            lambda _: self._load_deposits()
        )
        top.addWidget(self.deposit_year_combo)
        top.addStretch(1)
        section.add_layout(top)

        self.deposit_table = QTableWidget(12, 2)
        self.deposit_table.setHorizontalHeaderLabels(["月份", "强制存款"])
        self.deposit_table.verticalHeader().setVisible(False)
        self.deposit_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.deposit_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.deposit_spins: dict[int, QWidget] = {}
        for month in range(1, 13):
            month_item = QTableWidgetItem(f"{month} 月")
            month_item.setTextAlignment(Qt.AlignCenter)
            self.deposit_table.setItem(month - 1, 0, month_item)
            spin = make_money_spin(0.0, 0.0, 1e8)
            self.deposit_spins[month] = spin
            self.deposit_table.setCellWidget(month - 1, 1, spin)
        self.deposit_table.setMinimumHeight(12 * 34 + 34)
        section.add(self.deposit_table)
        layout.addWidget(section)
        layout.addStretch(1)

    def _deposit_year(self) -> int:
        data = self.deposit_year_combo.currentData()
        if data:
            return int(data)
        return QDate.currentDate().year()

    def _load_deposits(self) -> None:
        year = self._deposit_year()
        year_id = repository.ensure_year(self.conn, year)
        records = repository.get_monthly_records(self.conn, year_id)
        for month in range(1, 13):
            rec = records.get(month, {})
            self.deposit_spins[month].setValue(
                float(rec.get("forced_deposit", 0.0) or 0.0)
            )

    def _save_deposits(self) -> None:
        year = self._deposit_year()
        year_id = repository.ensure_year(self.conn, year)
        records = repository.get_monthly_records(self.conn, year_id)
        rows = []
        for month in range(1, 13):
            rec = dict(records.get(month) or {"month": month})
            rec["month"] = month
            rec["forced_deposit"] = float(self.deposit_spins[month].value())
            rows.append(rec)
        repository.upsert_monthly_records(self.conn, year_id, rows)
        self.conn.commit()
        flash_saved(self.deposit_save_button)
        if self.on_change:
            self.on_change()

    def save(self) -> None:
        """全局保存：保存当前年份的每月强制存款。"""
        self._save_deposits()

    def refresh(self) -> None:
        self._load_deposits()
