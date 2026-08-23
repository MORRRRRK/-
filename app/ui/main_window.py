from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QAbstractItemView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .. import VERSION_LABEL, __version__
from ..edition import edition_label, is_customer
from ..core import repository
from ..core.db import Database
from ..core.paths import backups_dir, db_path, exports_dir
from ..services import exporter
from ..services.web_server import WebService
from ..services.updater import is_newer, update_repo, update_token
from ..services.importer import MigrationError, import_xlsx
from .update_worker import UpdateCheckWorker, UpdateInstallWorker
from .pages.about import AboutPage
from .pages.holdings import HoldingsPage
from .pages.insurance import InsurancePage
from .pages.monthly import MonthlyPage
from .pages.overview import OverviewPage
from .pages.planning import PlanningPage
from .pages.reports import ReportsPage
from .pages.settings import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            f"个人财务软件 {VERSION_LABEL} {edition_label()}"
        )
        self.resize(1280, 960)
        self.setMinimumSize(1080, 760)
        self.db = Database()
        self._check_worker = None
        self._install_worker = None
        self._current_about_page = None
        self.web_server: WebService | None = None
        self._build_menus()
        self._build_ui()
        self.refresh_all()
        self._apply_style()
        self._apply_web_settings()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(168)
        for name in [
            "资产总览",
            "月度流水",
            "工资参数",
            "持仓管理",
            "资产规划",
            "智能报告",
            "设置",
            "关于",
        ]:
            self.nav.addItem(name)
        self.nav.currentRowChanged.connect(self._switch_page)

        self.stack = QStackedWidget()
        self.reports_page = ReportsPage(self.db.conn, self.refresh_all)
        self.settings_page = SettingsPage(self.db.conn, self._settings_changed)
        self.about_page = AboutPage(self.db.conn, self._check_update)
        self.pages = [
            OverviewPage(self.db.conn),
            MonthlyPage(self.db.conn, self.refresh_all),
            InsurancePage(self.db.conn, self.refresh_all),
            HoldingsPage(self.db.conn, self.refresh_all),
            PlanningPage(self.db.conn, self.refresh_all),
            self.reports_page,
            self.settings_page,
            self.about_page,
        ]
        for page in self.pages:
            self.stack.addWidget(page)

        root.addWidget(self.nav)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._apply_row_selection(self)
        self.nav.setCurrentRow(0)
        QTimer.singleShot(2000, self._startup_update_check)

    def _switch_page(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")
        file_menu.addAction("备份数据库", self._backup)
        file_menu.addAction("恢复备份", self._restore)
        file_menu.addSeparator()
        file_menu.addAction("导出 CSV", self._export_csv)
        file_menu.addAction("从 Excel 导入", self._import_excel)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)

    def refresh_all(self) -> None:
        for page in self.pages:
            page.refresh()

    def _settings_changed(self) -> None:
        self._apply_style()
        self.refresh_all()
        self._apply_web_settings()

    def _apply_web_settings(self) -> None:
        if self.web_server is not None:
            self.web_server.stop()
            self.web_server = None
        enabled = repository.get_setting(self.db.conn, "web_enabled", "0") == "1"
        access_code = repository.get_setting(self.db.conn, "web_access_code", "").strip()
        try:
            port = int(repository.get_setting(self.db.conn, "web_port", "8765"))
        except ValueError:
            port = 8765
        if not enabled:
            self.settings_page.set_web_status("局域网访问已关闭")
            return
        if not access_code:
            self.settings_page.set_web_status("请先设置访问码后再启用")
            return
        try:
            self.web_server = WebService(port, access_code)
            self.web_server.start()
        except OSError as exc:
            self.web_server = None
            self.settings_page.set_web_status(f"局域网访问启动失败：{exc}")
            return
        urls = self.web_server.urls()
        self.settings_page.set_web_status(
            f"已启动，本机：{urls['local']}  局域网：{urls['lan']}"
        )

    def closeEvent(self, event) -> None:
        if self.web_server is not None:
            self.web_server.stop()
            self.web_server = None
        super().closeEvent(event)

    def _startup_update_check(self) -> None:
        self._run_update_check(quiet=True)

    def _check_update(self, about_page=None) -> None:
        self._run_update_check(quiet=False, about_page=about_page)

    def _run_update_check(self, quiet: bool = False, about_page=None) -> None:
        if self._check_worker is not None and self._check_worker.isRunning():
            return
        repo = update_repo(self.db.conn)
        token = update_token(self.db.conn)
        if not repo:
            message = "尚未配置 GitHub 更新仓库，请在“设置”中填写 owner/repo"
            if about_page is not None:
                about_page.update_status.setText(message)
            elif not quiet:
                QMessageBox.information(self, "无法检查更新", message)
            return
        self._current_about_page = about_page
        self._check_worker = UpdateCheckWorker(repo, token, is_customer())
        self._check_worker.finished.connect(self._on_check_finished)
        self._check_worker.failed.connect(self._on_check_failed)
        self._check_worker.start()

    def _on_check_finished(self, info: dict) -> None:
        self._check_worker = None
        if is_newer(info.get("version", ""), __version__):
            message = (
                f"发现新版本 V{info.get('version')}\n\n"
                f"{str(info.get('notes') or '')[:300]}\n\n是否立即更新？"
            )
            choice = QMessageBox.question(
                self,
                "发现新版本",
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if choice == QMessageBox.Yes:
                self._install_update(info)
            elif self._current_about_page is not None:
                self._current_about_page.update_status.setText("已忽略本次更新")
        else:
            if self._current_about_page is not None:
                self._current_about_page.update_status.setText("已是最新版本")

    def _on_check_failed(self, message: str) -> None:
        self._check_worker = None
        if self._current_about_page is not None:
            self._current_about_page.update_status.setText(message)

    def _install_update(self, info: dict) -> None:
        if self._install_worker is not None and self._install_worker.isRunning():
            return
        backup_dir = Path(
            repository.get_setting(self.db.conn, "backup_dir", str(backups_dir()))
        )
        token = update_token(self.db.conn)
        self._install_worker = UpdateInstallWorker(
            self.db.conn, info, backup_dir, token
        )
        self._install_worker.finished.connect(self._on_install_finished)
        self._install_worker.failed.connect(self._on_install_failed)
        self._install_worker.start()
        if self._current_about_page is not None:
            self._current_about_page.update_status.setText("正在下载并校验更新包…")

    def _on_install_finished(self, version: str) -> None:
        self._install_worker = None
        QMessageBox.information(
            self,
            "更新已启动",
            f"新版 V{version} 将在软件退出后自动安装，请稍候。",
        )
        QTimer.singleShot(800, QApplication.instance().quit)

    def _on_install_failed(self, message: str) -> None:
        self._install_worker = None
        QMessageBox.warning(
            self, "更新失败", message + "\n\n当前版本不受影响，可继续使用。"
        )

    def _backup(self) -> None:
        target = exporter.backup_database(
            self.db.path,
            Path(repository.get_setting(self.db.conn, "backup_dir", str(backups_dir()))),
        )
        QMessageBox.information(self, "备份完成", f"已备份到：\n{target}")

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择备份文件", str(backups_dir()), "SQLite 备份 (*.db)"
        )
        if not path:
            return
        if QMessageBox.question(
            self, "确认恢复", "恢复会覆盖当前数据，是否继续？"
        ) != QMessageBox.Yes:
            return
        self.db.close()
        shutil.copy2(path, db_path())
        self.db = Database()
        self._build_ui()
        self.refresh_all()
        QMessageBox.information(self, "恢复完成", "数据已恢复。")

    def _export_csv(self) -> None:
        written = exporter.export_csv(
            self.db.conn,
            Path(repository.get_setting(self.db.conn, "export_dir", str(exports_dir()))),
        )
        QMessageBox.information(
            self, "导出完成", "已导出到：\n" + "\n".join(str(p) for p in written)
        )

    @staticmethod
    def _apply_row_selection(root: QWidget) -> None:
        for widget in root.findChildren(QTableWidget):
            widget.setSelectionBehavior(QAbstractItemView.SelectRows)
            widget.setSelectionMode(QAbstractItemView.SingleSelection)

    def _import_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Excel 文件", "", "Excel 文件 (*.xlsx)"
        )
        if not path:
            return
        if QMessageBox.question(
            self, "确认导入", "导入会替换当前业务数据，是否继续？"
        ) != QMessageBox.Yes:
            return
        try:
            import_xlsx(self.db.conn, path)
        except MigrationError as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.refresh_all()
        QMessageBox.information(self, "导入完成", "Excel 数据已导入并通过对账。")

    def _apply_style(self) -> None:
        from PySide6.QtGui import QColor, QGuiApplication, QPalette
        from PySide6.QtWidgets import QApplication
        from ..core import repository

        try:
            font_size = int(repository.get_setting(self.db.conn, "font_size", "10"))
        except ValueError:
            font_size = 10
        accent = repository.get_setting(self.db.conn, "theme_color", "#2563eb")
        theme_mode = repository.get_setting(self.db.conn, "theme_mode", "system")
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
            QLabel#cardTitle {
                color: __MUTED__;
                font-size: 13px;
            }
            QLabel#cardValue {
                font-size: 22px;
                font-weight: 600;
                color: __TEXT__;
            }
            QLabel#cardSub {
                color: __MUTED__;
                font-size: 12px;
            }
            QLabel#sectionTitle {
                font-size: 15px;
                font-weight: 600;
                color: __TEXT__;
            }
            QLabel#fieldLabel {
                color: __MUTED__;
            }
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
        self.setStyleSheet(style)


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
