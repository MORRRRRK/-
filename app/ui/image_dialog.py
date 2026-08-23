from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
)

from ..core import repository
from ..core.paths import images_dir
from ..ui.widgets import confirm_delete, make_button


class ImagePreviewDialog(QDialog):
    def __init__(self, conn, year_id: int, month: int, on_changed, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.year_id = year_id
        self.month = month
        self.on_changed = on_changed
        self.setWindowTitle(f"{month} 月图片备注")
        self.resize(760, 520)
        self._build()
        self._reload()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        splitter = QSplitter()

        self.image_list = QListWidget()
        self.image_list.currentItemChanged.connect(self._preview)
        splitter.addWidget(self.image_list)

        self.preview_label = QLabel("选择左侧图片进行预览")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(400, 360)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.preview_label)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self.import_button = make_button("导入图片", primary=True)
        self.delete_button = make_button("删除选中")
        self.close_button = make_button("关闭")
        self.import_button.clicked.connect(self._import)
        self.delete_button.clicked.connect(self._delete_selected)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)

    def _reload(self) -> None:
        self.image_list.clear()
        self.preview_label.setText("选择左侧图片进行预览")
        self._images = repository.list_monthly_images(self.conn, self.year_id, self.month)
        for image in self._images:
            item = QListWidgetItem(Path(image["file_path"]).name)
            item.setData(Qt.UserRole, image["id"])
            item.setToolTip(image["file_path"])
            self.image_list.addItem(item)
        if self.image_list.count():
            self.image_list.setCurrentRow(0)

    def _preview(self) -> None:
        row = self.image_list.currentRow()
        if row < 0 or row >= len(self._images):
            self.preview_label.setText("没有图片")
            return
        from PySide6.QtGui import QPixmap

        path = self._images[row]["file_path"]
        if not Path(path).exists():
            self.preview_label.setText("图片文件不存在：\n" + path)
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.preview_label.setText("无法加载图片")
            return
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def _import(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择收入/支出截图",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not files:
            return
        target_dir = images_dir() / str(self.year_id) / f"{self.month:02d}"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for index, source in enumerate(files):
            source_path = Path(source)
            target = target_dir / f"{stamp}_{index}_{source_path.name}"
            shutil.copy2(source_path, target)
            repository.add_monthly_image(
                self.conn, self.year_id, self.month, str(target), source_path.name
            )
        self.conn.commit()
        self._reload()
        self.on_changed()

    def _delete_selected(self) -> None:
        row = self.image_list.currentRow()
        if row < 0 or row >= len(self._images):
            QMessageBox.information(self, "提示", "请先选择要删除的图片")
            return
        if not confirm_delete(self, "删除图片", "确定删除选中的图片备注？"):
            return
        image = self._images[row]
        path = Path(image["file_path"])
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
        repository.delete_monthly_image(self.conn, image["id"])
        self.conn.commit()
        self._reload()
        self.on_changed()
