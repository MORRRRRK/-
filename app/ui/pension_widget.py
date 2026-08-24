from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import repository
from ..edition import is_customer
from ..services import pension as pension_service
from .widgets import (
    NoWheelSpinBox,
    Section,
    confirm_delete,
    flash_saved,
    make_button,
    make_formula_button,
    make_money_spin,
    make_percent_spin,
    money,
)

PENSION_FORMULA_TEXT = (
    "缴费指数 = 月缴费基数 ÷ 2024 年计发基数\n"
    "基础养老金 = 计发基数×(1+平均缴费指数)÷2×缴费年限×1%\n"
    "个人账户养老金 = 个人账户储存额 ÷ 计发月数\n"
    "个人账户储存额 = 月缴费基数×个人比例×12×缴费年限（未计利息）\n"
    "月退休金 = 基础养老金 + 个人账户养老金；多段工作分别计算，以最新一份为准"
)


class PensionWidget(QWidget):
    """退休金测算：按多段工作经历分别估算，以最新一份工作为准。"""

    def __init__(self, conn, on_change=None):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._pension_rows: list[dict] = []
        self._pension_ids: list[int | None] = []
        self._deleted_pension_jobs: list[dict] = []
        self._build()
        self._reload_pension()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        actions = []
        if not is_customer():
            actions.append(
                make_formula_button(
                    self, "退休金计算公式", PENSION_FORMULA_TEXT
                )
            )
        section = Section(
            "退休金测算（按工作经历分别估算，最新一份工作为准）",
            actions=actions,
        )
        pension_form = QGridLayout()
        pension_form.setHorizontalSpacing(12)
        pension_form.setVerticalSpacing(8)

        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["女性", "男性"])
        self.gender_combo.currentTextChanged.connect(self._gender_changed)
        self.retire_age_spin = NoWheelSpinBox()
        self.retire_age_spin.setDecimals(0)
        self.retire_age_spin.setRange(40, 75)
        self.retire_age_spin.setValue(55.0)
        self.retire_age_spin.setAlignment(Qt.AlignRight)
        self.pension_rate_spin = make_percent_spin(
            self._salary_pension_rate()
        )
        pension_form.addWidget(QLabel("性别"), 0, 0)
        pension_form.addWidget(self.gender_combo, 0, 1)
        pension_form.addWidget(QLabel("退休年龄"), 0, 2)
        pension_form.addWidget(self.retire_age_spin, 0, 3)
        pension_form.addWidget(QLabel("个人养老缴费比例"), 0, 4)
        pension_form.addWidget(self.pension_rate_spin, 0, 5)
        pension_form.setColumnStretch(6, 1)

        pension_note = QLabel(
            "缴费指数按“月缴费基数 ÷ 2024 年计发基数”估算；"
            "个人账户储存额按缴费基数 × 个人比例 × 12 × 年限估算，未计利息。"
        )
        pension_note.setObjectName("fieldLabel")
        pension_note.setWordWrap(True)
        pension_form.addWidget(pension_note, 1, 0, 1, 7)

        pension_buttons = QHBoxLayout()
        self.job_add_button = make_button("新增工作记录")
        self.job_fill_button = make_button("从工资参数填充基数")
        self.job_delete_button = make_button("删除选中")
        self.job_undo_button = make_button("撤销删除")
        self.job_save_button = make_button("保存工作记录", primary=True)
        self.pension_calc_button = make_button("测算退休金")
        self.job_add_button.clicked.connect(self._add_pension_job)
        self.job_fill_button.clicked.connect(self._fill_pension_bases)
        self.job_delete_button.clicked.connect(self._delete_pension_job)
        self.job_undo_button.clicked.connect(self._undo_pension_delete)
        self.job_save_button.clicked.connect(self._save_pension_jobs)
        self.pension_calc_button.clicked.connect(self._calculate_pension)
        for button in (
            self.job_add_button,
            self.job_fill_button,
            self.job_delete_button,
            self.job_undo_button,
            self.job_save_button,
            self.pension_calc_button,
        ):
            pension_buttons.addWidget(button)
        pension_buttons.addStretch(1)
        section.add_layout(pension_form)
        section.add_layout(pension_buttons)

        self.pension_table = QTableWidget(0, 6)
        self.pension_table.setHorizontalHeaderLabels(
            ["工作名称", "省份", "开始年份", "结束年份", "月缴费基数", "备注"]
        )
        self.pension_table.verticalHeader().setVisible(False)
        self.pension_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        section.add(self.pension_table)
        layout.addWidget(section)

        pension_result = Section(
            "测算结果（仅供参考，实际以社保经办机构核定为准）"
        )
        self.pension_main_result = QLabel("-")
        self.pension_main_result.setObjectName("summaryValue")
        self.pension_main_result.setWordWrap(True)
        self.pension_detail_result = QLabel("")
        self.pension_detail_result.setObjectName("fieldLabel")
        self.pension_detail_result.setWordWrap(True)
        self.pension_detail_result.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        pension_result.add(self.pension_main_result)
        pension_result.add(self.pension_detail_result)
        layout.addWidget(pension_result)

    def refresh(self) -> None:
        self._reload_pension()

    def _salary_pension_base(self) -> float:
        years = repository.list_years(self.conn)
        if not years:
            return 0.0
        year_id = years[-1]["id"]
        for item in repository.list_insurance_items(self.conn, year_id):
            if item["name"] == "养老" and float(item.get("base") or 0) > 0:
                return float(item["base"])
        params = repository.get_insurance_params(self.conn, year_id) or {}
        return float(params.get("monthly_salary") or 0.0)

    def _salary_pension_rate(self) -> float:
        years = repository.list_years(self.conn)
        if not years:
            return 0.08
        year_id = years[-1]["id"]
        for item in repository.list_insurance_items(self.conn, year_id):
            if item["name"] == "养老":
                return float(item.get("personal_rate") or 0.08)
        params = repository.get_insurance_params(self.conn, year_id) or {}
        return float(params.get("pension_personal_rate") or 0.08)

    @staticmethod
    def _year_spin(value: float) -> NoWheelSpinBox:
        spin = NoWheelSpinBox()
        spin.setDecimals(0)
        spin.setRange(1970, 2100)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignRight)
        return spin

    def _append_pension_row(self, job: dict | None = None) -> None:
        row = self.pension_table.rowCount()
        self.pension_table.insertRow(row)
        self._pension_rows.append(dict(job) if job else {})
        self._pension_ids.append(job.get("id") if job else None)

        name_item = QTableWidgetItem(job["name"] if job else "")
        name_item.setTextAlignment(Qt.AlignCenter)
        self.pension_table.setItem(row, 0, name_item)

        province_combo = QComboBox()
        province_combo.setEditable(True)
        province_combo.addItems(sorted(pension_service.PROVINCE_BASES_2024))
        province_combo.setCurrentText(job["province"] if job else "")
        self.pension_table.setCellWidget(row, 1, province_combo)

        start_spin = self._year_spin(float(job["start_year"] or 2010) if job else 2010.0)
        self.pension_table.setCellWidget(row, 2, start_spin)
        end_spin = self._year_spin(float(job["end_year"] or 2024) if job else 2024.0)
        self.pension_table.setCellWidget(row, 3, end_spin)

        base_spin = make_money_spin(float(job["monthly_base"] or 0.0) if job else 0.0)
        base_spin.setRange(0.0, 1e8)
        self.pension_table.setCellWidget(row, 4, base_spin)

        note_item = QTableWidgetItem(job["note"] if job else "")
        note_item.setTextAlignment(Qt.AlignCenter)
        self.pension_table.setItem(row, 5, note_item)

    def _reload_pension(self) -> None:
        jobs = repository.list_pension_jobs(self.conn)
        self._pension_rows = []
        self._pension_ids = []
        self.pension_table.setRowCount(0)
        for job in jobs:
            self._append_pension_row(job)
        if jobs:
            self._calculate_pension()

    def _pension_row_values(self, row: int) -> dict:
        province = self.pension_table.cellWidget(row, 1).currentText().strip()
        return {
            "name": self.pension_table.item(row, 0).text().strip(),
            "province": province,
            "start_year": int(self.pension_table.cellWidget(row, 2).value()),
            "end_year": int(self.pension_table.cellWidget(row, 3).value()),
            "monthly_base": float(self.pension_table.cellWidget(row, 4).value()),
            "note": self.pension_table.item(row, 5).text().strip(),
        }

    def _add_pension_job(self) -> None:
        self._append_pension_row()
        self.pension_table.setCurrentCell(self.pension_table.rowCount() - 1, 0)

    def _fill_pension_bases(self) -> None:
        base = self._salary_pension_base()
        rate = self._salary_pension_rate()
        self.pension_rate_spin.setValue(rate * 100.0)
        for row in range(self.pension_table.rowCount()):
            self.pension_table.cellWidget(row, 4).setValue(base)
        if base > 0:
            self.pension_main_result.setText(
                f"已将月缴费基数填充为工资参数中的 {money(base)} 元"
            )
        else:
            self.pension_main_result.setText("工资参数中暂无可用的养老缴费基数")

    def _delete_pension_job(self) -> None:
        row = self.pension_table.currentRow()
        if row < 0 or row >= len(self._pension_ids):
            QMessageBox.information(self, "提示", "请先选择要删除的工作记录")
            return
        values = self._pension_row_values(row)
        name = values["name"] or f"第{row + 1}份工作"
        if not confirm_delete(self, "删除工作记录", f"确定删除“{name}”？"):
            return
        job_id = self._pension_ids[row]
        if job_id is not None:
            job = self._pension_rows[row]
            repository.delete_pension_job(self.conn, job_id)
            self._deleted_pension_jobs.append(dict(job))
            self.conn.commit()
        self._pension_rows.pop(row)
        self._pension_ids.pop(row)
        self.pension_table.removeRow(row)
        self._calculate_pension()
        if self.on_change:
            self.on_change()

    def _undo_pension_delete(self) -> None:
        if not self._deleted_pension_jobs:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        job = self._deleted_pension_jobs.pop()
        repository.add_pension_job(self.conn, job)
        self.conn.commit()
        self._reload_pension()
        if self.on_change:
            self.on_change()

    def _save_pension_jobs(self) -> None:
        for row in range(self.pension_table.rowCount()):
            values = self._pension_row_values(row)
            if not values["name"]:
                QMessageBox.warning(self, "提示", "工作名称不能为空")
                return
            if not values["province"]:
                QMessageBox.warning(self, "提示", "请为每份工作选择省份")
                return
            if values["end_year"] < values["start_year"]:
                QMessageBox.warning(self, "提示", "结束年份不能早于开始年份")
                return
            if self._pension_ids[row] is None:
                self._pension_ids[row] = repository.add_pension_job(
                    self.conn, values
                )
            else:
                repository.update_pension_job(
                    self.conn, self._pension_ids[row], values
                )
        self.conn.commit()
        flash_saved(self.job_save_button)
        self._reload_pension()
        if self.on_change:
            self.on_change()

    def _calculate_pension(self) -> None:
        if self.pension_table.rowCount() == 0:
            self.pension_main_result.setText("请先新增工作记录")
            self.pension_detail_result.setText("")
            return
        jobs = [
            self._pension_row_values(row)
            for row in range(self.pension_table.rowCount())
            if self._pension_row_values(row)["name"]
        ]
        if not jobs:
            self.pension_main_result.setText("请先填写工作名称")
            self.pension_detail_result.setText("")
            return
        retire_age = float(self.retire_age_spin.value())
        personal_rate = float(self.pension_rate_spin.value()) / 100.0
        results = [
            pension_service.calculate_pension(job, retire_age, personal_rate)
            for job in jobs
        ]
        latest = max(results, key=lambda r: r["job"]["end_year"])
        total_years = sum(r["contribution_years"] for r in results)
        main_warning = (
            "累计缴费不足 15 年，通常不能按月领取职工养老金"
            if total_years < 15
            else ""
        )
        self.pension_main_result.setText(
            f"最新工作“{latest['job']['name']}”：约 {money(latest['total'])} 元/月"
            + (f"（{main_warning}）" if main_warning else "")
        )
        lines = []
        for index, result in enumerate(results, start=1):
            job = result["job"]
            lines.append(
                f"【工作{index}】{job['name']} · {job['province']} "
                f"{job['start_year']}—{job['end_year']}（{result['contribution_years']} 年）"
            )
            job_warning = result["warning"]
            if "不足 15 年" in job_warning and total_years >= 15:
                job_warning = ""
            if job_warning:
                lines.append(f"提示：{job_warning}")
            lines.append(
                f"基础养老金 {money(result['basic_pension'])} 元 + "
                f"个人账户养老金 {money(result['personal_pension'])} 元 "
                f"= 约 {money(result['total'])} 元/月"
            )
        self.pension_detail_result.setText("\n".join(lines))

    def _gender_changed(self, text: str) -> None:
        self.retire_age_spin.setValue(60.0 if text == "男性" else 55.0)
