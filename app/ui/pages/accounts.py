from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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

from ...services import account_service
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

ACCOUNT_TYPES = [
    ("现金", "cash"),
    ("银行卡", "bank"),
    ("支付宝", "alipay"),
    ("微信", "wechat"),
    ("投资账户", "investment"),
    ("信用卡", "credit_card"),
    ("贷款", "loan"),
    ("其他", "other"),
]


class AccountsPage(QScrollArea):
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
        self.add_button = make_button("新增账户", primary=True)
        self.edit_button = make_button("编辑")
        self.delete_button = make_button("删除")
        self.add_button.clicked.connect(self._add)
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)
        top.addWidget(self.add_button)
        top.addWidget(self.edit_button)
        top.addWidget(self.delete_button)
        top.addStretch(1)
        layout.addLayout(top)

        section = Section("账户列表")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["名称", "类型", "机构", "初始余额", "当前余额", "备注"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(lambda _: self._edit())
        section.add(self.table)
        layout.addWidget(section)

        cards = QHBoxLayout()
        self.asset_card = StatCard("总资产")
        self.liability_card = StatCard("总负债")
        self.net_card = StatCard("净资产")
        cards.addWidget(self.asset_card)
        cards.addWidget(self.liability_card)
        cards.addWidget(self.net_card)
        layout.addLayout(cards)
        self.refresh()

    def refresh(self) -> None:
        accounts = account_service.get_accounts(self.conn)
        self._ids = [a["id"] for a in accounts]
        self.table.setRowCount(len(accounts))
        for row, account in enumerate(accounts):
            values = [
                account["name"],
                dict(ACCOUNT_TYPES).get(account["type"], account["type"]),
                account["institution"],
                money(account["initial_balance"]),
                money(account["current_balance"]),
                account["note"],
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(
                    Qt.AlignRight | Qt.AlignVCenter if col in (3, 4) else Qt.AlignLeft
                )
                self.table.setItem(row, col, item)
        summary = account_service.get_account_summary(self.conn)
        self.asset_card.set_value(money(summary["total_assets"]), "")
        self.liability_card.set_value(money(summary["total_liabilities"]), "")
        self.net_card.set_value(money(summary["net_worth"]), "")

    def _selected(self) -> int | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._ids):
            return self._ids[row]
        return None

    def _add(self) -> None:
        dialog = AccountDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        account_service.add_account(self.conn, **dialog.values())
        self.conn.commit()
        self.refresh()
        self.on_change()

    def _edit(self) -> None:
        account_id = self._selected()
        if account_id is None:
            QMessageBox.information(self, "提示", "请先选择账户")
            return
        account = account_service.get_account(self.conn, account_id)
        dialog = AccountDialog(self, account)
        if dialog.exec() != QDialog.Accepted:
            return
        account_service.update_account(self.conn, account_id, **dialog.values())
        self.conn.commit()
        self.refresh()
        self.on_change()

    def _delete(self) -> None:
        account_id = self._selected()
        if account_id is None:
            return
        account = account_service.get_account(self.conn, account_id)
        if not confirm_delete(self, "删除账户", f"确定删除账户“{account['name']}”？"):
            return
        try:
            account_service.delete_account(self.conn, account_id)
        except ValueError as exc:
            QMessageBox.warning(self, "无法删除", str(exc))
            return
        self.conn.commit()
        self.refresh()
        self.on_change()


class AccountDialog(QDialog):
    def __init__(self, parent=None, account: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("编辑账户" if account else "新增账户")
        self.setMinimumWidth(420)
        layout = QGridLayout(self)
        self.name_edit = line_edit(account["name"] if account else "", "账户名称")
        self.type_combo = QComboBox()
        for label, value in ACCOUNT_TYPES:
            self.type_combo.addItem(label, value)
        if account:
            index = self.type_combo.findData(account["type"])
            self.type_combo.setCurrentIndex(max(0, index))
        self.institution_edit = line_edit(account["institution"] if account else "", "机构")
        self.balance_spin = make_money_spin(
            float(account["initial_balance"]) if account else 0.0
        )
        self.note_edit = line_edit(account["note"] if account else "", "备注")
        rows = [
            ("名称", self.name_edit),
            ("类型", self.type_combo),
            ("机构", self.institution_edit),
            ("初始余额", self.balance_spin),
            ("备注", self.note_edit),
        ]
        for row, (title, widget) in enumerate(rows):
            label = QLabel(title)
            label.setObjectName("fieldLabel")
            layout.addWidget(label, row, 0)
            layout.addWidget(widget, row, 1)
        buttons = QHBoxLayout()
        ok = make_button("确定", primary=True)
        cancel = make_button("取消")
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons, len(rows), 0, 1, 2)

    def _accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "请填写账户名称")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "account_type": self.type_combo.currentData(),
            "institution": self.institution_edit.text().strip(),
            "initial_balance": float(self.balance_spin.value()),
            "is_liability": self.type_combo.currentData() in ("credit_card", "loan"),
            "note": self.note_edit.text().strip(),
        }
