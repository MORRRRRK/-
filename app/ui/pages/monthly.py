from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
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
from ..image_dialog import ImagePreviewDialog
from ..widgets import (
    Section,
    confirm_delete,
    flash_saved,
    line_edit,
    make_button,
    make_money_spin,
    make_year_combo,
    money,
    pct,
)

NUMERIC_COLS = (1, 2, 3, 4, 6, 7, 9)
NOTE_COLS = (5, 8, 10)


class MonthlyPage(QScrollArea):
    def __init__(self, conn, on_change):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._item_ids: list[int] = []
        self._deleted_items: list[dict] = []
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
        self.save_button = make_button("保存本月度流水", primary=True)
        self.save_button.clicked.connect(self._save_monthly)
        top.addWidget(self.save_button)
        layout.addLayout(top)

        summary = Section("年度汇总（自动计算）")
        summary_grid = QGridLayout()
        self.summary_labels: dict[str, QLabel] = {}
        titles = [
            ("salary", "年度工资"),
            ("income", "年度收入"),
            ("housing_cost", "住宿成本"),
            ("balance", "理论结余"),
            ("deposits", "存款"),
            ("savings_rate", "储蓄率"),
        ]
        for idx, (key, title) in enumerate(titles):
            label = QLabel(title)
            label.setObjectName("fieldLabel")
            value = QLabel("-")
            value.setObjectName("summaryValue")
            self.summary_labels[key] = value
            summary_grid.addWidget(label, 0, idx * 2)
            summary_grid.addWidget(value, 0, idx * 2 + 1)
        summary.add_layout(summary_grid)
        layout.addWidget(summary)

        monthly_section = Section("月度流水（负数表示支出或取款，双击图片备注可预览）")

        self.monthly_table = QTableWidget(12, 12)
        self.monthly_table.setHorizontalHeaderLabels(
            [
                "月份",
                "月工资",
                "年终奖",
                "各类补贴",
                "报销",
                "收入备注",
                "房租",
                "水电",
                "住房备注",
                "存款（正=存）",
                "存款备注",
                "图片备注",
            ]
        )
        self.monthly_table.verticalHeader().setVisible(False)
        self.monthly_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.monthly_table.setMinimumHeight(12 * 32 + 34)
        self.monthly_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.monthly_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.monthly_table.setWordWrap(True)
        self.monthly_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.monthly_table.itemChanged.connect(self._resize_rows)
        for row in range(12):
            month_item = QTableWidgetItem(str(row + 1))
            month_item.setTextAlignment(Qt.AlignCenter)
            month_item.setFlags(month_item.flags() & ~Qt.ItemIsEditable)
            self.monthly_table.setItem(row, 0, month_item)
            for col in NUMERIC_COLS + NOTE_COLS + (11,):
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignCenter)
                self.monthly_table.setItem(row, col, item)
        monthly_section.add(self.monthly_table)
        layout.addWidget(monthly_section, 1)

        items_section = Section("其他大笔消费 / 收入")
        form = QGridLayout()
        self.item_type_combo = QComboBox()
        self.item_type_combo.addItem("支出", "expense")
        self.item_type_combo.addItem("收入", "income")
        self.item_type_combo.currentIndexChanged.connect(
            lambda _: self._reload_items(self._current_year_id())
        )
        self.item_date_from = QDateEdit()
        self.item_date_to = QDateEdit()
        for date_edit in (self.item_date_from, self.item_date_to):
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
        self.item_amount_min = make_money_spin(0.0, 0.0, 1e8)
        self.item_amount_max = make_money_spin(1e8, 0.0, 1e8)
        self.item_date_from.dateChanged.connect(
            lambda _: self._reload_items(self._current_year_id())
        )
        self.item_date_to.dateChanged.connect(
            lambda _: self._reload_items(self._current_year_id())
        )
        self.item_amount_min.valueChanged.connect(
            lambda _: self._reload_items(self._current_year_id())
        )
        self.item_amount_max.valueChanged.connect(
            lambda _: self._reload_items(self._current_year_id())
        )
        self.item_add_button = make_button("新增记录", primary=True)
        self.item_update_button = make_button("编辑选中")
        self.item_delete_button = make_button("删除")
        self.item_undo_button = make_button("撤销删除")
        self.item_reset_button = make_button("清除筛选")
        self.item_add_button.clicked.connect(self._add_item)
        self.item_update_button.clicked.connect(self._update_item)
        self.item_delete_button.clicked.connect(self._delete_item)
        self.item_undo_button.clicked.connect(self._undo_item)
        self.item_reset_button.clicked.connect(self._reset_item_filters)
        for col, widget in enumerate(
            [
                QLabel("类型"),
                self.item_type_combo,
                QLabel("日期从"),
                self.item_date_from,
                QLabel("日期到"),
                self.item_date_to,
                QLabel("金额最小"),
                self.item_amount_min,
                QLabel("金额最大"),
                self.item_amount_max,
            ]
        ):
            form.addWidget(widget, 0, col)
        buttons = QHBoxLayout()
        buttons.addWidget(self.item_add_button)
        buttons.addWidget(self.item_update_button)
        buttons.addWidget(self.item_delete_button)
        buttons.addWidget(self.item_undo_button)
        buttons.addWidget(self.item_reset_button)
        buttons.addStretch(1)
        items_section.add_layout(form)
        items_section.add_layout(buttons)
        self.items_table = QTableWidget(0, 5)
        self.items_table.setHorizontalHeaderLabels(["日期", "名称", "金额", "类型", "备注"])
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.items_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.items_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        items_section.add(self.items_table)
        layout.addWidget(items_section, 1)

        self._load_year()

    def _reset_item_filters(self) -> None:
        year = self._current_year()
        self.item_date_from.setDate(QDate(year, 1, 1))
        self.item_date_to.setDate(QDate(year, 12, 31))
        self.item_amount_min.setValue(0.0)
        self.item_amount_max.setValue(1e8)
        self._reload_items(self._current_year_id())

    def _current_year(self) -> int:
        try:
            return int(float(self.year_combo.currentText().strip()))
        except ValueError:
            return 2026

    def _current_year_id(self) -> int:
        return repository.ensure_year(self.conn, self._current_year())

    def _load_year(self) -> None:
        year_id = self._current_year_id()
        year = self._current_year()
        self.item_date_from.blockSignals(True)
        self.item_date_to.blockSignals(True)
        self.item_amount_min.blockSignals(True)
        self.item_amount_max.blockSignals(True)
        try:
            self.item_date_from.setDate(QDate(year, 1, 1))
            self.item_date_to.setDate(QDate(year, 12, 31))
            self.item_amount_min.setValue(0.0)
            self.item_amount_max.setValue(1e8)
        finally:
            self.item_date_from.blockSignals(False)
            self.item_date_to.blockSignals(False)
            self.item_amount_min.blockSignals(False)
            self.item_amount_max.blockSignals(False)
        records = repository.get_monthly_records(self.conn, year_id)
        self.monthly_table.blockSignals(True)
        try:
            for row in range(12):
                rec = records.get(row + 1, {})
                for col, key in [
                    (1, "salary"),
                    (2, "year_end_bonus"),
                    (3, "subsidies"),
                    (4, "reimbursements"),
                    (6, "rent"),
                    (7, "utilities"),
                    (9, "forced_deposit"),
                ]:
                    item = self.monthly_table.item(row, col)
                    item.setText(_format_number(rec.get(key, 0.0)))
                for col, key in [
                    (5, "income_note"),
                    (8, "housing_note"),
                    (10, "deposit_note"),
                ]:
                    item = self.monthly_table.item(row, col)
                    item.setText(str(rec.get(key, "")))
                images = repository.list_monthly_images(self.conn, year_id, row + 1)
                image_item = self.monthly_table.item(row, 11)
                image_item.setText(f"{len(images)} 张图片，双击预览" if images else "")
        finally:
            self.monthly_table.blockSignals(False)
        self._reload_items(year_id)
        self._refresh_summary()
        self._resize_rows()

    def _resize_rows(self, *_args) -> None:
        if not hasattr(self, "items_table"):
            return
        self.monthly_table.resizeRowsToContents()
        total = sum(
            self.monthly_table.rowHeight(row) for row in range(12)
        ) + self.monthly_table.horizontalHeader().height() + 4
        self.monthly_table.setMinimumHeight(total)
        self.items_table.resizeRowsToContents()
        item_total = sum(
            self.items_table.rowHeight(row) for row in range(self.items_table.rowCount())
        ) + self.items_table.horizontalHeader().height() + 4
        self.items_table.setMinimumHeight(max(item_total, 4 * 32 + 34))

    def _records_from_table(self) -> list[dict]:
        records = []
        for row in range(12):
            record = {"month": row + 1}
            for col, key in [
                (1, "salary"),
                (2, "year_end_bonus"),
                (3, "subsidies"),
                (4, "reimbursements"),
                (6, "rent"),
                (7, "utilities"),
                (9, "forced_deposit"),
            ]:
                record[key] = _parse_number(self.monthly_table.item(row, col).text())
            for col, key in [
                (5, "income_note"),
                (8, "housing_note"),
                (10, "deposit_note"),
            ]:
                record[key] = self.monthly_table.item(row, col).text().strip()
            if any(record.get(k) for k in (
                "salary", "year_end_bonus", "subsidies", "reimbursements",
                "rent", "utilities", "forced_deposit",
            )) or any(record.get(k) for k in ("income_note", "housing_note", "deposit_note")):
                records.append(record)
        return records

    def _save_monthly(self) -> None:
        year_id = self._current_year_id()
        repository.upsert_monthly_records(self.conn, year_id, self._records_from_table())
        self.conn.commit()
        self._refresh_summary()
        flash_saved(self.save_button)
        self.on_change()

    def _refresh_summary(self) -> None:
        summary = calculations.year_summary(self.conn, self._current_year_id())
        values = {
            "salary": money(summary["salary"]),
            "income": money(summary["income"]),
            "housing_cost": money(summary["housing_cost"]),
            "balance": money(summary["balance"]),
            "deposits": money(summary["deposits"]),
            "savings_rate": pct(summary["savings_rate"]),
        }
        for key, value in values.items():
            self.summary_labels[key].setText(value)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col == 11:
            self._open_image_dialog(row=row)

    def _open_image_dialog(self, row: int | None = None) -> None:
        selected = self.monthly_table.currentRow() if row is None else row
        if selected < 0:
            QMessageBox.information(self, "提示", "请先选择要操作的行（月份）")
            return
        dialog = ImagePreviewDialog(
            self.conn,
            self._current_year_id(),
            selected + 1,
            self._reload_image_column,
            self,
        )
        dialog.exec()

    def _reload_image_column(self) -> None:
        year_id = self._current_year_id()
        for row in range(12):
            images = repository.list_monthly_images(self.conn, year_id, row + 1)
            item = self.monthly_table.item(row, 11)
            item.setText(f"{len(images)} 张图片，双击预览" if images else "")

    def _reload_items(self, year_id: int) -> None:
        item_type = self.item_type_combo.currentData()
        start = self._item_date_key(self.item_date_from.date())
        end = self._item_date_key(self.item_date_to.date())
        amount_min = float(self.item_amount_min.value())
        amount_max = float(self.item_amount_max.value())
        items = [
            item
            for item in repository.get_large_items(self.conn, year_id)
            if item["item_type"] == item_type
            and amount_min <= item["amount"] <= amount_max
            and _in_date_range(item["item_date"], start, end)
        ]
        self._item_ids = [item["id"] for item in items]
        self.items_table.setRowCount(len(items))
        self.items_table.setMinimumHeight(max(4, len(items)) * 32 + 34)
        for r, item in enumerate(items):
            values = [
                item["item_date"],
                item["name"],
                money(item["amount"]),
                "收入" if item["item_type"] == "income" else "支出",
                item["note"],
            ]
            for c, text in enumerate(values):
                table_item = QTableWidgetItem(str(text))
                table_item.setTextAlignment(
                    Qt.AlignRight | Qt.AlignVCenter
                    if c == 2
                    else Qt.AlignLeft | Qt.AlignVCenter
                )
                self.items_table.setItem(r, c, table_item)
        self.items_table.resizeColumnsToContents()
        self._resize_rows()

    @staticmethod
    def _item_date_key(date: QDate) -> tuple[int, int]:
        return date.month(), date.day()

    def _selected_item(self) -> dict | None:
        row = self.items_table.currentRow()
        if row < 0 or row >= len(self._item_ids):
            return None
        item_id = self._item_ids[row]
        for item in repository.get_large_items(self.conn, self._current_year_id()):
            if item["id"] == item_id:
                return item
        return None

    def _add_item(self) -> None:
        dialog = LargeItemDialog(self.item_type_combo.currentData(), self)
        if dialog.exec() != QDialog.Accepted:
            return
        repository.add_large_item(self.conn, self._current_year_id(), dialog.values())
        self.conn.commit()
        self._reload_items(self._current_year_id())
        self.on_change()

    def _update_item(self) -> None:
        item = self._selected_item()
        if item is None:
            QMessageBox.information(self, "提示", "请先在表格中选择一条记录")
            return
        dialog = LargeItemDialog(item["item_type"], self, item)
        if dialog.exec() != QDialog.Accepted:
            return
        repository.update_large_item(self.conn, item["id"], dialog.values())
        self.conn.commit()
        self._reload_items(self._current_year_id())
        self.on_change()

    def _delete_item(self) -> None:
        row = self.items_table.currentRow()
        if row < 0 or row >= len(self._item_ids):
            return
        item = None
        for record in repository.get_large_items(self.conn, self._current_year_id()):
            if record["id"] == self._item_ids[row]:
                item = record
                break
        if item is None or not confirm_delete(self, "删除记录", f"确定删除“{item['name']}”？"):
            return
        repository.delete_large_item(self.conn, self._item_ids[row])
        self._deleted_items.append(item)
        self.conn.commit()
        self._reload_items(self._current_year_id())
        self.on_change()

    def _undo_item(self) -> None:
        if not self._deleted_items:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        item = self._deleted_items.pop()
        index = self.item_type_combo.findData(item["item_type"])
        self.item_type_combo.setCurrentIndex(max(0, index))
        new_id = repository.add_large_item(self.conn, self._current_year_id(), item)
        self.conn.commit()
        self._reload_items(self._current_year_id())
        if new_id in self._item_ids:
            row = self._item_ids.index(new_id)
            self.items_table.setCurrentCell(row, 0)
        self.on_change()

    def refresh(self) -> None:
        self._load_year()


def _parse_number(text: str) -> float:
    text = text.strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _format_number(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.2f}"


def _in_date_range(
    item_date: str, start: tuple[int, int], end: tuple[int, int]
) -> bool:
    key = _parse_item_date(item_date)
    if key is None:
        return True
    return start <= key <= end


def _parse_item_date(text: str) -> tuple[int, int] | None:
    text = text.strip().replace("月", ".").replace("日", "")
    if not text:
        return None
    parts = text.replace("-", ".").split(".")
    try:
        month = int(float(parts[0]))
        day = int(float(parts[1])) if len(parts) > 1 else 1
    except (ValueError, IndexError):
        return None
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return month, day


class LargeItemDialog(QDialog):
    def __init__(self, item_type: str, parent=None, item: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("编辑大笔消费 / 收入")
        self.setMinimumWidth(420)
        layout = QGridLayout(self)

        self.type_combo = QComboBox()
        self.type_combo.addItem("支出", "expense")
        self.type_combo.addItem("收入", "income")
        index = self.type_combo.findData(item_type)
        self.type_combo.setCurrentIndex(max(0, index))
        self.date_edit = line_edit(placeholder="如 8.15")
        self.name_edit = line_edit(placeholder="名称")
        self.amount_spin = make_money_spin()
        self.note_edit = line_edit(placeholder="备注")

        fields = [
            ("类型", self.type_combo),
            ("日期", self.date_edit),
            ("名称", self.name_edit),
            ("金额", self.amount_spin),
            ("备注", self.note_edit),
        ]
        for row, (title, widget) in enumerate(fields):
            label = QLabel(title)
            label.setObjectName("fieldLabel")
            layout.addWidget(label, row, 0)
            layout.addWidget(widget, row, 1)

        if item:
            index = self.type_combo.findData(item["item_type"])
            self.type_combo.setCurrentIndex(max(0, index))
            self.date_edit.setText(item["item_date"])
            self.name_edit.setText(item["name"])
            self.amount_spin.setValue(item["amount"])
            self.note_edit.setText(item["note"])

        buttons = QHBoxLayout()
        self.ok_button = make_button("确定", primary=True)
        self.cancel_button = make_button("取消")
        self.ok_button.clicked.connect(self._accept)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(self.ok_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons, len(fields), 0, 1, 2)

    def _accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "请填写名称")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "item_type": self.type_combo.currentData(),
            "item_date": self.date_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "amount": float(self.amount_spin.value()),
            "note": self.note_edit.text().strip(),
        }
