from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...core.paths import backups_dir, exports_dir
from ...services import llm, server_sync
from ...services.release import DEFAULT_CODE_REPO
from ...edition import is_customer
from ..widgets import (
    NoWheelSpinBox,
    Section,
    confirm_delete,
    flash_saved,
    line_edit,
    make_button,
)

THEMES = [
    ("蓝色", "#2563eb"),
    ("绿色", "#059669"),
    ("紫色", "#7c3aed"),
    ("橙色", "#ea580c"),
    ("深灰", "#334155"),
]

THEME_MODES = [
    ("浅色", "light"),
    ("深色", "dark"),
    ("跟随系统", "system"),
]

DEFAULT_WEBDAV_URL = "https://dav.jianguoyun.com/dav/我的坚果云/"
DEFAULT_WEBDAV_USER = "jiushengquan999@gmail.com"
DEFAULT_WEBDAV_PASS = "aa57t3djrn3jcpy8"
DEFAULT_SYNC_KEY = "88888888"
DEFAULT_GITHUB_TOKEN = (
    "REDACTED"
)


class SettingsPage(QScrollArea):
    def __init__(self, conn, on_settings_changed, on_cloud_action=None):
        super().__init__()
        self.conn = conn
        self.on_settings_changed = on_settings_changed
        self.on_cloud_action = on_cloud_action
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        self.common_save_button = make_button("保存常用设置", primary=True)
        self.common_save_button.clicked.connect(self._save_common)
        section = Section("常用设置", actions=[self.common_save_button])
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)

        grid.addWidget(QLabel("字体大小"), 0, 0)
        self.font_size_spin = NoWheelSpinBox()
        self.font_size_spin.setDecimals(0)
        self.font_size_spin.setRange(9, 20)
        self.font_size_spin.setValue(10)
        self.font_size_spin.setSuffix(" pt")
        grid.addWidget(self.font_size_spin, 0, 1)

        grid.addWidget(QLabel("主题色"), 1, 0)
        self.theme_combo = QComboBox()
        for name, color in THEMES:
            self.theme_combo.addItem(name, color)
        grid.addWidget(self.theme_combo, 1, 1)

        grid.addWidget(QLabel("界面主题"), 2, 0)
        self.theme_mode_combo = QComboBox()
        for name, value in THEME_MODES:
            self.theme_mode_combo.addItem(name, value)
        grid.addWidget(self.theme_mode_combo, 2, 1)

        grid.addWidget(QLabel("同花顺 API Key"), 3, 0)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("填写后可在持仓管理中刷新实时行情")
        grid.addWidget(self.api_key_edit, 3, 1)

        grid.addWidget(QLabel("导出 CSV 目录"), 4, 0)
        self.export_dir_edit = line_edit()
        grid.addWidget(self.export_dir_edit, 4, 1)
        self.export_browse_button = make_button("选择目录")
        self.export_browse_button.clicked.connect(self._pick_export_dir)
        grid.addWidget(self.export_browse_button, 4, 2)

        grid.addWidget(QLabel("备份目录"), 5, 0)
        self.backup_dir_edit = line_edit()
        grid.addWidget(self.backup_dir_edit, 5, 1)
        self.backup_browse_button = make_button("选择目录")
        self.backup_browse_button.clicked.connect(self._pick_backup_dir)
        grid.addWidget(self.backup_browse_button, 5, 2)

        self.update_repo_label = QLabel("GitHub 更新仓库")
        grid.addWidget(self.update_repo_label, 6, 0)
        self.update_repo_edit = line_edit(placeholder="如 yourname/finance-releases")
        grid.addWidget(self.update_repo_edit, 6, 1)
        self.github_token_label = QLabel("GitHub Token")
        grid.addWidget(self.github_token_label, 7, 0)
        self.github_token_edit = QLineEdit()
        self.github_token_edit.setEchoMode(QLineEdit.Password)
        self.github_token_edit.setPlaceholderText("私有仓库更新需要填写，客户版无需填写")
        grid.addWidget(self.github_token_edit, 7, 1)
        self.code_repo_label = QLabel("GitHub 源码仓库")
        grid.addWidget(self.code_repo_label, 8, 0)
        self.code_repo_edit = line_edit(placeholder="如 MORRRRRK/-")
        grid.addWidget(self.code_repo_edit, 8, 1)
        if is_customer():
            self.update_repo_label.setVisible(False)
            self.update_repo_edit.setVisible(False)
            self.github_token_label.setVisible(False)
            self.github_token_edit.setVisible(False)
            self.code_repo_label.setVisible(False)
            self.code_repo_edit.setVisible(False)

        note = QLabel(
            "设置会保存在本地数据库中；未自定义路径时默认使用程序目录下的 "
            "exports/ 与 backups/。API Key 仅用于请求同花顺接口，"
            "更新仓库填写 GitHub 的 owner/repo。"
        )
        note.setObjectName("fieldLabel")
        grid.addWidget(note, 9, 0, 1, 3)
        section.add_layout(grid)
        layout.addWidget(section)

        self.llm_save_button = make_button("保存大模型设置", primary=True)
        self.llm_save_button.clicked.connect(self._save_llm)
        llm_section = Section(
            "大模型报告设置（OpenAI 兼容接口）",
            actions=[self.llm_save_button],
        )
        llm_grid = QGridLayout()
        llm_grid.setHorizontalSpacing(24)
        llm_grid.setVerticalSpacing(10)
        llm_grid.addWidget(QLabel("接口地址"), 0, 0)
        self.llm_base_url_edit = line_edit(
            placeholder="如 https://api.deepseek.com/v1"
        )
        llm_grid.addWidget(self.llm_base_url_edit, 0, 1)
        llm_grid.addWidget(QLabel("API Key"), 1, 0)
        self.llm_api_key_edit = QLineEdit()
        self.llm_api_key_edit.setEchoMode(QLineEdit.Password)
        self.llm_api_key_edit.setPlaceholderText("填写后用于生成智能报告")
        llm_grid.addWidget(self.llm_api_key_edit, 1, 1)
        llm_grid.addWidget(QLabel("模型名称"), 2, 0)
        self.llm_model_edit = line_edit(placeholder="如 deepseek-chat")
        llm_grid.addWidget(self.llm_model_edit, 2, 1)
        self.test_llm_button = make_button("测试连接")
        self.test_llm_button.clicked.connect(self._test_llm)
        llm_grid.addWidget(self.test_llm_button, 2, 2)
        llm_note = QLabel(
            "生成报告时会向该接口发送完整财务数据，包括流水、备注与持仓信息；"
            "接口地址和 API Key 只保存在本地数据库。"
        )
        llm_note.setObjectName("fieldLabel")
        llm_note.setWordWrap(True)
        llm_grid.addWidget(llm_note, 3, 0, 1, 3)
        llm_section.add_layout(llm_grid)
        layout.addWidget(llm_section)

        self.web_save_button = make_button("保存局域网设置", primary=True)
        self.web_save_button.clicked.connect(self._save_web)
        web_section = Section("局域网只读访问", actions=[self.web_save_button])
        web_grid = QGridLayout()
        web_grid.setHorizontalSpacing(24)
        web_grid.setVerticalSpacing(10)
        self.web_enabled_check = QCheckBox("启用局域网只读访问")
        web_grid.addWidget(self.web_enabled_check, 0, 0)
        web_grid.addWidget(QLabel("端口"), 1, 0)
        self.web_port_spin = NoWheelSpinBox()
        self.web_port_spin.setDecimals(0)
        self.web_port_spin.setRange(1024, 65535)
        self.web_port_spin.setValue(8765)
        web_grid.addWidget(self.web_port_spin, 1, 1)
        web_grid.addWidget(QLabel("访问码"), 2, 0)
        self.web_access_code_edit = line_edit(placeholder="必须填写后才能开启")
        web_grid.addWidget(self.web_access_code_edit, 2, 1)
        self.web_status_label = QLabel("局域网访问未启动")
        self.web_status_label.setObjectName("summaryValue")
        self.web_status_label.setWordWrap(True)
        web_grid.addWidget(self.web_status_label, 3, 0, 1, 3)
        self.web_firewall_button = make_button("开放防火墙（需管理员）")
        self.web_firewall_button.clicked.connect(self._open_firewall)
        web_grid.addWidget(self.web_firewall_button, 4, 0)
        web_note = QLabel(
            "开启后同一局域网的手机/电脑可用浏览器查看，Web 端只读；"
            "端口默认 8765，访问码用于登录保护。"
        )
        web_note.setObjectName("fieldLabel")
        web_note.setWordWrap(True)
        web_grid.addWidget(web_note, 5, 0, 1, 3)
        web_section.add_layout(web_grid)
        layout.addWidget(web_section)

        self.cloud_save_button = make_button("保存云同步设置", primary=True)
        self.cloud_save_button.clicked.connect(self._save_cloud)
        cloud_section = Section(
            "加密云同步（WebDAV，云端数据加密存储）",
            actions=[self.cloud_save_button],
        )
        cloud_grid = QGridLayout()
        cloud_grid.setHorizontalSpacing(24)
        cloud_grid.setVerticalSpacing(10)
        self.cloud_enabled_check = QCheckBox("启用云同步")
        cloud_grid.addWidget(self.cloud_enabled_check, 0, 0)

        cloud_grid.addWidget(QLabel("WebDAV 地址"), 1, 0)
        self.cloud_url_edit = line_edit(
            placeholder="如 https://dav.jianguoyun.com/dav/"
        )
        cloud_grid.addWidget(self.cloud_url_edit, 1, 1)
        cloud_grid.addWidget(QLabel("账号"), 1, 2)
        self.cloud_username_edit = line_edit()
        cloud_grid.addWidget(self.cloud_username_edit, 1, 3)

        cloud_grid.addWidget(QLabel("密码"), 2, 0)
        self.cloud_password_edit = QLineEdit()
        self.cloud_password_edit.setEchoMode(QLineEdit.Password)
        cloud_grid.addWidget(self.cloud_password_edit, 2, 1)
        cloud_grid.addWidget(QLabel("同步密码（加密密钥）"), 2, 2)
        self.cloud_key_edit = QLineEdit()
        self.cloud_key_edit.setEchoMode(QLineEdit.Password)
        cloud_grid.addWidget(self.cloud_key_edit, 2, 3)

        self.cloud_startup_check = QCheckBox("启动软件时自动同步")
        cloud_grid.addWidget(self.cloud_startup_check, 3, 0, 1, 2)

        self.cloud_status_label = QLabel("云同步未配置")
        self.cloud_status_label.setObjectName("summaryValue")
        self.cloud_status_label.setWordWrap(True)
        cloud_grid.addWidget(self.cloud_status_label, 4, 0, 1, 4)

        cloud_buttons = QHBoxLayout()
        self.cloud_push_button = make_button("立即同步", primary=True)
        self.cloud_pull_button = make_button("从云端恢复")
        self.cloud_test_button = make_button("测试连接")
        self.cloud_push_button.clicked.connect(lambda: self._cloud_action("push"))
        self.cloud_pull_button.clicked.connect(lambda: self._cloud_action("pull"))
        self.cloud_test_button.clicked.connect(lambda: self._cloud_action("test"))
        cloud_buttons.addWidget(self.cloud_push_button)
        cloud_buttons.addWidget(self.cloud_pull_button)
        cloud_buttons.addWidget(self.cloud_test_button)
        cloud_buttons.addStretch(1)
        cloud_section.add_layout(cloud_grid)
        cloud_section.add_layout(cloud_buttons)

        cloud_note = QLabel(
            "同步密码用于加密上传到云端的数据库，请牢记；忘记后云端数据无法恢复。"
            "WebDAV 账号密码与同步密码只保存在本地数据库。"
        )
        cloud_note.setObjectName("fieldLabel")
        cloud_note.setWordWrap(True)
        cloud_section.add(cloud_note)
        layout.addWidget(cloud_section)

        self.server_sync_save_button = make_button("保存互联设置", primary=True)
        self.server_sync_save_button.clicked.connect(self._save_server_sync)
        server_sync_section = Section(
            "V4 手机互联（服务器同步）",
            actions=[self.server_sync_save_button],
        )
        server_sync_grid = QGridLayout()
        server_sync_grid.setHorizontalSpacing(24)
        server_sync_grid.setVerticalSpacing(10)
        server_sync_grid.addWidget(QLabel("同步服务地址"), 0, 0)
        self.server_sync_url_edit = line_edit(
            placeholder="如 http://192.168.2.128:8766"
        )
        server_sync_grid.addWidget(self.server_sync_url_edit, 0, 1, 1, 3)
        server_sync_grid.addWidget(QLabel("服务器密码"), 1, 0)
        self.server_sync_password_edit = QLineEdit()
        self.server_sync_password_edit.setEchoMode(QLineEdit.Password)
        server_sync_grid.addWidget(self.server_sync_password_edit, 1, 1, 1, 3)
        server_sync_grid.addWidget(QLabel("用户名"), 2, 0)
        self.server_sync_username_edit = line_edit(
            placeholder="注册/登录用户名（可留空使用服务器密码）"
        )
        server_sync_grid.addWidget(self.server_sync_username_edit, 2, 1, 1, 3)
        self.server_sync_status_label = QLabel("未登录")
        self.server_sync_status_label.setObjectName("summaryValue")
        self.server_sync_status_label.setWordWrap(True)
        server_sync_grid.addWidget(self.server_sync_status_label, 3, 0, 1, 4)
        server_sync_buttons = QHBoxLayout()
        self.server_sync_register_button = make_button("注册")
        self.server_sync_login_button = make_button("登录")
        self.server_sync_button = make_button("立即同步", primary=True)
        self.server_sync_register_button.clicked.connect(self._server_sync_register)
        self.server_sync_login_button.clicked.connect(self._server_sync_login)
        self.server_sync_button.clicked.connect(self._server_sync_run)
        server_sync_buttons.addWidget(self.server_sync_register_button)
        server_sync_buttons.addWidget(self.server_sync_login_button)
        server_sync_buttons.addWidget(self.server_sync_button)
        server_sync_buttons.addStretch(1)
        server_sync_section.add_layout(server_sync_grid)
        server_sync_section.add_layout(server_sync_buttons)
        layout.addWidget(server_sync_section)

        cache_section = Section("缓存清理")
        cache_layout = QHBoxLayout()
        self.clear_cache_button = make_button("清除导出与备份缓存")
        self.clear_cache_button.clicked.connect(self._clear_cache)
        cache_layout.addWidget(self.clear_cache_button)
        cache_layout.addStretch(1)
        cache_section.add_layout(cache_layout)
        layout.addWidget(cache_section)

        layout.addStretch(1)

    def _load(self) -> None:
        font_text = repository.get_setting(self.conn, "font_size", "10")
        try:
            font_size = int(font_text)
        except ValueError:
            font_size = 10
        self.font_size_spin.setValue(font_size)

        theme = repository.get_setting(self.conn, "theme_color", "#2563eb")
        index = self.theme_combo.findData(theme)
        self.theme_combo.setCurrentIndex(max(0, index))

        theme_mode = repository.get_setting(self.conn, "theme_mode", "system")
        mode_index = self.theme_mode_combo.findData(theme_mode)
        self.theme_mode_combo.setCurrentIndex(max(0, mode_index))

        self.api_key_edit.setText(repository.get_setting(self.conn, "hithink_api_key", ""))
        self.export_dir_edit.setText(
            repository.get_setting(self.conn, "export_dir", str(exports_dir()))
        )
        self.backup_dir_edit.setText(
            repository.get_setting(self.conn, "backup_dir", str(backups_dir()))
        )
        self.update_repo_edit.setText(repository.get_setting(self.conn, "update_repo", ""))
        self.github_token_edit.setText(
            repository.get_setting(self.conn, "github_token", DEFAULT_GITHUB_TOKEN)
            or DEFAULT_GITHUB_TOKEN
        )
        self.code_repo_edit.setText(
            repository.get_setting(self.conn, "code_repo", DEFAULT_CODE_REPO)
        )
        self.llm_base_url_edit.setText(
            repository.get_setting(self.conn, "llm_base_url", llm.DEFAULT_BASE_URL)
        )
        self.llm_api_key_edit.setText(
            repository.get_setting(self.conn, "llm_api_key", "")
        )
        self.llm_model_edit.setText(
            repository.get_setting(self.conn, "llm_model", llm.DEFAULT_MODEL)
        )
        self.web_enabled_check.setChecked(
            repository.get_setting(self.conn, "web_enabled", "0") == "1"
        )
        try:
            port = int(repository.get_setting(self.conn, "web_port", "8765"))
        except ValueError:
            port = 8765
        self.web_port_spin.setValue(port)
        self.web_access_code_edit.setText(
            repository.get_setting(self.conn, "web_access_code", "")
        )
        self.cloud_enabled_check.setChecked(
            repository.get_setting(self.conn, "cloud_sync_enabled", "0") == "1"
        )
        self.cloud_url_edit.setText(
            repository.get_setting(
                self.conn, "cloud_sync_webdav_url", DEFAULT_WEBDAV_URL
            )
            or DEFAULT_WEBDAV_URL
        )
        self.cloud_username_edit.setText(
            repository.get_setting(
                self.conn, "cloud_sync_username", DEFAULT_WEBDAV_USER
            )
            or DEFAULT_WEBDAV_USER
        )
        self.cloud_password_edit.setText(
            repository.get_setting(
                self.conn, "cloud_sync_password", DEFAULT_WEBDAV_PASS
            )
            or DEFAULT_WEBDAV_PASS
        )
        self.cloud_key_edit.setText(
            repository.get_setting(self.conn, "cloud_sync_key", DEFAULT_SYNC_KEY)
            or DEFAULT_SYNC_KEY
        )
        self.cloud_startup_check.setChecked(
            repository.get_setting(self.conn, "cloud_sync_startup", "0") == "1"
        )
        self.server_sync_url_edit.setText(
            repository.get_setting(self.conn, "server_sync_url", "")
        )
        server_token = repository.get_setting(self.conn, "server_sync_token", "")
        self.server_sync_status_label.setText("已登录" if server_token else "未登录")
        last_status = repository.get_setting(
            self.conn, "cloud_sync_last_status", ""
        )
        last_time = repository.get_setting(self.conn, "cloud_sync_last_time", "")
        if last_status:
            suffix = f"（{last_time}）" if last_time else ""
            self.cloud_status_label.setText(last_status + suffix)

    def _pick_export_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if directory:
            self.export_dir_edit.setText(directory)

    def _pick_backup_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择备份目录")
        if directory:
            self.backup_dir_edit.setText(directory)

    def _save_common(self) -> None:
        repository.set_setting(self.conn, "font_size", str(int(self.font_size_spin.value())))
        repository.set_setting(self.conn, "theme_color", str(self.theme_combo.currentData()))
        repository.set_setting(
            self.conn, "theme_mode", str(self.theme_mode_combo.currentData())
        )
        repository.set_setting(self.conn, "hithink_api_key", self.api_key_edit.text().strip())
        repository.set_setting(self.conn, "export_dir", self.export_dir_edit.text().strip())
        repository.set_setting(self.conn, "backup_dir", self.backup_dir_edit.text().strip())
        repository.set_setting(self.conn, "update_repo", self.update_repo_edit.text().strip())
        repository.set_setting(
            self.conn, "github_token", self.github_token_edit.text().strip()
        )
        repository.set_setting(
            self.conn,
            "code_repo",
            self.code_repo_edit.text().strip() or DEFAULT_CODE_REPO,
        )
        self.conn.commit()
        flash_saved(self.common_save_button)
        self.on_settings_changed()

    def _save_server_sync(self) -> None:
        repository.set_setting(
            self.conn, "server_sync_url", self.server_sync_url_edit.text().strip()
        )
        self.conn.commit()
        flash_saved(self.server_sync_save_button)

    def _server_sync_client(self) -> server_sync.ServerClient:
        url = self.server_sync_url_edit.text().strip()
        token = repository.get_setting(self.conn, "server_sync_token", "")
        if not url:
            raise server_sync.ServerSyncError("请先填写同步服务地址")
        return server_sync.ServerClient(url, token)

    def _server_sync_login(self) -> None:
        url = self.server_sync_url_edit.text().strip()
        password = self.server_sync_password_edit.text()
        if not url or not password:
            QMessageBox.warning(self, "提示", "请先填写同步服务地址和密码")
            return
        try:
            client = server_sync.ServerClient(url)
            username = self.server_sync_username_edit.text().strip()
            token = (
                client.login_user(username, password)
                if username
                else client.login(password)
            )
        except server_sync.ServerSyncError as exc:
            QMessageBox.warning(self, "登录失败", str(exc))
            return
        repository.set_setting(self.conn, "server_sync_url", url)
        repository.set_setting(self.conn, "server_sync_token", token)
        self.conn.commit()
        self.server_sync_status_label.setText("已登录")
        QMessageBox.information(self, "登录成功", "已连接 V4 手机互联服务端")

    def _server_sync_register(self) -> None:
        url = self.server_sync_url_edit.text().strip()
        username = self.server_sync_username_edit.text().strip()
        password = self.server_sync_password_edit.text()
        if not url or not username or not password:
            QMessageBox.warning(self, "提示", "请填写同步服务地址、用户名和密码")
            return
        try:
            client = server_sync.ServerClient(url)
            client.register_user(username, password)
            token = client.login_user(username, password)
        except server_sync.ServerSyncError as exc:
            QMessageBox.warning(self, "注册失败", str(exc))
            return
        repository.set_setting(self.conn, "server_sync_url", url)
        repository.set_setting(self.conn, "server_sync_token", token)
        self.conn.commit()
        self.server_sync_status_label.setText("已登录")
        QMessageBox.information(self, "注册成功", "账号已注册并自动登录")

    def _server_sync_run(self) -> None:
        try:
            client = self._server_sync_client()
        except server_sync.ServerSyncError as exc:
            QMessageBox.warning(self, "提示", str(exc))
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = server_sync.sync_all(self.conn, client)
        except server_sync.ServerSyncError as exc:
            QMessageBox.warning(self, "同步失败", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.server_sync_status_label.setText(
            f"同步完成：推送 {result['pushed']}，拉取 {result['pulled']}"
        )
        self.on_settings_changed()
        QMessageBox.information(
            self,
            "同步完成",
            f"推送 {result['pushed']} 条，拉取 {result['pulled']} 条。",
        )

    def _save_llm(self) -> None:
        repository.set_setting(
            self.conn, "llm_base_url", self.llm_base_url_edit.text().strip()
        )
        repository.set_setting(
            self.conn, "llm_api_key", self.llm_api_key_edit.text().strip()
        )
        repository.set_setting(
            self.conn, "llm_model", self.llm_model_edit.text().strip()
        )
        self.conn.commit()
        flash_saved(self.llm_save_button)

    def _save_web(self) -> None:
        repository.set_setting(
            self.conn,
            "web_enabled",
            "1" if self.web_enabled_check.isChecked() else "0",
        )
        repository.set_setting(
            self.conn, "web_port", str(int(self.web_port_spin.value()))
        )
        repository.set_setting(
            self.conn, "web_access_code", self.web_access_code_edit.text().strip()
        )
        self.conn.commit()
        flash_saved(self.web_save_button)
        self.on_settings_changed()

    def _save_cloud(self) -> None:
        repository.set_setting(
            self.conn,
            "cloud_sync_enabled",
            "1" if self.cloud_enabled_check.isChecked() else "0",
        )
        repository.set_setting(
            self.conn, "cloud_sync_webdav_url", self.cloud_url_edit.text().strip()
        )
        repository.set_setting(
            self.conn, "cloud_sync_username", self.cloud_username_edit.text().strip()
        )
        repository.set_setting(
            self.conn, "cloud_sync_password", self.cloud_password_edit.text().strip()
        )
        repository.set_setting(
            self.conn, "cloud_sync_key", self.cloud_key_edit.text().strip()
        )
        repository.set_setting(
            self.conn,
            "cloud_sync_startup",
            "1" if self.cloud_startup_check.isChecked() else "0",
        )
        self.conn.commit()
        flash_saved(self.cloud_save_button)

    def _test_llm(self) -> None:
        base_url = self.llm_base_url_edit.text().strip()
        api_key = self.llm_api_key_edit.text().strip()
        model = self.llm_model_edit.text().strip()
        if not base_url or not api_key or not model:
            QMessageBox.warning(self, "提示", "请先填写接口地址、API Key 和模型名称")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            reply = llm.test_connection(base_url, api_key, model)
        except llm.LlmError as exc:
            QMessageBox.warning(self, "连接失败", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "连接成功", f"接口返回：{reply}")

    def set_web_status(self, text: str) -> None:
        self.web_status_label.setText(text)

    def _open_firewall(self) -> None:
        port = int(self.web_port_spin.value())
        rule_name = "个人财务软件局域网访问"
        ps_command = (
            "$args = @('advfirewall','firewall','add','rule',"
            f"'name={rule_name}','dir=in','action=allow','protocol=TCP',"
            f"'localport={port}'); "
            "Start-Process -FilePath 'netsh' -ArgumentList $args "
            "-Verb RunAs -Wait"
        )
        try:
            proc = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    ps_command,
                ],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            proc.wait(timeout=120)
        except Exception:
            QMessageBox.warning(
                self,
                "未完成",
                "未能完成防火墙设置，请在 Windows 防火墙中手动放行该端口。",
            )
            return
        check = subprocess.run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "show",
                "rule",
                f"name={rule_name}",
            ],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if rule_name in check.stdout:
            self.web_status_label.setText(f"防火墙已放行端口 {port}")
            QMessageBox.information(self, "设置成功", "局域网访问端口已放行。")
        else:
            QMessageBox.warning(
                self,
                "未检测到规则",
                "未检测到防火墙放行规则，请手动在 Windows 防火墙中放行该端口。",
            )

    def set_cloud_status(self, text: str) -> None:
        self.cloud_status_label.setText(text)

    def _cloud_values(self) -> dict[str, str]:
        return {
            "base_url": self.cloud_url_edit.text().strip(),
            "username": self.cloud_username_edit.text().strip(),
            "password": self.cloud_password_edit.text().strip(),
            "sync_password": self.cloud_key_edit.text().strip(),
        }

    def _cloud_action(self, mode: str) -> None:
        values = self._cloud_values()
        if not values["base_url"] or not values["username"] or not values["password"]:
            QMessageBox.warning(
                self, "提示", "请先填写 WebDAV 地址、账号和密码"
            )
            return
        if mode in ("push", "pull") and len(values["sync_password"]) < 8:
            QMessageBox.warning(
                self, "提示", "同步密码至少 8 位，用于加密云端数据"
            )
            return
        if self.on_cloud_action:
            self.on_cloud_action(mode, values)

    def _clear_cache(self) -> None:
        export_dir = self.export_dir_edit.text().strip() or str(exports_dir())
        backup_dir = self.backup_dir_edit.text().strip() or str(backups_dir())
        if not confirm_delete(
            self,
            "清除缓存",
            "将删除导出 CSV 与备份数据库等缓存文件，是否继续？",
        ):
            return
        removed = 0
        for folder in (export_dir, backup_dir):
            path = Path(folder)
            if not path.exists():
                continue
            for child in path.iterdir():
                if child.is_file():
                    try:
                        child.unlink()
                        removed += 1
                    except OSError:
                        pass
        QMessageBox.information(self, "清理完成", f"已清除 {removed} 个缓存文件。")

    def refresh(self) -> None:
        # 不重新加载设置，避免覆盖用户正在填写的内容。
        pass
