from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import QAbstractItemView, QAbstractSpinBox
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..services import account_service, category_service


def money(value: float) -> str:
    return f"{value:,.2f}"


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def make_year_combo(years: list[int]) -> QComboBox:
    combo = QComboBox()
    for year in sorted((y for y in years if int(y) >= 2000), reverse=True):
        combo.addItem(str(year), year)
    return combo


class NoWheelSpinBox(QDoubleSpinBox):
    """禁用鼠标滚轮，避免浏览时误改数值。"""

    def wheelEvent(self, event) -> None:
        event.ignore()


def make_money_spin(value: float = 0.0, minimum: float = -1e8, maximum: float = 1e8) -> NoWheelSpinBox:
    spin = NoWheelSpinBox()
    spin._enter_save = True
    spin.setDecimals(2)
    spin.setRange(minimum, maximum)
    spin.setValue(float(value))
    spin.setGroupSeparatorShown(True)
    spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
    spin.setAlignment(Qt.AlignRight)
    return spin


def make_percent_spin(value: float = 0.0) -> NoWheelSpinBox:
    spin = NoWheelSpinBox()
    spin.setDecimals(2)
    spin.setRange(0.0, 100.0)
    spin.setSuffix(" %")
    spin.setValue(float(value) * 100.0)
    spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
    spin.setAlignment(Qt.AlignRight)
    return spin


def make_button(text: str, primary: bool = False) -> QPushButton:
    btn = QPushButton(text)
    if primary:
        btn.setObjectName("primaryButton")
    return btn


def make_formula_button(parent, title: str, text: str) -> QPushButton:
    """开发版“查看公式”按钮，点击弹出该计算结果的计算方式。"""
    button = make_button("查看公式")
    button.clicked.connect(
        lambda _=False: QMessageBox.information(parent, title, text)
    )
    return button


class InfoIcon(QToolButton):
    """圆形问号提示：鼠标悬停显示使用说明。"""

    def __init__(self, tooltip: str, parent=None):
        super().__init__(parent)
        self.setText("?")
        self.setObjectName("infoIcon")
        self.setToolTip(tooltip)
        self.setCursor(Qt.WhatsThisCursor)
        self.setFixedSize(18, 18)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAutoRaise(True)


def info_label(text: str, tooltip: str) -> QWidget:
    """小标题说明仅保留标签，问号说明只显示在模块大标题上。"""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    layout.addWidget(label)
    layout.addStretch(1)
    return widget


def flash_saved(button: QPushButton) -> None:
    """保存成功后让按钮短暂变绿，提示用户保存成功。"""
    original = button.styleSheet()
    button.setStyleSheet(
        "QPushButton { background: #16a34a; color: white; "
        "border: 1px solid #16a34a; border-radius: 5px; padding: 6px 14px; }"
    )
    QTimer.singleShot(1400, lambda: button.setStyleSheet(original))


class WheelGuard(QObject):
    """全局禁用下拉、日期、数值控件的鼠标滚轮改动。"""

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Wheel and isinstance(
            obj, (QAbstractSpinBox, QComboBox, QDateEdit)
        ):
            event.ignore()
            return True
        return False


class PageShortcutFilter(QObject):
    """全局快捷键：回车保存当前页内容；Ctrl+Z 在非文本输入处撤销上一步。"""

    def __init__(self, get_page, parent=None):
        super().__init__(parent)
        self.get_page = get_page

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.KeyPress:
            return False
        key = event.key()
        modifiers = event.modifiers()
        if key in (Qt.Key_Return, Qt.Key_Enter) and modifiers in (
            Qt.NoModifier,
            Qt.KeypadModifier,
        ):
            if QApplication.activeModalWidget() is not None:
                return False
            focus = QApplication.focusWidget()
            page = self.get_page()
            if focus is None or page is None or not hasattr(page, "save"):
                return False
            decision = self._enter_action(focus)
            if decision == "consume":
                page.save()
                return True
            if decision == "after":
                QTimer.singleShot(0, page.save)
            return False
        if (
            key == Qt.Key_Z
            and modifiers & Qt.ControlModifier
            and not modifiers & (Qt.ShiftModifier | Qt.AltModifier)
        ):
            if QApplication.activeModalWidget() is not None:
                return False
            focus = QApplication.focusWidget()
            if focus is None or self._is_text_editor(focus):
                return False
            page = self.get_page()
            if page is not None and hasattr(page, "undo"):
                page.undo()
                return True
        return False

    def _enter_action(self, focus) -> str:
        if not isinstance(
            focus, (QLineEdit, QAbstractSpinBox, QAbstractItemView)
        ):
            return "skip"
        if isinstance(focus, QLineEdit):
            parent_spin = focus.parentWidget()
            if isinstance(parent_spin, QAbstractSpinBox):
                return (
                    "after"
                    if getattr(parent_spin, "_enter_save", False)
                    else "skip"
                )
            if isinstance(parent_spin, QComboBox):
                return "skip"
            flag = getattr(focus, "_enter_save", None)
            if flag is False:
                return "skip"
            if flag is True:
                return "consume"
        if isinstance(focus, QAbstractSpinBox):
            return (
                "after" if getattr(focus, "_enter_save", False) else "skip"
            )
        table = self._find_table(focus)
        if table is not None and getattr(table, "_enter_save", False):
            return "after" if isinstance(focus, QLineEdit) else "consume"
        return "skip"

    @staticmethod
    def _find_table(widget):
        current = widget
        while current is not None:
            if isinstance(current, QTableWidget):
                return current
            current = current.parentWidget()
        return None

    @staticmethod
    def _is_text_editor(focus) -> bool:
        return isinstance(
            focus, (QLineEdit, QTextEdit, QPlainTextEdit)
        ) or (isinstance(focus, QComboBox) and focus.isEditable())


def confirm_delete(parent, title: str, text: str) -> bool:
    """删除前一次确认，防止误删。"""
    return QMessageBox.question(parent, title, text) == QMessageBox.Yes


class StatCard(QFrame):
    """总览页指标卡片。"""

    def __init__(self, title: str, parent=None, info: str = ""):
        super().__init__(parent)
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("cardTitle")
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)
        self.value_label = QLabel("0.00")
        self.value_label.setObjectName("cardValue")
        self.sub_label = QLabel("")
        self.sub_label.setObjectName("cardSub")
        layout.addLayout(title_row)
        layout.addWidget(self.value_label)
        layout.addWidget(self.sub_label)

    def set_value(self, value: str, sub: str = "") -> None:
        self.value_label.setText(value)
        self.sub_label.setText(sub)


class Section(QFrame):
    """白底分组面板。"""

    def __init__(
        self,
        title: str,
        parent=None,
        actions: list | None = None,
        info: str = "",
    ):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_row = QHBoxLayout()
        title_row.addWidget(title_label)
        if info:
            title_row.addWidget(InfoIcon(info))
        title_row.addStretch(1)
        for action in actions or []:
            title_row.addWidget(action)
        layout.addLayout(title_row)
        self.body = QVBoxLayout()
        layout.addLayout(self.body)

    def add(self, widget) -> None:
        self.body.addWidget(widget)

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)


class LabeledRow(QHBoxLayout):
    def __init__(self, text: str, value_widget):
        super().__init__()
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        self.addWidget(label)
        self.addStretch(1)
        self.addWidget(value_widget)


def line_edit(text: str = "", placeholder: str = "") -> QLineEdit:
    edit = QLineEdit(text)
    edit._enter_save = True
    if placeholder:
        edit.setPlaceholderText(placeholder)
    return edit


class TransactionDialog(QDialog):
    """快速记账对话框：支出/收入/转账。"""

    def __init__(self, conn, parent=None, transaction: dict | None = None):
        super().__init__(parent)
        self.conn = conn
        self.transaction = transaction
        self.setWindowTitle("编辑交易" if transaction else "快速记账")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        self.type_combo = QComboBox()
        self.type_combo.addItem("支出", "expense")
        self.type_combo.addItem("收入", "income")
        self.type_combo.addItem("转账", "transfer")
        if transaction:
            index = self.type_combo.findData(transaction["type"])
            self.type_combo.setCurrentIndex(max(0, index))
        layout.addWidget(self.type_combo)

        self.amount_spin = make_money_spin(
            float(transaction["amount"]) if transaction else 0.0, 0.0, 1e8
        )
        layout.addWidget(QLabel("金额"))
        layout.addWidget(self.amount_spin)

        self.category_combo = QComboBox()
        self._reload_categories()
        layout.addWidget(QLabel("分类"))
        layout.addWidget(self.category_combo)

        self.account_combo = QComboBox()
        self.to_account_combo = QComboBox()
        self._reload_accounts()
        layout.addWidget(QLabel("账户"))
        layout.addWidget(self.account_combo)
        layout.addWidget(QLabel("转入账户"))
        layout.addWidget(self.to_account_combo)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        layout.addWidget(QLabel("日期"))
        layout.addWidget(self.date_edit)

        self.merchant_edit = line_edit(transaction["merchant"] if transaction else "", "商家")
        self.note_edit = line_edit(transaction["note"] if transaction else "", "备注")
        self.reimbursable_check = QCheckBox("可报销")
        if transaction:
            self.reimbursable_check.setChecked(bool(transaction["is_reimbursable"]))
        layout.addWidget(self.merchant_edit)
        layout.addWidget(self.note_edit)
        layout.addWidget(self.reimbursable_check)

        buttons = QHBoxLayout()
        ok = make_button("保存", primary=True)
        cancel = make_button("取消")
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _reload_categories(self) -> None:
        self.category_combo.clear()
        self.category_combo.addItem("无", 0)
        categories = category_service.get_categories(self.conn)

        def walk(items, prefix=""):
            for item in items:
                self.category_combo.addItem(prefix + item["name"], item["id"])
                walk(item.get("children") or [], prefix + "  ")

        walk(categories)
        if self.transaction and self.transaction.get("category_id"):
            index = self.category_combo.findData(self.transaction["category_id"])
            self.category_combo.setCurrentIndex(max(0, index))

    def _reload_accounts(self) -> None:
        accounts = account_service.get_accounts(self.conn)
        for combo in (self.account_combo, self.to_account_combo):
            combo.clear()
            for account in accounts:
                combo.addItem(account["name"], account["id"])
        if self.transaction:
            index = self.account_combo.findData(self.transaction["account_id"])
            self.account_combo.setCurrentIndex(max(0, index))
            if self.transaction.get("to_account_id"):
                index = self.to_account_combo.findData(self.transaction["to_account_id"])
                self.to_account_combo.setCurrentIndex(max(0, index))

    def _accept(self) -> None:
        if float(self.amount_spin.value()) <= 0:
            QMessageBox.warning(self, "提示", "金额必须大于 0")
            return
        if self.account_combo.currentData() is None:
            QMessageBox.warning(
                self, "提示", "请先到“账户管理”创建账户，再开始记账。"
            )
            return
        if self.type_combo.currentData() == "transfer" and (
            self.account_combo.currentData() == self.to_account_combo.currentData()
        ):
            QMessageBox.warning(self, "提示", "转出和转入账户不能相同")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "trans_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "trans_type": self.type_combo.currentData(),
            "amount": float(self.amount_spin.value()),
            "category_id": self.category_combo.currentData() or None,
            "account_id": self.account_combo.currentData(),
            "to_account_id": self.to_account_combo.currentData(),
            "merchant": self.merchant_edit.text().strip(),
            "note": self.note_edit.text().strip(),
            "is_reimbursable": 1 if self.reimbursable_check.isChecked() else 0,
        }
