from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
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
        if is_customer():
            self.update_repo_label.setVisible(False)
            self.update_repo_edit.setVisible(False)

        note = QLabel(
            "设置会保存在本地数据库中；未自定义路径时默认使用程序目录下的 "
            "exports/ 与 backups/。API Key 仅用于请求同花顺接口，"
            "更新仓库填写 GitHub 的 owner/repo。"
        )
        note.setObjectName("fieldLabel")
        grid.addWidget(note, 7, 0, 1, 3)
        section.add_layout(grid)
        layout.addWidget(section)

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
        self.conn.commit()
        flash_saved(self.save_button)
        self.on_settings_changed()

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
