from __future__ import annotations

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
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...core.paths import backups_dir, exports_dir
from ...services import llm
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


class SettingsPage(QWidget):
    def __init__(self, conn, on_settings_changed):
        super().__init__()
        self.conn = conn
        self.on_settings_changed = on_settings_changed
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        section = Section("常用设置")
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
        if is_customer():
            self.update_repo_label.setVisible(False)
            self.update_repo_edit.setVisible(False)
            self.github_token_label.setVisible(False)
            self.github_token_edit.setVisible(False)

        note = QLabel(
            "设置会保存在本地数据库中；未自定义路径时默认使用程序目录下的 "
            "exports/ 与 backups/。API Key 仅用于请求同花顺接口，"
            "更新仓库填写 GitHub 的 owner/repo。"
        )
        note.setObjectName("fieldLabel")
        grid.addWidget(note, 8, 0, 1, 3)
        section.add_layout(grid)
        layout.addWidget(section)

        llm_section = Section("大模型报告设置（OpenAI 兼容接口）")
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

        web_section = Section("局域网只读访问")
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
        web_note = QLabel(
            "开启后同一局域网的手机/电脑可用浏览器查看，Web 端只读；"
            "端口默认 8765，访问码用于登录保护。"
        )
        web_note.setObjectName("fieldLabel")
        web_note.setWordWrap(True)
        web_grid.addWidget(web_note, 4, 0, 1, 3)
        web_section.add_layout(web_grid)
        layout.addWidget(web_section)

        cache_section = Section("缓存清理")
        cache_layout = QHBoxLayout()
        self.clear_cache_button = make_button("清除导出与备份缓存")
        self.clear_cache_button.clicked.connect(self._clear_cache)
        cache_layout.addWidget(self.clear_cache_button)
        cache_layout.addStretch(1)
        cache_section.add_layout(cache_layout)
        layout.addWidget(cache_section)

        buttons = QHBoxLayout()
        self.save_button = make_button("保存设置", primary=True)
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.save_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
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
            repository.get_setting(self.conn, "github_token", "")
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

    def _pick_export_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if directory:
            self.export_dir_edit.setText(directory)

    def _pick_backup_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择备份目录")
        if directory:
            self.backup_dir_edit.setText(directory)

    def _save(self) -> None:
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
            self.conn, "llm_base_url", self.llm_base_url_edit.text().strip()
        )
        repository.set_setting(
            self.conn, "llm_api_key", self.llm_api_key_edit.text().strip()
        )
        repository.set_setting(
            self.conn, "llm_model", self.llm_model_edit.text().strip()
        )
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
        flash_saved(self.save_button)
        self.on_settings_changed()

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
        self._load()
