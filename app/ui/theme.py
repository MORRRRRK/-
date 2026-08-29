"""界面主题与配色，从主窗口独立出来便于维护。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow

from ..core import repository


def apply_theme(window: QMainWindow, conn) -> None:
    try:
        font_size = int(repository.get_setting(conn, "font_size", "10"))
    except ValueError:
        font_size = 10
    accent = repository.get_setting(conn, "theme_color", "#2563eb")
    theme_mode = repository.get_setting(conn, "theme_mode", "system")
    if theme_mode == "dark":
        dark = True
    elif theme_mode == "light":
        dark = False
    else:
        dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    QApplication.instance().setFont(QFont("Microsoft YaHei UI", font_size))

    app = QApplication.instance()
    if dark:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#1f2630"))
        palette.setColor(QPalette.WindowText, QColor("#e5e7eb"))
        palette.setColor(QPalette.Base, QColor("#232a36"))
        palette.setColor(QPalette.AlternateBase, QColor("#293240"))
        palette.setColor(QPalette.Text, QColor("#e5e7eb"))
        palette.setColor(QPalette.Button, QColor("#2a3340"))
        palette.setColor(QPalette.ButtonText, QColor("#e5e7eb"))
        palette.setColor(QPalette.Highlight, QColor(accent))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.ToolTipBase, QColor("#2a3340"))
        palette.setColor(QPalette.ToolTipText, QColor("#e5e7eb"))
    else:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#f5f6f8"))
        palette.setColor(QPalette.WindowText, QColor("#1f2430"))
        palette.setColor(QPalette.Base, QColor("#ffffff"))
        palette.setColor(QPalette.AlternateBase, QColor("#f8fafc"))
        palette.setColor(QPalette.Text, QColor("#1f2430"))
        palette.setColor(QPalette.Button, QColor("#eef0f4"))
        palette.setColor(QPalette.ButtonText, QColor("#1f2430"))
        palette.setColor(QPalette.Highlight, QColor(accent))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
        palette.setColor(QPalette.ToolTipText, QColor("#1f2430"))
    app.setPalette(palette)

    colors = _theme_colors(dark)
    style = """
        QMainWindow, QWidget { background: __BG__; color: __TEXT__; }
        QListWidget#nav {
            background: __NAV_BG__;
            color: __NAV_TEXT__;
            border: none;
            font-size: 14px;
            padding-top: 10px;
        }
        QListWidget#nav::item {
            height: 44px;
            padding-left: 18px;
            border: none;
        }
        QListWidget#nav::item:selected {
            background: __ACCENT__;
            color: white;
        }
        QFrame#card {
            background: __PANEL__;
            border: 1px solid __BORDER__;
            border-radius: 6px;
        }
        QFrame#bigStatCard {
            background: __PANEL__;
            border: 1px solid __ACCENT__;
            border-radius: 8px;
        }
        QFrame#summaryStatCard {
            background: __PANEL__;
            border: 1px solid __BORDER__;
            border-radius: 8px;
        }
        QFrame#bigStatCard QLabel#cardValue,
        QFrame#summaryStatCard QLabel#cardValue {
            font-size: 28px;
            font-weight: 700;
        }
        QFrame#bigStatCard QLabel#cardTitle,
        QFrame#summaryStatCard QLabel#cardTitle {
            font-size: 14px;
        }
        QFrame#divider {
            background: __BORDER__;
            border: none;
            min-height: 1px;
            max-height: 1px;
        }
        QLabel#pageTitle {
            font-size: 22px;
            font-weight: 700;
            color: __TEXT__;
        }
        QTextBrowser {
            background: __PANEL__;
            border: 1px solid __BORDER__;
            border-radius: 6px;
            padding: 6px;
        }
        QLabel#cardTitle { color: __MUTED__; font-size: 13px; }
        QLabel#cardValue {
            font-size: 22px;
            font-weight: 600;
            color: __TEXT__;
        }
        QLabel#cardSub { color: __MUTED__; font-size: 12px; }
        QLabel#sectionTitle {
            font-size: 15px;
            font-weight: 600;
            color: __TEXT__;
        }
        QLabel#fieldLabel { color: __MUTED__; }
        QLabel#summaryValue {
            color: __TEXT__;
            font-weight: 600;
            font-size: 14px;
        }
        QPushButton {
            background: __BUTTON__;
            border: 1px solid __BORDER__;
            border-radius: 5px;
            padding: 6px 14px;
        }
        QPushButton:hover { background: __BUTTON_HOVER__; }
        QPushButton#primaryButton {
            background: __ACCENT__;
            color: white;
            border-color: __ACCENT__;
        }
        QPushButton#primaryButton:hover { background: __ACCENT__; }
        QToolButton#infoIcon {
            background: __INPUT__;
            border: 1px solid __BORDER__;
            border-radius: 9px;
            color: __MUTED__;
            font-size: 12px;
            font-weight: 700;
        }
        QToolButton#infoIcon:hover {
            border-color: __ACCENT__;
            color: __ACCENT__;
            background: __BUTTON_HOVER__;
        }
        QTableWidget {
            background: __PANEL__;
            alternate-background-color: __TABLE_ALT__;
            border: 1px solid __BORDER__;
            border-radius: 8px;
            gridline-color: __BORDER__;
        }
        QHeaderView::section {
            background: __HEADER__;
            border: none;
            border-bottom: 1px solid __BORDER__;
            padding: 6px;
            font-weight: 600;
        }
        QTableCornerButton::section {
            background: __HEADER__;
            border: none;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: __SCROLL__;
            border-radius: 5px;
            min-height: 24px;
        }
        QScrollBar::handle:vertical:hover { background: __SCROLL_HOVER__; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QLineEdit, QComboBox, QDoubleSpinBox, QDateEdit {
            background: __INPUT__;
            color: __TEXT__;
            border: 1px solid __BORDER__;
            border-radius: 4px;
            padding: 4px 6px;
        }
        QComboBox {
            background: __INPUT__;
            color: __TEXT__;
            border: 1px solid __BORDER__;
            border-radius: 5px;
            padding: 4px 26px 4px 8px;
            min-height: 24px;
        }
        QComboBox:hover { border-color: __ACCENT__; }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 22px;
            border-left: 1px solid __BORDER__;
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
            background: __HEADER__;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid __MUTED__;
            margin-right: 6px;
        }
        QComboBox QAbstractItemView {
            background: __PANEL__;
            color: __TEXT__;
            border: 1px solid __BORDER__;
            border-radius: 5px;
            selection-background-color: __ACCENT__;
            selection-color: white;
            outline: 0;
        }
        QMenuBar {
            background: __PANEL__;
            border-bottom: 1px solid __BORDER__;
            color: __TEXT__;
        }
        QMenuBar::item { padding: 6px 12px; }
        QMenuBar::item:selected { background: __BUTTON_HOVER__; }
        QMenu { background: __PANEL__; color: __TEXT__; border: 1px solid __BORDER__; }
        QMenu::item:selected { background: __BUTTON_HOVER__; }
        QToolTip {
            background: __INPUT__;
            color: __TEXT__;
            border: 1px solid __BORDER__;
            padding: 4px 6px;
        }
    """
    replacements = {
        "__ACCENT__": accent,
        **{key: value for key, value in colors.items()},
    }
    for key, value in replacements.items():
        style = style.replace(key, value)
    window.setStyleSheet(style)


def _theme_colors(dark: bool) -> dict[str, str]:
    if dark:
        return {
            "__BG__": "#171c24",
            "__PANEL__": "#1f2630",
            "__BORDER__": "#303a48",
            "__TEXT__": "#e5e7eb",
            "__MUTED__": "#9aa3b2",
            "__BUTTON__": "#2a3340",
            "__BUTTON_HOVER__": "#34404f",
            "__INPUT__": "#232a36",
            "__HEADER__": "#232a36",
            "__TABLE_ALT__": "#293240",
            "__SCROLL__": "#3a4554",
            "__SCROLL_HOVER__": "#4a5668",
            "__NAV_BG__": "#10141a",
            "__NAV_TEXT__": "#c7ccd4",
        }
    return {
        "__BG__": "#f5f6f8",
        "__PANEL__": "#ffffff",
        "__BORDER__": "#e2e5ea",
        "__TEXT__": "#1f2430",
        "__MUTED__": "#6b7280",
        "__BUTTON__": "#eef0f4",
        "__BUTTON_HOVER__": "#e2e6ec",
        "__INPUT__": "#ffffff",
        "__HEADER__": "#f1f3f7",
        "__TABLE_ALT__": "#f8fafc",
        "__SCROLL__": "#c8ced8",
        "__SCROLL_HOVER__": "#aab2bf",
        "__NAV_BG__": "#232a36",
        "__NAV_TEXT__": "#d5dae3",
    }
