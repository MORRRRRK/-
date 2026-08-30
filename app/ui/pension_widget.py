from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
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
    make_save_button,
    money,
)

PENSION_FORMULA_TEXT = (
    "平均缴费指数 = 月缴费基数 ÷ 2024 年计发基数（上限 3）\n"
    "基础养老金 = 计发基数×(1+平均缴费指数)÷2×缴费年限×1%\n"
    "个人账户养老金 = 个人账户储存额 ÷ 计发月数\n"
    "个人账户储存额 = 月缴费基数×个人养老缴费比例×12×缴费年限（未计利息）\n"
    "个人养老金月领 ≈ 账户余额 ÷ 计发月数，账户余额按年缴存并模拟年化复利\n"
    "月退休金合计 = 最新工作基本养老金 + 个人养老金月领"
)


class PensionWidget(QWidget):
    """退休金测算：多段工作经历 + 可选个人养老金，全部数据手填。"""

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
            "退休金测算",
            actions=actions,
            info="按工作经历分别估算，以最新一份工作的测算为准",
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
        pension_form.addWidget(QLabel("性别"), 0, 0)
        pension_form.addWidget(self.gender_combo, 0, 1)
        pension_form.addWidget(QLabel("退休年龄"), 0, 2)
        pension_form.addWidget(self.retire_age_spin, 0, 3)
        pension_form.setColumnStretch(4, 1)

        pension_note = QLabel(
            "工作记录中的个人/企业养老缴费比例用于估算个人账户储存额，"
            "所有数据均需手动填写。"
        )
        pension_note.setObjectName("fieldLabel")
        pension_note.setWordWrap(True)
        pension_form.addWidget(pension_note, 1, 0, 1, 5)

        job_save_row = QHBoxLayout()
        self.job_save_button = make_save_button("保存工作记录")
        self.job_save_button.clicked.connect(self._save_pension_jobs)
        job_save_row.addStretch(1)
        job_save_row.addWidget(self.job_save_button)
        section.add_layout(job_save_row)

        pension_buttons = QHBoxLayout()
        self.job_add_button = make_button("新增工作记录")
        self.job_delete_button = make_button("删除选中")
        self.job_undo_button = make_button("撤销删除")
        self.pension_calc_button = make_button("测算退休金")
        self.job_add_button.clicked.connect(self._add_pension_job)
        self.job_delete_button.clicked.connect(self._delete_pension_job)
        self.job_undo_button.clicked.connect(self._undo_pension_delete)
        self.pension_calc_button.clicked.connect(self._calculate_pension)
        for button in (
            self.job_add_button,
            self.job_delete_button,
            self.job_undo_button,
            self.pension_calc_button,
        ):
            pension_buttons.addWidget(button)
        pension_buttons.addStretch(1)
        section.add_layout(pension_form)
        section.add_layout(pension_buttons)

        self.pension_table = QTableWidget(0, 8)
        self.pension_table._enter_save = True
        self.pension_table.setHorizontalHeaderLabels(
            [
                "工作名称", "省份", "开始年份", "结束年份",
                "月缴费基数", "个人养老缴费比例(%)", "企业养老缴费比例(%)", "备注",
            ]
        )
        self.pension_table.verticalHeader().setVisible(False)
        self.pension_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.pension_table.setMinimumHeight(6 * 34 + 34)
        section.add(self.pension_table)
        layout.addWidget(section)

        self._build_personal_pension(layout)

        pension_result = Section(
            "测算结果",
            info="测算仅供参考，实际以社保经办机构核定为准",
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

    def _build_personal_pension(self, layout) -> None:
        self.pp_save_button = make_save_button("保存个人养老金")
        self.pp_save_button.clicked.connect(self._save_pension_settings)
        section = Section(
            "个人养老金",
            save_actions=[self.pp_save_button],
            info="每年缴存上限 12000 元，按计发月数估算退休后每月领取",
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        self.pp_enabled_check = QCheckBox("是否缴纳个人养老金")
        self.pp_enabled_check.toggled.connect(
            lambda _: self._calculate_pension()
        )
        self.pp_annual_spin = make_money_spin(12000.0, 0.0, 1e7)
        self.pp_return_spin = make_percent_spin(0.03)
        self.pp_start_spin = self._year_spin(2024.0)
        self.pp_end_spin = self._year_spin(2033.0)
        grid.addWidget(self.pp_enabled_check, 0, 0, 1, 2)
        grid.addWidget(QLabel("每年缴存金额"), 1, 0)
        grid.addWidget(self.pp_annual_spin, 1, 1)
        grid.addWidget(QLabel("预计年化收益率"), 1, 2)
        grid.addWidget(self.pp_return_spin, 1, 3)
        grid.addWidget(QLabel("开始缴存年份"), 2, 0)
        grid.addWidget(self.pp_start_spin, 2, 1)
        grid.addWidget(QLabel("结束缴存年份"), 2, 2)
        grid.addWidget(self.pp_end_spin, 2, 3)
        grid.setColumnStretch(4, 1)
        section.add_layout(grid)
        layout.addWidget(section)

    def refresh(self) -> None:
        self._reload_pension()

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

        start_spin = self._year_spin(
            float(job["start_year"] or 2010) if job else 2010.0
        )
        self.pension_table.setCellWidget(row, 2, start_spin)
        end_spin = self._year_spin(
            float(job["end_year"] or 2024) if job else 2024.0
        )
        self.pension_table.setCellWidget(row, 3, end_spin)

        base_spin = make_money_spin(
            float(job["monthly_base"] or 0.0) if job else 0.0
        )
        base_spin.setRange(0.0, 1e8)
        self.pension_table.setCellWidget(row, 4, base_spin)

        personal_rate = make_percent_spin(
            float(job.get("personal_rate") or 0.08) if job else 0.08
        )
        self.pension_table.setCellWidget(row, 5, personal_rate)
        company_rate = make_percent_spin(
            float(job.get("company_rate") or 0.16) if job else 0.16
        )
        self.pension_table.setCellWidget(row, 6, company_rate)

        note_item = QTableWidgetItem(job["note"] if job else "")
        note_item.setTextAlignment(Qt.AlignCenter)
        self.pension_table.setItem(row, 7, note_item)

    def _reload_pension(self) -> None:
        jobs = repository.list_pension_jobs(self.conn)
        self._pension_rows = []
        self._pension_ids = []
        self.pension_table.setRowCount(0)
        for job in jobs:
            self._append_pension_row(job)
        self._load_pension_settings()
        self._calculate_pension()

    def _pension_row_values(self, row: int) -> dict:
        province = self.pension_table.cellWidget(row, 1).currentText().strip()
        return {
            "name": self.pension_table.item(row, 0).text().strip(),
            "province": province,
            "start_year": int(self.pension_table.cellWidget(row, 2).value()),
            "end_year": int(self.pension_table.cellWidget(row, 3).value()),
            "monthly_base": float(
                self.pension_table.cellWidget(row, 4).value()
            ),
            "personal_rate": float(
                self.pension_table.cellWidget(row, 5).value()
            )
            / 100.0,
            "company_rate": float(
                self.pension_table.cellWidget(row, 6).value()
            )
            / 100.0,
            "note": self.pension_table.item(row, 7).text().strip(),
        }

    def _add_pension_job(self) -> None:
        self._append_pension_row()
        self.pension_table.setCurrentCell(self.pension_table.rowCount() - 1, 0)

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

    def _load_pension_settings(self) -> None:
        def get(key: str, default: str) -> str:
            return repository.get_setting(self.conn, key, default)

        self.pp_enabled_check.setChecked(
            get("pension_enabled", "0") == "1"
        )
        self.pp_annual_spin.setValue(float(get("pension_annual", "12000")))
        self.pp_return_spin.setValue(float(get("pension_return_rate", "0.03")))
        self.pp_start_spin.setValue(float(get("pension_start_year", "2024")))
        self.pp_end_spin.setValue(float(get("pension_end_year", "2033")))

    def _save_pension_settings(self) -> None:
        repository.set_setting(
            self.conn,
            "pension_enabled",
            "1" if self.pp_enabled_check.isChecked() else "0",
        )
        repository.set_setting(
            self.conn, "pension_annual", str(self.pp_annual_spin.value())
        )
        repository.set_setting(
            self.conn, "pension_return_rate", str(self.pp_return_spin.value())
        )
        repository.set_setting(
            self.conn, "pension_start_year", str(self.pp_start_spin.value())
        )
        repository.set_setting(
            self.conn, "pension_end_year", str(self.pp_end_spin.value())
        )
        self.conn.commit()
        flash_saved(self.pp_save_button)
        self._calculate_pension()

    def save(self) -> None:
        self._save_pension_jobs()
        self._save_pension_settings()

    def undo(self) -> None:
        self._undo_pension_delete()

    def _calculate_pension(self) -> None:
        jobs = [
            self._pension_row_values(row)
            for row in range(self.pension_table.rowCount())
            if self._pension_row_values(row)["name"]
        ]
        retire_age = float(self.retire_age_spin.value())
        results = [
            pension_service.calculate_pension(job, retire_age)
            for job in jobs
        ]
        pp = pension_service.calculate_personal_pension(
            self.pp_enabled_check.isChecked(),
            float(self.pp_annual_spin.value()),
            float(self.pp_return_spin.value()) / 100.0,
            int(self.pp_start_spin.value()),
            int(self.pp_end_spin.value()),
            retire_age,
        )

        if not jobs and not pp["enabled"]:
            self.pension_main_result.setText("请先新增工作记录或填写个人养老金")
            self.pension_detail_result.setText("")
            return

        total_years = sum(r["contribution_years"] for r in results)
        main_warning = (
            "累计缴费不足 15 年，通常不能按月领取职工养老金"
            if 0 < total_years < 15
            else ""
        )
        lines = []
        latest_basic = 0.0
        if results:
            latest = max(results, key=lambda r: r["job"]["end_year"])
            latest_basic = latest["total"]
            lines.append(
                f"最新工作“{latest['job']['name']}”：约 "
                f"{money(latest['total'])} 元/月"
            )
            for index, result in enumerate(results, start=1):
                job = result["job"]
                lines.append(
                    f"【工作{index}】{job['name']} · {job['province']} "
                    f"{job['start_year']}—{job['end_year']}"
                    f"（{result['contribution_years']} 年）"
                )
                job_warning = result["warning"]
                if "不足 15 年" in job_warning and total_years >= 15:
                    job_warning = ""
                if job_warning:
                    lines.append(f"提示：{job_warning}")
                lines.append(
                    f"基础养老金 {money(result['basic_pension'])} 元 + "
                    f"个人账户养老金 {money(result['personal_pension'])} 元"
                    f" = 约 {money(result['total'])} 元/月"
                )

        grand_total = latest_basic + pp["monthly"]
        if pp["enabled"]:
            lines.append(
                f"个人养老金：累计缴存 {money(pp['contributed'])} 元，"
                f"按 {pp['years']} 年、年化 "
                f"{float(self.pp_return_spin.value()):.2f}% 估算账户余额 "
                f"{money(pp['balance'])} 元，按月领取约 "
                f"{money(pp['monthly'])} 元/月（税后约 "
                f"{money(pp['monthly_after_tax'])} 元）"
            )
        if main_warning:
            lines.insert(0, main_warning)
        if pp["warning"] and pp["enabled"]:
            lines.append(pp["warning"])
        self.pension_main_result.setText(
            f"预计月退休金合计：约 {money(grand_total)} 元/月"
        )
        self.pension_detail_result.setText("\n".join(lines))

    def _gender_changed(self, text: str) -> None:
        self.retire_age_spin.setValue(60.0 if text == "男性" else 55.0)
