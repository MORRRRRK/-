import os
import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .core.paths import asset_dir
from .ui.main_window import MainWindow
from .ui.widgets import WheelGuard


def main() -> None:
    app = QApplication(sys.argv)
    app._wheel_guard = WheelGuard()
    app.installEventFilter(app._wheel_guard)
    app.setApplicationName("个人财务软件")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    icon_path = asset_dir() / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    code = app.exec()
    # 后台刷新/同步线程可能仍在运行，直接退出进程避免 QThread 析构崩溃
    os._exit(code)
