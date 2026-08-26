from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QInputDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.paths import exports_dir
from ...services import account_service, exporter, importer, transaction_service
from ..widgets import (
    Section,
    TransactionDialog,
    confirm_delete,
    make_button,
    money,
)


class TransactionsPage(QScrollArea):
    def __init__(self, conn, on_change):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._ids: list[int] = []
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        self.expense_button = make_button("记支出", primary=True)
        self.income_button = make_button("记收入", primary=True)
        self.transfer_button = make_button("转账", primary=True)
        self.delete_button = make_button("删除")
        self.bluecoins_button = make_button("导入 BlueCoins")
        self.delete_history_button = make_button("删除历史")
        self.expense_button.clicked.connect(lambda: self._add("expense"))
        self.income_button.clicked.connect(lambda: self._add("income"))
        self.transfer_button.clicked.connect(lambda: self._add("transfer"))
        self.delete_button.clicked.connect(self._delete)
        self.bluecoins_button.clicked.connect(self._import_bluecoins)
        self.delete_history_button.clicked.connect(self._delete_history)
        top.addWidget(self.expense_button)
        top.addWidget(self.income_button)
        top.addWidget(self.transfer_button)
        top.addWidget(self.delete_button)
        top.addWidget(self.bluecoins_button)
        top.addWidget(self.delete_history_button)
        top.addStretch(1)
        layout.addLayout(top)

        filters = QHBoxLayout()
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.end_date = QDateEdit(QDate.currentDate())
        for edit in (self.start_date, self.end_date):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.category_combo = QComboBox()
        self.category_combo.addItem("全部分类", 0)
        from ...services import category_service

        for item in category_service.get_categories(self.conn):
            self.category_combo.addItem(item["name"], item["id"])
        self.account_combo = QComboBox()
        self.account_combo.addItem("全部账户", 0)
        for account in account_service.get_accounts(self.conn):
            self.account_combo.addItem(account["name"], account["id"])
        self.type_combo = QComboBox()
        self.type_combo.addItem("全部类型", "")
        self.type_combo.addItem("支出", "expense")
        self.type_combo.addItem("收入", "income")
        self.type_combo.addItem("转账", "transfer")
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("搜索商家/备注")
        self.search_button = make_button("查询")
        self.export_button = make_button("导出")
        self.search_button.clicked.connect(self.refresh)
        self.export_button.clicked.connect(self._export)
        for widget in (
            QLabel("从"), self.start_date, QLabel("到"), self.end_date,
            self.category_combo, self.account_combo, self.type_combo,
            self.keyword_edit, self.search_button, self.export_button,
        ):
            filters.addWidget(widget)
        layout.addLayout(filters)

        section = Section("交易记录")
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["日期", "类型", "分类", "商家", "账户", "备注", "金额", "可报销"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(lambda _: self._edit())
        section.add(self.table)
        layout.addWidget(section)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("summaryValue")
        layout.addWidget(self.summary_label)
        self.refresh()

    def refresh(self) -> None:
        rows = transaction_service.get_transactions(
            self.conn,
            self.start_date.date().toString("yyyy-MM-dd"),
            self.end_date.date().toString("yyyy-MM-dd"),
            self.category_combo.currentData() or None,
            self.account_combo.currentData() or None,
            self.type_combo.currentData(),
            self.keyword_edit.text().strip(),
        )
        self._ids = [row["id"] for row in rows]
        accounts = {a["id"]: a["name"] for a in account_service.get_accounts(self.conn)}
        categories = {
            c["id"]: c["name"]
            for c in self.conn.execute("SELECT id, name FROM transaction_categories")
        }
        self.table.setRowCount(len(rows))
        income = expense = 0.0
        for r, row in enumerate(rows):
            amount = float(row["amount"] or 0)
            if row["type"] == "income":
                income += amount
                amount_text = f"+{money(amount)}"
                color = Qt.green
            elif row["type"] == "expense":
                expense += amount
                amount_text = f"-{money(amount)}"
                color = Qt.red
            else:
                amount_text = money(amount)
                color = Qt.darkBlue
            values = [
                row["trans_date"],
                {"expense": "支出", "income": "收入", "transfer": "转账"}.get(
                    row["type"], row["type"]
                ),
                categories.get(row["category_id"], ""),
                row["merchant"],
                accounts.get(row["account_id"], ""),
                row["note"],
                amount_text,
                "是" if row["is_reimbursable"] else "",
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                if c == 6:
                    item.setForeground(color)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)
        self.summary_label.setText(
            f"收入 {money(income)}  支出 {money(expense)}  结余 {money(income - expense)}"
        )

    def _add(self, trans_type: str) -> None:
        if not account_service.get_accounts(self.conn):
            QMessageBox.information(
                self, "提示", "请先到“账户管理”创建一个账户，再开始记账。"
            )
            return
        dialog = TransactionDialog(self.conn, self)
        if trans_type:
            index = dialog.type_combo.findData(trans_type)
            dialog.type_combo.setCurrentIndex(max(0, index))
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            transaction_service.add_transaction(self.conn, **dialog.values())
            self.conn.commit()
        except Exception as exc:
            QMessageBox.warning(self, "记账失败", f"保存失败：{exc}")
            return
        self.refresh()
        self.on_change()
        QMessageBox.information(self, "记账成功", "交易已保存。")

    def _edit(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            QMessageBox.information(self, "提示", "请先选择交易")
            return
        transaction = transaction_service.get_transaction(self.conn, self._ids[row])
        dialog = TransactionDialog(self.conn, self, transaction)
        if dialog.exec() != QDialog.Accepted:
            return
        transaction_service.update_transaction(self.conn, transaction["id"], **dialog.values())
        self.conn.commit()
        self.refresh()
        self.on_change()

    def _delete(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            return
        if not confirm_delete(self, "删除交易", "确定删除选中的交易？"):
            return
        transaction_service.delete_transaction(self.conn, self._ids[row])
        self.conn.commit()
        self.refresh()
        self.on_change()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出交易", str(exports_dir() / "transactions.csv"), "CSV (*.csv)"
        )
        if not path:
            return
        exporter.export_transactions(
            self.conn,
            self.start_date.date().toString("yyyy-MM-dd"),
            self.end_date.date().toString("yyyy-MM-dd"),
            Path(path),
        )
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")

    def _import_bluecoins(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 BlueCoins CSV", "", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            count = importer.import_bluecoins_csv(self.conn, Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self.conn.commit()
        self.refresh()
        self.on_change()
        QMessageBox.information(self, "导入完成", f"成功导入 {count} 条交易。")

    def _delete_history(self) -> None:
        cutoff, ok = QInputDialog.getText(
            self,
            "删除历史记录",
            "删除该日期之前的所有交易（留空删除全部）：\n格式 2026-01-01",
        )
        if not ok:
            return
        cutoff = cutoff.strip()
        if not confirm_delete(
            self, "删除历史", f"确定删除{(' ' + cutoff + ' 之前') if cutoff else '全部'}交易记录？"
        ):
            return
        rows = transaction_service.get_transactions(self.conn)
        deleted = 0
        for row in rows:
            if cutoff and row["trans_date"] >= cutoff:
                continue
            transaction_service.delete_transaction(self.conn, row["id"])
            deleted += 1
        self.conn.commit()
        self.refresh()
        self.on_change()
        QMessageBox.information(self, "删除完成", f"已删除 {deleted} 条历史记录。")
