from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...services import account_service, transaction_service
from ..widgets import (
    Section,
    StatCard,
    confirm_delete,
    flash_saved,
    line_edit,
    make_button,
    make_money_spin,
    money,
)


class SpendingPlansPage(QWidget):
    """消费计划：多个大项计划，每个计划按分项归集实际流水。"""

    def __init__(self, conn, on_change=None):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._plan_ids: list[int] = []
        self._item_ids: list[int | None] = []
        self._deleted_items: list[dict] = []
        self._deleted_plan: dict | None = None
        self._current_plan_id: int | None = None
        self._build()
        self._reload_plans()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("计划"))
        self.plan_combo = QComboBox()
        self.plan_combo.setMinimumWidth(220)
        self.plan_combo.currentIndexChanged.connect(
            lambda _: self._load_plan()
        )
        toolbar.addWidget(self.plan_combo)
        self.add_plan_button = make_button("新增计划", primary=True)
        self.rename_plan_button = make_button("重命名")
        self.delete_plan_button = make_button("删除计划")
        self.undo_plan_button = make_button("撤销删除")
        self.add_plan_button.clicked.connect(self._add_plan)
        self.rename_plan_button.clicked.connect(self._rename_plan)
        self.delete_plan_button.clicked.connect(self._delete_plan)
        self.undo_plan_button.clicked.connect(self._undo_plan)
        toolbar.addWidget(self.add_plan_button)
        toolbar.addWidget(self.rename_plan_button)
        toolbar.addWidget(self.delete_plan_button)
        toolbar.addWidget(self.undo_plan_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.plan_save_button = make_button("保存计划信息", primary=True)
        self.plan_save_button.clicked.connect(self._save_plan)
        plan_section = Section(
            "计划信息",
            actions=[self.plan_save_button],
            info="日期范围为选填，填写后用于关联流水时默认筛选时间段",
        )
        form = QHBoxLayout()
        form.addWidget(QLabel("名称"))
        self.plan_name_edit = line_edit(placeholder="例如：国庆旅行 / 买相机 / 养猫")
        self.plan_name_edit.setMinimumWidth(220)
        form.addWidget(self.plan_name_edit)
        form.addWidget(QLabel("总预算"))
        self.budget_spin = make_money_spin(0.0, 0.0, 1e9)
        form.addWidget(self.budget_spin)

        self.start_check = QCheckBox("开始日期")
        self.start_date_edit = QDateEdit(QDate.currentDate())
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setEnabled(False)
        self.start_check.toggled.connect(self.start_date_edit.setEnabled)
        self.end_check = QCheckBox("结束日期")
        self.end_date_edit = QDateEdit(QDate.currentDate())
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setEnabled(False)
        self.end_check.toggled.connect(self.end_date_edit.setEnabled)
        form.addWidget(self.start_check)
        form.addWidget(self.start_date_edit)
        form.addWidget(self.end_check)
        form.addWidget(self.end_date_edit)
        form.addStretch(1)
        plan_section.add_layout(form)
        form2 = QHBoxLayout()
        form2.addWidget(QLabel("备注"))
        self.plan_note_edit = line_edit(placeholder="可留空")
        form2.addWidget(self.plan_note_edit, 1)
        plan_section.add_layout(form2)
        layout.addWidget(plan_section)

        cards = QHBoxLayout()
        self.actual_card = StatCard("实际总花费", info="已关联流水金额 + 手动补录金额")
        self.planned_card = StatCard("计划总金额", info="所有分项计划金额合计")
        self.remaining_card = StatCard("剩余预算", info="总预算 - 实际总花费；未填预算时不计算")
        self.link_card = StatCard("关联笔数", info="从记账流水勾选归集到本计划的交易笔数")
        for card in (
            self.actual_card,
            self.planned_card,
            self.remaining_card,
            self.link_card,
        ):
            cards.addWidget(card)
        layout.addLayout(cards)

        self.add_item_button = make_button("新增分项")
        self.delete_item_button = make_button("删除选中")
        self.undo_item_button = make_button("撤销删除")
        self.save_items_button = make_button("保存分项", primary=True)
        self.add_item_button.clicked.connect(self._add_item)
        self.delete_item_button.clicked.connect(self._delete_item)
        self.undo_item_button.clicked.connect(self._undo_item)
        self.save_items_button.clicked.connect(self._save_items)
        items_section = Section(
            "分项与关联流水",
            actions=[
                self.add_item_button,
                self.delete_item_button,
                self.undo_item_button,
                self.save_items_button,
            ],
            info="每个分项可单独关联记账流水，实际金额 = 关联流水合计 + 手动补录",
        )

        self.items_table = QTableWidget(0, 7)
        self.items_table.setHorizontalHeaderLabels(
            [
                "分项名称",
                "手动补录",
                "计划金额",
                "实际金额",
                "关联笔数",
                "备注",
                "操作",
            ]
        )
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.items_table.setMinimumHeight(6 * 32 + 34)
        items_section.add(self.items_table)
        layout.addWidget(items_section, 1)

    def _reload_plans(self) -> None:
        plans = repository.list_spending_plans(self.conn)
        if not plans:
            repository.add_spending_plan(self.conn, "新计划")
            self.conn.commit()
            plans = repository.list_spending_plans(self.conn)
        current = self.plan_combo.currentData()
        self.plan_combo.blockSignals(True)
        self.plan_combo.clear()
        self._plan_ids = []
        for plan in plans:
            self.plan_combo.addItem(plan["name"], plan["id"])
            self._plan_ids.append(plan["id"])
        index = self.plan_combo.findData(current)
        if index < 0:
            index = self.plan_combo.count() - 1
        self.plan_combo.setCurrentIndex(max(0, index))
        self.plan_combo.blockSignals(False)
        self._load_plan()

    def _current_plan(self) -> dict | None:
        plan_id = self.plan_combo.currentData()
        if plan_id is None:
            return None
        return repository.get_spending_plan(self.conn, plan_id)

    def _load_plan(self) -> None:
        plan = self._current_plan()
        if plan is None:
            self._current_plan_id = None
            return
        self._current_plan_id = int(plan["id"])
        self.plan_name_edit.setText(plan.get("name", ""))
        self.budget_spin.setValue(float(plan.get("total_budget") or 0.0))
        start = str(plan.get("start_date") or "")
        end = str(plan.get("end_date") or "")
        self.start_check.setChecked(bool(start))
        self.end_check.setChecked(bool(end))
        if start:
            self.start_date_edit.setDate(
                QDate.fromString(start, "yyyy-MM-dd")
            )
        if end:
            self.end_date_edit.setDate(QDate.fromString(end, "yyyy-MM-dd"))
        self.plan_note_edit.setText(plan.get("note", ""))

        summary = repository.spending_plan_summary(
            self.conn, self._current_plan_id
        )
        self.actual_card.set_value(money(summary["total_actual"]), "")
        self.planned_card.set_value(money(summary["total_planned"]), "")
        budget = summary["budget"]
        if budget > 0:
            self.remaining_card.set_value(
                money(summary["remaining"]),
                "总预算 " + money(budget),
            )
        else:
            self.remaining_card.set_value("未设置", "未填写总预算")
        self.link_card.set_value(str(summary["total_links"]), "")

        self._item_ids = []
        self.items_table.setRowCount(0)
        for item in summary["items"]:
            self._append_item_row(item)
        self.items_table.setMinimumHeight(
            max(6, len(summary["items"])) * 32 + 34
        )

    def _append_item_row(self, item: dict | None = None) -> None:
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        self._item_ids.append(item["id"] if item else None)

        name_item = QTableWidgetItem(item["name"] if item else "新分项")
        name_item.setTextAlignment(Qt.AlignCenter)
        self.items_table.setItem(row, 0, name_item)

        manual = float(item.get("manual_actual") or 0.0) if item else 0.0
        manual_item = QTableWidgetItem(f"{manual:.2f}")
        manual_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, 1, manual_item)

        planned = float(item.get("planned_amount") or 0.0) if item else 0.0
        planned_item = QTableWidgetItem(f"{planned:.2f}")
        planned_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, 2, planned_item)

        actual = float(item.get("actual") or 0.0) if item else 0.0
        actual_item = QTableWidgetItem(money(actual))
        actual_item.setFlags(actual_item.flags() & ~Qt.ItemIsEditable)
        actual_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, 3, actual_item)

        count = int(item.get("linked_count") or 0) if item else 0
        count_item = QTableWidgetItem(str(count))
        count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
        count_item.setTextAlignment(Qt.AlignCenter)
        self.items_table.setItem(row, 4, count_item)

        note_item = QTableWidgetItem(item["note"] if item else "")
        note_item.setTextAlignment(Qt.AlignCenter)
        self.items_table.setItem(row, 5, note_item)

        op = QWidget()
        op_layout = QHBoxLayout(op)
        op_layout.setContentsMargins(4, 2, 4, 2)
        op_layout.setSpacing(4)
        link_button = make_button("关联流水")
        link_button.clicked.connect(
            lambda _=False, r=row: self._open_link_dialog(r)
        )
        op_layout.addWidget(link_button)
        op_layout.addStretch(1)
        self.items_table.setCellWidget(row, 6, op)

    def _item_from_row(self, row: int) -> dict:
        return {
            "id": self._item_ids[row],
            "plan_id": self._current_plan_id,
            "name": self.items_table.item(row, 0).text().strip(),
            "manual_actual": _parse_float(
                self.items_table.item(row, 1).text()
            ),
            "planned_amount": _parse_float(
                self.items_table.item(row, 2).text()
            ),
            "note": self.items_table.item(row, 5).text().strip(),
            "sort_order": row,
        }

    def _add_item(self) -> None:
        if self._current_plan_id is None:
            return
        self._append_item_row()
        self.items_table.setCurrentCell(
            self.items_table.rowCount() - 1, 0
        )

    def _delete_item(self) -> None:
        row = self.items_table.currentRow()
        if row < 0 or row >= len(self._item_ids):
            QMessageBox.information(self, "提示", "请先选择要删除的分项")
            return
        item = self._item_from_row(row)
        if not confirm_delete(
            self, "删除分项", f"确定删除“{item['name'] or '未命名分项'}”？"
        ):
            return
        if item["id"] is not None:
            self._deleted_items.append(dict(item))
            repository.delete_spending_plan_item(self.conn, item["id"])
            self.conn.commit()
        self._item_ids.pop(row)
        self.items_table.removeRow(row)
        self._load_plan()
        self.on_change()

    def _undo_item(self) -> None:
        if not self._deleted_items:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        item = self._deleted_items.pop()
        repository.restore_spending_plan_item(self.conn, item)
        self.conn.commit()
        self._load_plan()
        self.on_change()

    def _save_items(self) -> None:
        if self._current_plan_id is None:
            return
        for row in range(self.items_table.rowCount()):
            name = self.items_table.item(row, 0).text().strip()
            if not name:
                continue
            item = self._item_from_row(row)
            if item["id"] is None:
                repository.add_spending_plan_item(
                    self.conn,
                    self._current_plan_id,
                    name,
                    item["planned_amount"],
                    item["manual_actual"],
                    item["note"],
                )
            else:
                repository.update_spending_plan_item(
                    self.conn,
                    item["id"],
                    name,
                    item["planned_amount"],
                    item["manual_actual"],
                    item["note"],
                )
        self.conn.commit()
        flash_saved(self.save_items_button)
        self._load_plan()
        self.on_change()

    def _open_link_dialog(self, row: int) -> None:
        if self._current_plan_id is None:
            return
        item_id = self._item_ids[row]
        if item_id is None:
            QMessageBox.information(
                self, "提示", "请先保存分项，再关联流水"
            )
            return
        plan = repository.get_spending_plan(
            self.conn, self._current_plan_id
        )
        dialog = LinkTransactionsDialog(
            self.conn,
            self._current_plan_id,
            item_id,
            str(plan.get("start_date") or "") if plan else "",
            str(plan.get("end_date") or "") if plan else "",
            self,
        )
        if dialog.exec() == QDialog.Accepted:
            self._load_plan()
            self.on_change()

    def _save_plan(self) -> None:
        if self._current_plan_id is None:
            return
        name = self.plan_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写计划名称")
            return
        start = (
            self.start_date_edit.date().toString("yyyy-MM-dd")
            if self.start_check.isChecked()
            else ""
        )
        end = (
            self.end_date_edit.date().toString("yyyy-MM-dd")
            if self.end_check.isChecked()
            else ""
        )
        repository.update_spending_plan(
            self.conn,
            self._current_plan_id,
            name,
            float(self.budget_spin.value()),
            start,
            end,
            self.plan_note_edit.text().strip(),
        )
        self.conn.commit()
        flash_saved(self.plan_save_button)
        self._reload_plans()
        self.on_change()

    def _add_plan(self) -> None:
        name, ok = QInputDialog.getText(
            self, "新增消费计划", "计划名称：", text="新计划"
        )
        if not ok or not name.strip():
            return
        plan_id = repository.add_spending_plan(self.conn, name.strip())
        self.conn.commit()
        self._reload_plans()
        index = self.plan_combo.findData(plan_id)
        self.plan_combo.setCurrentIndex(max(0, index))
        self.on_change()

    def _rename_plan(self) -> None:
        plan = self._current_plan()
        if plan is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名计划", "计划名称：", text=plan.get("name", "")
        )
        if not ok or not name.strip():
            return
        repository.update_spending_plan(
            self.conn,
            plan["id"],
            name.strip(),
            float(plan.get("total_budget") or 0.0),
            plan.get("start_date", ""),
            plan.get("end_date", ""),
            plan.get("note", ""),
        )
        self.conn.commit()
        self._reload_plans()

    def _delete_plan(self) -> None:
        plan = self._current_plan()
        if plan is None:
            return
        if len(repository.list_spending_plans(self.conn)) <= 1:
            QMessageBox.information(self, "提示", "至少保留一个消费计划")
            return
        if not confirm_delete(
            self, "删除计划", f"确定删除计划“{plan.get('name')}”？"
        ):
            return
        plan_id = int(plan["id"])
        snapshot = {
            "plan": plan,
            "items": repository.list_spending_plan_items(
                self.conn, plan_id
            ),
            "links": repository.list_spending_plan_links(
                self.conn, plan_id
            ),
        }
        repository.delete_spending_plan(self.conn, plan_id)
        self.conn.commit()
        self._deleted_plan = snapshot
        self._reload_plans()
        self.on_change()

    def _undo_plan(self) -> None:
        if self._deleted_plan is None:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        snapshot = self._deleted_plan
        repository.restore_spending_plan(
            self.conn, snapshot["plan"]
        )
        for item in snapshot["items"]:
            repository.restore_spending_plan_item(self.conn, item)
        repository.restore_spending_plan_links(
            self.conn, snapshot["links"]
        )
        self.conn.commit()
        self._deleted_plan = None
        self._reload_plans()
        self.on_change()

    def refresh(self) -> None:
        self._reload_plans()


class LinkTransactionsDialog(QDialog):
    """勾选记账流水，归集到某个计划分项。"""

    def __init__(
        self,
        conn,
        plan_id: int,
        item_id: int,
        start_date: str = "",
        end_date: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.plan_id = plan_id
        self.item_id = item_id
        self._transaction_ids: list[int] = []
        self.setWindowTitle("关联流水")
        self.resize(820, 520)
        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        default_start = QDate.fromString(start_date, "yyyy-MM-dd") if start_date else QDate.currentDate().addMonths(-3)
        default_end = QDate.fromString(end_date, "yyyy-MM-dd") if end_date else QDate.currentDate()
        self.start_edit = QDateEdit(default_start)
        self.end_edit = QDateEdit(default_end)
        for edit in (self.start_edit, self.end_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("搜索商家/备注")
        self.search_button = make_button("查询")
        self.search_button.clicked.connect(self._search)
        filter_row.addWidget(QLabel("从"))
        filter_row.addWidget(self.start_edit)
        filter_row.addWidget(QLabel("到"))
        filter_row.addWidget(self.end_edit)
        filter_row.addWidget(self.keyword_edit, 1)
        filter_row.addWidget(self.search_button)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["勾选", "日期", "商家", "备注", "金额", "账户"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.table.setMinimumHeight(360)
        layout.addWidget(self.table, 1)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("summaryValue")
        layout.addWidget(self.summary_label)

        buttons = QHBoxLayout()
        ok_button = make_button("保存关联", primary=True)
        cancel_button = make_button("取消")
        ok_button.clicked.connect(self._save)
        cancel_button.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(ok_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

        self._existing: set[int] = set()
        for link in repository.list_spending_plan_links(
            self.conn, self.plan_id
        ):
            if int(link["item_id"]) == self.item_id:
                self._existing.add(int(link["transaction_id"]))
        self._search()

    def _search(self) -> None:
        start = self.start_edit.date().toString("yyyy-MM-dd")
        end = self.end_edit.date().toString("yyyy-MM-dd")
        rows = transaction_service.get_transactions(
            self.conn,
            start,
            end,
            trans_type="expense",
            keyword=self.keyword_edit.text().strip(),
        )
        accounts = {
            a["id"]: a["name"]
            for a in account_service.get_accounts(self.conn)
        }
        self._transaction_ids = [row["id"] for row in rows]
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(
                Qt.Checked
                if int(row["id"]) in self._existing
                else Qt.Unchecked
            )
            check.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, check)
            values = [
                row["trans_date"],
                row["merchant"],
                row["note"],
                money(abs(float(row["amount"] or 0))),
                accounts.get(row["account_id"], ""),
            ]
            for c, text in enumerate(values, start=1):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)
        self._update_summary()

    def _selected_ids(self) -> list[int]:
        selected = []
        for r, transaction_id in enumerate(self._transaction_ids):
            item = self.table.item(r, 0)
            if item and item.checkState() == Qt.Checked:
                selected.append(transaction_id)
        return selected

    def _update_summary(self) -> None:
        selected = self._selected_ids()
        total = 0.0
        for r, transaction_id in enumerate(self._transaction_ids):
            if transaction_id in selected:
                total += abs(
                    float(self.table.item(r, 4).text().replace(",", "") or 0)
                )
        self.summary_label.setText(
            f"已勾选 {len(selected)} 笔，合计 {money(total)}"
        )

    def _save(self) -> None:
        repository.set_spending_item_links(
            self.conn,
            self.plan_id,
            self.item_id,
            self._selected_ids(),
        )
        self.conn.commit()
        self.accept()


def _parse_float(text: str) -> float:
    text = (text or "").strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
