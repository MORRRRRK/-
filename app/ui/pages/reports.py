from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core import paths, repository
from ...services import llm
from ..widgets import (
    NoWheelSpinBox,
    Section,
    confirm_delete,
    flash_saved,
    make_button,
)

REPORT_TYPES = [
    ("账单报告", "bill"),
    ("工资报告", "salary"),
    ("资产规划建议", "planning"),
    ("综合财务报告", "custom"),
]

TYPE_NAMES = {
    "bill": "账单报告",
    "salary": "工资报告",
    "planning": "资产规划建议",
    "custom": "综合财务报告",
}


class ReportWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        context: dict,
        report_type: str,
        period_label: str,
        base_url: str,
        api_key: str,
        model: str,
        parent=None,
    ):
        super().__init__(parent)
        self.context = context
        self.report_type = report_type
        self.period_label = period_label
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def run(self) -> None:
        try:
            content = llm.generate_report_text(
                self.context,
                self.report_type,
                self.period_label,
                self.base_url,
                self.api_key,
                self.model,
            )
        except llm.LlmError as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(content)


class ReportsPage(QScrollArea):
    def __init__(self, conn, on_change):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._report_ids: list[int] = []
        self._deleted_reports: list[dict] = []
        self._worker: ReportWorker | None = None
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form_section = Section(
            "生成智能报告",
            info=(
                "报告为手动生成，不会自动调用接口。\n"
                "账单报告参考记账流水，工资报告参考工资管理，"
                "资产规划建议参考资产总览与规划结果。"
            ),
        )
        form = QHBoxLayout()
        self.type_combo = QComboBox()
        for label, value in REPORT_TYPES:
            self.type_combo.addItem(label, value)
        self.type_combo.currentIndexChanged.connect(self._toggle_period_inputs)
        self._period_labels: list[QLabel] = []
        form.addWidget(QLabel("报告类型"))
        form.addWidget(self.type_combo)

        self.year_spin = NoWheelSpinBox()
        self.year_spin.setDecimals(0)
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(_default_year())
        self.year_spin.setAlignment(Qt.AlignRight)
        form.addWidget(QLabel("年份"))
        form.addWidget(self.year_spin)

        self.month_combo = QComboBox()
        self.month_combo.addItem("全年", 0)
        self.month_combo.addItems([f"{m} 月" for m in range(1, 13)])
        form.addWidget(self.month_combo)

        self.start_date_edit = QDateEdit(QDate(_default_year(), 1, 1))
        self.end_date_edit = QDateEdit(QDate(_default_year(), 12, 31))
        for edit in (self.start_date_edit, self.end_date_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.start_label = QLabel("起始")
        self.end_label = QLabel("结束")
        self._period_labels = [self.start_label, self.end_label]
        form.addWidget(self.start_label)
        form.addWidget(self.start_date_edit)
        form.addWidget(self.end_label)
        form.addWidget(self.end_date_edit)

        self.generate_button = make_button("生成报告", primary=True)
        self.generate_button.clicked.connect(self._generate)
        form.addWidget(self.generate_button)
        self.status_label = QLabel("")
        self.status_label.setObjectName("fieldLabel")
        form.addWidget(self.status_label)
        form_section.add_layout(form)

        self.consent_check = QCheckBox(
            "我已了解并同意：生成报告会将完整财务数据发送到所填大模型接口"
        )
        form_section.add(self.consent_check)
        layout.addWidget(form_section)

        history_section = Section("报告历史")
        buttons = QHBoxLayout()
        self.view_button = make_button("查看选中")
        self.copy_button = make_button("复制内容")
        self.export_button = make_button("导出 Markdown")
        self.delete_button = make_button("删除")
        self.undo_button = make_button("撤销删除")
        self.refresh_button = make_button("刷新")
        self.view_button.clicked.connect(self._view_selected)
        self.copy_button.clicked.connect(self._copy_selected)
        self.export_button.clicked.connect(self._export_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.undo_button.clicked.connect(self._undo_delete)
        self.refresh_button.clicked.connect(self._reload_reports)
        for button in (
            self.view_button,
            self.copy_button,
            self.export_button,
            self.delete_button,
            self.undo_button,
            self.refresh_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        history_section.add_layout(buttons)

        self.reports_table = QTableWidget(0, 5)
        self.reports_table.setHorizontalHeaderLabels(
            ["类型", "标题", "时间段", "模型", "生成时间"]
        )
        self.reports_table.verticalHeader().setVisible(False)
        self.reports_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.reports_table.itemSelectionChanged.connect(self._view_selected)
        history_section.add(self.reports_table)
        layout.addWidget(history_section, 1)

        preview_section = Section("报告预览")
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        preview_section.add(self.preview)
        layout.addWidget(preview_section, 2)

        self._toggle_period_inputs()
        self.refresh()

    def _toggle_period_inputs(self) -> None:
        report_type = self.type_combo.currentData()
        self.year_spin.setVisible(report_type in ("bill", "salary", "planning"))
        self.month_combo.setVisible(report_type in ("bill", "salary"))
        for label in self._period_labels:
            label.setVisible(report_type == "custom")
        self.start_date_edit.setVisible(report_type == "custom")
        self.end_date_edit.setVisible(report_type == "custom")

    def _report_values(self) -> tuple[str, str, str]:
        report_type = self.type_combo.currentData()
        year = int(self.year_spin.value())
        if report_type == "planning":
            return report_type, f"{year} 年", f"{year}-01-01~{year}-12-31"
        if report_type in ("bill", "salary"):
            month = int(self.month_combo.currentData() or 0)
            if month:
                return (
                    report_type,
                    f"{year} 年 {month} 月",
                    f"{year}-{month:02d}-01~{year}-{month:02d}-31",
                )
            return report_type, f"{year} 年", f"{year}-01-01~{year}-12-31"
        start = self.start_date_edit.date().toString("yyyy-MM-dd")
        end = self.end_date_edit.date().toString("yyyy-MM-dd")
        return report_type, f"{start} 至 {end}", f"{start}~{end}"

    def _generate(self) -> None:
        if not self.consent_check.isChecked():
            QMessageBox.warning(
                self, "需要确认", "请先勾选“已了解并同意发送完整财务数据”"
            )
            return
        base_url = repository.get_setting(
            self.conn, "llm_base_url", llm.DEFAULT_BASE_URL
        ).strip() or llm.DEFAULT_BASE_URL
        api_key = repository.get_setting(self.conn, "llm_api_key", "").strip()
        model = repository.get_setting(
            self.conn, "llm_model", llm.DEFAULT_MODEL
        ).strip() or llm.DEFAULT_MODEL
        if not base_url or not api_key or not model:
            QMessageBox.warning(
                self, "缺少配置", "请先在“设置”中填写大模型接口地址、API Key 和模型名称"
            )
            return
        report_type, title, period = self._report_values()
        self.status_label.setText("正在生成报告，请稍候…")
        self.generate_button.setEnabled(False)
        start = period.split("~")[0] if "~" in period else ""
        end = period.split("~")[1] if "~" in period else ""
        try:
            context = llm.build_financial_context(
                self.conn, report_type, start, end
            )
        except Exception as exc:
            self.status_label.setText("")
            self.generate_button.setEnabled(True)
            QMessageBox.warning(self, "生成失败", f"读取财务数据失败：{exc}")
            return
        self._worker = ReportWorker(
            context,
            report_type,
            title,
            base_url,
            api_key,
            model,
            self,
        )
        self._worker.finished.connect(lambda content, t=title, p=period: self._on_finished(content, t, p))
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_finished(self, content: str, title: str, period: str) -> None:
        self._worker = None
        self.generate_button.setEnabled(True)
        self.status_label.setText("报告生成成功")
        report_type = self.type_combo.currentData()
        model = repository.get_setting(self.conn, "llm_model", "").strip()
        repository.add_ai_report(
            self.conn,
            {
                "report_type": report_type,
                "title": title,
                "period_start": period.split("~")[0],
                "period_end": period.split("~")[1] if "~" in period else "",
                "content": content,
                "model": model,
            },
        )
        self.conn.commit()
        flash_saved(self.generate_button)
        self._reload_reports()
        self.preview.setMarkdown(content)
        self.on_change()

    def _on_failed(self, message: str) -> None:
        self._worker = None
        self.generate_button.setEnabled(True)
        self.status_label.setText("")
        QMessageBox.warning(self, "生成失败", message)

    def _reload_reports(self) -> None:
        reports = repository.list_ai_reports(self.conn)
        self._report_ids = [r["id"] for r in reports]
        self.reports_table.setRowCount(len(reports))
        for row, report in enumerate(reports):
            values = [
                TYPE_NAMES.get(report["report_type"], report["report_type"]),
                report["title"],
                report["period_start"] + (f" ~ {report['period_end']}" if report["period_end"] else ""),
                report["model"],
                report["created_at"],
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignCenter)
                self.reports_table.setItem(row, col, item)
        self.reports_table.resizeColumnsToContents()

    def _selected_report(self) -> dict | None:
        row = self.reports_table.currentRow()
        if row < 0 or row >= len(self._report_ids):
            return None
        report_id = self._report_ids[row]
        for report in repository.list_ai_reports(self.conn):
            if report["id"] == report_id:
                return report
        return None

    def _view_selected(self) -> None:
        report = self._selected_report()
        if report:
            self.preview.setMarkdown(report["content"])

    def _copy_selected(self) -> None:
        report = self._selected_report()
        if not report:
            QMessageBox.information(self, "提示", "请先选择一份报告")
            return
        QApplication.clipboard().setText(report["content"])
        QMessageBox.information(self, "复制完成", "报告内容已复制到剪贴板")

    def _export_selected(self) -> None:
        report = self._selected_report()
        if not report:
            QMessageBox.information(self, "提示", "请先选择一份报告")
            return
        exports = Path(repository.get_setting(self.conn, "export_dir", str(paths.exports_dir())))
        exports.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = exports / f"ai_report_{stamp}.md"
        target.write_text(report["content"], encoding="utf-8")
        QMessageBox.information(self, "导出完成", f"已导出到：\n{target}")

    def _delete_selected(self) -> None:
        report = self._selected_report()
        if report is None or not confirm_delete(
            self, "删除报告", f"确定删除“{report['title']}”？"
        ):
            return
        repository.delete_ai_report(self.conn, report["id"])
        self._deleted_reports.append(report)
        self.conn.commit()
        self._reload_reports()
        self.preview.clear()
        self.on_change()

    def _undo_delete(self) -> None:
        if not self._deleted_reports:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        report = self._deleted_reports.pop()
        repository.add_ai_report(self.conn, report)
        self.conn.commit()
        self._reload_reports()
        self.on_change()

    def undo(self) -> None:
        self._undo_delete()

    def refresh(self) -> None:
        self._reload_reports()


def _default_year() -> int:
    return datetime.now().year
