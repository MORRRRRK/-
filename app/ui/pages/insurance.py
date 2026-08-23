from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...services import calculations
from ..widgets import (
    NoWheelSpinBox,
    Section,
    confirm_delete,
    flash_saved,
    make_button,
    make_money_spin,
    make_year_combo,
    money,
)


class InsurancePage(QScrollArea):
    def __init__(self, conn, on_change):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._deleted_rows: list[dict] = []
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(QLabel("年份"))
        years = [y["year"] for y in repository.list_years(self.conn)]
        self.year_combo = make_year_combo(years) if years else QComboBox()
        self.year_combo.setEditable(True)
        self.year_combo.lineEdit().setValidator(QIntValidator(1900, 2100))
        self.year_combo.setFixedWidth(120)
        self.year_combo.currentTextChanged.connect(self._load_year)
        top.addWidget(self.year_combo)
        top.addStretch(1)
        self.add_item_button = make_button("新增险种")
        self.delete_item_button = make_button("删除选中行")
        self.undo_delete_button = make_button("撤销删除")
        self.save_button = make_button("保存工资参数", primary=True)
        self.add_item_button.clicked.connect(self._add_item_row)
        self.delete_item_button.clicked.connect(self._delete_item_row)
        self.undo_delete_button.clicked.connect(self._undo_delete_row)
        self.save_button.clicked.connect(self._save)
        top.addWidget(self.add_item_button)
        top.addWidget(self.delete_item_button)
        top.addWidget(self.undo_delete_button)
        top.addWidget(self.save_button)
        layout.addLayout(top)

        salary_section = Section("月工资 / 13薪 / 年终奖")
        salary_grid = QGridLayout()
        salary_grid.setHorizontalSpacing(20)
        salary_grid.setVerticalSpacing(10)

        self.monthly_spin = make_money_spin()
        self.thirteenth_spin = make_money_spin()
        self.thirteenth_months_spin = self._count_spin(1.0)
        self.bonus_spin = make_money_spin()
        self.bonus_months_spin = self._count_spin(1.0)
        self.subsidy_spin = make_money_spin()

        widgets = [
            ("月工资", self.monthly_spin),
            ("13薪金额", self.thirteenth_spin),
            ("13薪月数", self.thirteenth_months_spin),
            ("年终奖金额", self.bonus_spin),
            ("年终奖月数", self.bonus_months_spin),
            ("租房补贴", self.subsidy_spin),
        ]
        for col, (title, widget) in enumerate(widgets):
            salary_grid.addWidget(QLabel(title), 0, col * 2)
            salary_grid.addWidget(widget, 0, col * 2 + 1)
        salary_section.add_layout(salary_grid)
        layout.addWidget(salary_section)

        items_section = Section("五险一金 / 其他险种（可自定义添加）")
        self.items_table = QTableWidget(0, 5)
        self.items_table.setHorizontalHeaderLabels(
            ["名称", "基数", "个人比例(%)", "公司比例(%)", "个人固定金额"]
        )
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.items_table.itemChanged.connect(self._refresh_result)
        items_section.add(self.items_table)
        layout.addWidget(items_section, 1)

        result_section = Section("自动计算结果")
        result_grid = QGridLayout()
        self.result_labels: dict[str, QLabel] = {}
        for idx, (key, title) in enumerate(
            [
                ("personal_total", "个人缴纳合计（月）"),
                ("company_total", "公司缴纳合计（月）"),
                ("gross_income", "税前总收入（年）"),
                ("total_package", "总包（年）"),
            ]
        ):
            label = QLabel(title)
            label.setObjectName("fieldLabel")
            value = QLabel("-")
            value.setObjectName("summaryValue")
            self.result_labels[key] = value
            result_grid.addWidget(label, 0, idx * 2)
            result_grid.addWidget(value, 0, idx * 2 + 1)
        result_section.add_layout(result_grid)
        layout.addWidget(result_section)
        layout.addStretch(1)

        self._load_year()

    @staticmethod
    def _count_spin(value: float) -> NoWheelSpinBox:
        spin = NoWheelSpinBox()
        spin.setDecimals(0)
        spin.setRange(0, 24)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignRight)
        return spin

    def _current_year(self) -> int:
        try:
            return int(float(self.year_combo.currentText().strip()))
        except ValueError:
            return 2026

    def _load_year(self) -> None:
        year_id = repository.ensure_year(self.conn, self._current_year())
        params = repository.get_insurance_params(self.conn, year_id) or {}
        self.monthly_spin.setValue(float(params.get("monthly_salary") or 12266.0))
        self.thirteenth_spin.setValue(
            float(params.get("thirteenth_amount") or params.get("monthly_salary") or 12266.0)
        )
        self.thirteenth_months_spin.setValue(
            float(params.get("thirteenth_month_months") or 1.0)
        )
        self.bonus_spin.setValue(
            float(params.get("year_end_bonus_amount") or params.get("monthly_salary") or 12266.0)
        )
        self.bonus_months_spin.setValue(float(params.get("year_end_bonus_months") or 1.0))
        self.subsidy_spin.setValue(float(params.get("housing_subsidy") or 750.0))

        self.items_table.blockSignals(True)
        self.items_table.setRowCount(0)
        for item in repository.list_insurance_items(self.conn, year_id):
            self._append_item_row(item)
        self.items_table.blockSignals(False)
        self._refresh_result()

    def _append_item_row(self, item: dict | None = None) -> None:
        self.items_table.blockSignals(True)
        try:
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)
            values = [
                item.get("name", "") if item else "自定义险种",
                f"{float(item.get('base') or 0):.2f}" if item else "0",
                f"{float(item.get('personal_rate') or 0) * 100:.2f}" if item else "0",
                f"{float(item.get('company_rate') or 0) * 100:.2f}" if item else "0",
                (
                    f"{float(item['personal_fixed']):.2f}"
                    if item and item.get("personal_fixed") is not None
                    else ""
                ),
            ]
            for col, text in enumerate(values):
                table_item = QTableWidgetItem(text)
                table_item.setTextAlignment(Qt.AlignCenter)
                self.items_table.setItem(row, col, table_item)
        finally:
            self.items_table.blockSignals(False)

    def _add_item_row(self) -> None:
        self._append_item_row()
        self.items_table.setCurrentCell(self.items_table.rowCount() - 1, 0)
        self._refresh_result()

    def _delete_item_row(self) -> None:
        row = self.items_table.currentRow()
        if row < 0:
            return
        item = self._item_from_row(row)
        if not confirm_delete(self, "删除险种", f"确定删除“{item['name']}”？"):
            return
        self._deleted_rows.append(item)
        self.items_table.removeRow(row)
        self._refresh_result()

    def _undo_delete_row(self) -> None:
        if not self._deleted_rows:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        self._append_item_row(self._deleted_rows.pop())
        self._refresh_result()

    def _item_from_row(self, row: int) -> dict:
        fixed_text = self.items_table.item(row, 4).text().strip()
        return {
            "name": self.items_table.item(row, 0).text().strip(),
            "base": _parse_float(self.items_table.item(row, 1).text()),
            "personal_rate": _parse_float(self.items_table.item(row, 2).text()) / 100.0,
            "company_rate": _parse_float(self.items_table.item(row, 3).text()) / 100.0,
            "personal_fixed": _parse_float(fixed_text) if fixed_text else None,
        }

    def _salary_params(self) -> dict:
        return {
            "base": 0.0,
            "monthly_salary": float(self.monthly_spin.value()),
            "thirteenth_month_months": float(self.thirteenth_months_spin.value()),
            "year_end_bonus_months": float(self.bonus_months_spin.value()),
            "thirteenth_amount": float(self.thirteenth_spin.value()),
            "year_end_bonus_amount": float(self.bonus_spin.value()),
            "housing_subsidy": float(self.subsidy_spin.value()),
            "housing_fund_personal_rate": 0.0,
            "housing_fund_company_rate": 0.0,
            "pension_personal_rate": 0.0,
            "pension_company_rate": 0.0,
            "medical_personal_rate": 0.0,
            "medical_company_rate": 0.0,
            "big_medical_personal": 0.0,
            "big_medical_company": 0.0,
            "maternity_personal_rate": 0.0,
            "maternity_company_rate": 0.0,
            "injury_personal_rate": 0.0,
            "injury_company_rate": 0.0,
            "unemployment_personal_rate": 0.0,
            "unemployment_company_rate": 0.0,
        }

    def _items_from_table(self) -> list[dict]:
        items = []
        for row in range(self.items_table.rowCount()):
            name = self.items_table.item(row, 0).text().strip()
            if not name:
                continue
            fixed_text = self.items_table.item(row, 4).text().strip()
            items.append(
                {
                    "name": name,
                    "base": _parse_float(self.items_table.item(row, 1).text()),
                    "personal_rate": _parse_float(self.items_table.item(row, 2).text()) / 100.0,
                    "company_rate": _parse_float(self.items_table.item(row, 3).text()) / 100.0,
                    "personal_fixed": (
                        _parse_float(fixed_text) if fixed_text else None
                    ),
                }
            )
        return items

    def _save(self) -> None:
        year_id = repository.ensure_year(self.conn, self._current_year())
        repository.upsert_insurance_params(self.conn, year_id, self._salary_params())
        repository.replace_insurance_items(self.conn, year_id, self._items_from_table())
        self.conn.commit()
        self._refresh_result()
        flash_saved(self.save_button)
        self.on_change()

    def _refresh_result(self) -> None:
        result = calculations.social_insurance_from_data(
            self._salary_params(), self._items_from_table()
        )
        values = {
            "personal_total": money(result["personal_total"]),
            "company_total": money(result["company_total"]),
            "gross_income": money(result["gross_income"]),
            "total_package": money(result["total_package"]),
        }
        for key, text in values.items():
            self.result_labels[key].setText(text)

    def refresh(self) -> None:
        self._load_year()


def _parse_float(text: str) -> float:
    text = text.strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
