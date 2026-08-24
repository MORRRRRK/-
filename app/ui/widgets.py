from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import QAbstractSpinBox
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)


def money(value: float) -> str:
    return f"{value:,.2f}"


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def make_year_combo(years: list[int]) -> QComboBox:
    combo = QComboBox()
    for year in sorted(years, reverse=True):
        combo.addItem(str(year), year)
    return combo


class NoWheelSpinBox(QDoubleSpinBox):
    """禁用鼠标滚轮，避免浏览时误改数值。"""

    def wheelEvent(self, event) -> None:
        event.ignore()


def make_money_spin(value: float = 0.0, minimum: float = -1e8, maximum: float = 1e8) -> NoWheelSpinBox:
    spin = NoWheelSpinBox()
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


def confirm_delete(parent, title: str, text: str) -> bool:
    """删除前一次确认，防止误删。"""
    return QMessageBox.question(parent, title, text) == QMessageBox.Yes


class StatCard(QFrame):
    """总览页指标卡片。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("cardTitle")
        self.value_label = QLabel("0.00")
        self.value_label.setObjectName("cardValue")
        self.sub_label = QLabel("")
        self.sub_label.setObjectName("cardSub")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.sub_label)

    def set_value(self, value: str, sub: str = "") -> None:
        self.value_label.setText(value)
        self.sub_label.setText(sub)


class Section(QFrame):
    """白底分组面板。"""

    def __init__(self, title: str, parent=None, actions: list | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_row = QHBoxLayout()
        title_row.addWidget(title_label)
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
    if placeholder:
        edit.setPlaceholderText(placeholder)
    return edit
