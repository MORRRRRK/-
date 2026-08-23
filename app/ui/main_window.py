from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QAbstractItemView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
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
from .sync_worker import CloudSyncWorker
from .pages.about import AboutPage
from .pages.holdings import HoldingsPage
from .pages.insurance import InsurancePage
from .pages.monthly import MonthlyPage
from .pages.overview import OverviewPage
from .pages.planning import PlanningPage
from .pages.reports import ReportsPage
from .pages.settings import SettingsPage
from .theme import apply_theme


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
        self._cloud_worker: CloudSyncWorker | None = None
        self._cloud_mode = ""
        self._cloud_quiet = False
        self._update_progress: QProgressDialog | None = None
        self._check_timer: QTimer | None = None
        self._current_about_page = None
        self.web_server: WebService | None = None
        self._build_menus()
        self._build_ui()
        self.refresh_all()
        self._apply_style()
        self._apply_web_settings()
        QTimer.singleShot(3000, self._startup_cloud_sync)

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
        self.settings_page = SettingsPage(
            self.db.conn, self._settings_changed, self._cloud_action
        )
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

    def _startup_cloud_sync(self) -> None:
        if repository.get_setting(self.db.conn, "cloud_sync_enabled", "0") != "1":
            return
        if repository.get_setting(self.db.conn, "cloud_sync_startup", "0") != "1":
            return
        config = self._cloud_config_from_settings()
        if config.get("base_url"):
            self._start_cloud_worker("push", config, quiet=True)

    def _cloud_config_from_settings(self) -> dict[str, str]:
        return {
            "base_url": repository.get_setting(
                self.db.conn, "cloud_sync_webdav_url", ""
            ).strip(),
            "username": repository.get_setting(
                self.db.conn, "cloud_sync_username", ""
            ).strip(),
            "password": repository.get_setting(
                self.db.conn, "cloud_sync_password", ""
            ),
            "sync_password": repository.get_setting(
                self.db.conn, "cloud_sync_key", ""
            ),
        }

    def _cloud_action(self, mode: str, config: dict[str, str]) -> None:
        self._start_cloud_worker(mode, config, quiet=False)

    def _start_cloud_worker(
        self, mode: str, config: dict[str, str], quiet: bool = False
    ) -> None:
        if self._cloud_worker is not None and self._cloud_worker.isRunning():
            self.settings_page.set_cloud_status("云同步正在进行中，请稍候")
            return
        backup_dir = Path(
            repository.get_setting(self.db.conn, "backup_dir", str(backups_dir()))
        )
        self._cloud_mode = mode
        self._cloud_quiet = quiet
        self._cloud_worker = CloudSyncWorker(
            mode, db_path(), config, backup_dir, self
        )
        self._cloud_worker.finished.connect(self._on_cloud_finished)
        self._cloud_worker.failed.connect(self._on_cloud_failed)
        if not quiet:
            labels = {
                "push": "正在上传加密同步文件…",
                "pull": "正在下载并校验云端文件…",
                "test": "正在测试 WebDAV 连接…",
            }
            self.settings_page.set_cloud_status(labels.get(mode, "正在云同步…"))
        self._cloud_worker.start()

    def _on_cloud_finished(self, result: dict) -> None:
        self._cloud_worker = None
        mode = self._cloud_mode
        if mode == "push":
            message = str(result.get("message", "同步成功"))
            if result.get("conflict_saved"):
                message += f"；云端旧文件已备份到 {result.get('conflict_path')}"
            self.settings_page.set_cloud_status(message)
            if not self._cloud_quiet:
                QMessageBox.information(self, "云同步完成", message)
        elif mode == "pull":
            self._apply_cloud_restore(Path(str(result.get("restore_path", ""))))
        elif mode == "test":
            self.settings_page.set_cloud_status(str(result.get("message", "连接成功")))

    def _on_cloud_failed(self, message: str) -> None:
        self._cloud_worker = None
        self.settings_page.set_cloud_status(message)
        if not self._cloud_quiet:
            QMessageBox.warning(self, "云同步失败", message)

    def _apply_cloud_restore(self, restore_path: Path) -> None:
        if not restore_path.exists():
            QMessageBox.warning(self, "恢复失败", "云端文件不存在")
            return
        if self.web_server is not None:
            self.web_server.stop()
            self.web_server = None
        exporter.backup_database(self.db.path, backups_dir())
        self.db.close()
        shutil.copy2(restore_path, db_path())
        restore_path.unlink(missing_ok=True)
        self.db = Database()
        self._build_ui()
        self.refresh_all()
        self._apply_style()
        self._apply_web_settings()
        self.settings_page.set_cloud_status("已从云端恢复")
        QMessageBox.information(self, "恢复完成", "已从云端恢复数据库。")

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
            if about_page is not None:
                self._current_about_page = about_page
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
        self._check_timer = QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.timeout.connect(self._on_check_timeout)
        self._check_timer.start(30000)
        self._check_worker.start()

    def _on_check_finished(self, info: dict) -> None:
        self._check_worker = None
        if self._check_timer is not None:
            self._check_timer.stop()
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
        if self._check_timer is not None:
            self._check_timer.stop()
        if self._current_about_page is not None:
            self._current_about_page.update_status.setText(message)

    def _on_check_timeout(self) -> None:
        if self._check_worker is not None and self._check_worker.isRunning():
            if self._current_about_page is not None:
                self._current_about_page.update_status.setText(
                    "检查更新超时，请检查网络后重试"
                )

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
        self._install_worker.progress.connect(self._on_install_progress)
        self._update_progress = QProgressDialog(
            "正在下载并校验更新包…", "", 0, 100, self
        )
        self._update_progress.setWindowTitle("软件更新")
        self._update_progress.setAutoClose(False)
        self._update_progress.setCancelButton(None)
        self._update_progress.setMinimumDuration(0)
        self._update_progress.show()
        self._install_worker.start()
        if self._current_about_page is not None:
            self._current_about_page.update_status.setText("正在下载并校验更新包…")

    def _on_install_finished(self, version: str) -> None:
        self._install_worker = None
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None
        if self._current_about_page is not None:
            self._current_about_page.clear_progress()
        QMessageBox.information(
            self,
            "更新已启动",
            f"新版 V{version} 将在软件退出后自动安装，请稍候。",
        )
        QTimer.singleShot(800, QApplication.instance().quit)

    def _on_install_failed(self, message: str) -> None:
        self._install_worker = None
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None
        if self._current_about_page is not None:
            self._current_about_page.clear_progress()
        QMessageBox.warning(
            self, "更新失败", message + "\n\n当前版本不受影响，可继续使用。"
        )

    def _on_install_progress(self, current: int, total: int) -> None:
        if self._update_progress is not None:
            if total <= 0:
                self._update_progress.setRange(0, 0)
            else:
                percent = max(0, min(100, int(current * 100 / total)))
                self._update_progress.setRange(0, 100)
                self._update_progress.setValue(percent)
                self._update_progress.setLabelText(
                    f"正在下载并校验更新包… {percent}%"
                )
        if self._current_about_page is not None:
            self._current_about_page.set_progress(current, total)

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
        apply_theme(self, self.db.conn)
