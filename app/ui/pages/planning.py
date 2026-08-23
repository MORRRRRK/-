from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...services import pension as pension_service
from ...services import planning as planning_service
from ..widgets import (
    NoWheelSpinBox,
    Section,
    confirm_delete,
    flash_saved,
    line_edit,
    make_button,
    make_money_spin,
    make_percent_spin,
    money,
)


class PlanningPage(QScrollArea):
    def __init__(self, conn, on_change):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._goal_ids: list[int] = []
        self._editing_goal: int | None = None
        self._deleted_goals: list[dict] = []
        self._pension_rows: list[dict] = []
        self._pension_ids: list[int | None] = []
        self._deleted_pension_jobs: list[dict] = []
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        projection_section = Section("净资产增长模拟（仅供参考）")
        proj_grid = QGridLayout()
        self.current_spin = make_money_spin(100000.0)
        self.monthly_invest_spin = make_money_spin(5000.0)
        self.proj_rate_spin = make_percent_spin(0.03)
        self.years_spin = make_money_spin(5.0, 0.0, 60.0)
        self.years_spin.setDecimals(1)
        self.proj_button = make_button("计算净资产增长")
        self.proj_button.clicked.connect(self._calc_projection)
        self.proj_result = QLabel("-")
        self.proj_result.setObjectName("summaryValue")
        widgets = [
            ("当前资产", self.current_spin),
            ("每月投入", self.monthly_invest_spin),
            ("年化收益率", self.proj_rate_spin),
            ("年数", self.years_spin),
        ]
        for col, (title, widget) in enumerate(widgets):
            proj_grid.addWidget(QLabel(title), 0, col * 2)
            proj_grid.addWidget(widget, 0, col * 2 + 1)
        proj_grid.addWidget(self.proj_button, 0, 8)
        proj_grid.addWidget(self.proj_result, 1, 0, 1, 10)
        projection_section.add_layout(proj_grid)
        layout.addWidget(projection_section)

        saving_section = Section("目标倒推每月存款")
        save_grid = QGridLayout()
        self.goal_amount_spin = make_money_spin(200000.0)
        self.goal_rate_spin = make_percent_spin(0.02)
        self.goal_date_edit = QDateEdit(QDate.currentDate())
        self.goal_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.calc_saving_button = make_button("计算每月需存")
        self.calc_saving_button.clicked.connect(self._calc_saving)
        self.saving_result = QLabel("-")
        self.saving_result.setObjectName("summaryValue")
        save_grid.addWidget(QLabel("目标金额"), 0, 0)
        save_grid.addWidget(self.goal_amount_spin, 0, 1)
        save_grid.addWidget(QLabel("目标日期"), 0, 2)
        save_grid.addWidget(self.goal_date_edit, 0, 3)
        save_grid.addWidget(QLabel("年化收益率"), 0, 4)
        save_grid.addWidget(self.goal_rate_spin, 0, 5)
        save_grid.addWidget(self.calc_saving_button, 0, 6)
        save_grid.addWidget(self.saving_result, 1, 0, 1, 8)
        saving_section.add_layout(save_grid)
        layout.addWidget(saving_section)

        goals_section = Section("储蓄目标管理")
        goal_form = QGridLayout()
        self.goal_name_edit = line_edit(placeholder="目标名称")
        self.goal_target_spin = make_money_spin()
        self.goal_current_spin = make_money_spin()
        self.goal_note_edit = line_edit(placeholder="备注")
        goal_form.addWidget(QLabel("名称"), 0, 0)
        goal_form.addWidget(self.goal_name_edit, 0, 1)
        goal_form.addWidget(QLabel("目标金额"), 0, 2)
        goal_form.addWidget(self.goal_target_spin, 0, 3)
        goal_form.addWidget(QLabel("已存金额"), 0, 4)
        goal_form.addWidget(self.goal_current_spin, 0, 5)
        goal_form.addWidget(QLabel("备注"), 0, 6)
        goal_form.addWidget(self.goal_note_edit, 0, 7)
        buttons = QHBoxLayout()
        self.goal_add_button = make_button("新增目标", primary=True)
        self.goal_update_button = make_button("保存修改")
        self.goal_delete_button = make_button("删除")
        self.goal_undo_button = make_button("撤销删除")
        self.goal_add_button.clicked.connect(self._add_goal)
        self.goal_update_button.clicked.connect(self._update_goal)
        self.goal_delete_button.clicked.connect(self._delete_goal)
        self.goal_undo_button.clicked.connect(self._undo_goal)
        buttons.addWidget(self.goal_add_button)
        buttons.addWidget(self.goal_update_button)
        buttons.addWidget(self.goal_delete_button)
        buttons.addWidget(self.goal_undo_button)
        buttons.addStretch(1)
        goals_section.add_layout(goal_form)
        goals_section.add_layout(buttons)
        self.goals_table = QTableWidget(0, 6)
        self.goals_table.setHorizontalHeaderLabels(
            ["名称", "目标金额", "目标日期", "已存金额", "每月需存", "备注"]
        )
        self.goals_table.verticalHeader().setVisible(False)
        self.goals_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.goals_table.itemSelectionChanged.connect(self._load_selected_goal)
        goals_section.add(self.goals_table)
        layout.addWidget(goals_section, 1)

        pension_section = Section("退休金测算（按工作经历分别估算，最新一份工作为准）")
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

        self.pension_note = QLabel(
            "缴费指数按“月缴费基数 ÷ 2024 年计发基数”估算；"
            "个人账户储存额按缴费基数 × 个人比例 × 12 × 年限估算，未计利息。"
        )
        self.pension_note.setObjectName("fieldLabel")
        self.pension_note.setWordWrap(True)
        pension_form.addWidget(self.pension_note, 1, 0, 1, 7)

        pension_buttons = QHBoxLayout()
        self.job_add_button = make_button("新增工作记录")
        self.job_fill_button = make_button("从工资参数填充基数")
        self.job_delete_button = make_button("删除选中")
        self.job_undo_button = make_button("撤销删除")
        self.job_save_button = make_button("保存工作记录")
        self.pension_calc_button = make_button("测算退休金", primary=True)
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
        pension_section.add_layout(pension_form)
        pension_section.add_layout(pension_buttons)

        self.pension_table = QTableWidget(0, 6)
        self.pension_table.setHorizontalHeaderLabels(
            ["工作名称", "省份", "开始年份", "结束年份", "月缴费基数", "备注"]
        )
        self.pension_table.verticalHeader().setVisible(False)
        self.pension_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        pension_section.add(self.pension_table)
        layout.addWidget(pension_section, 1)

        pension_result = Section("测算结果（仅供参考，实际以社保经办机构核定为准）")
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

        self.refresh()

    def _calc_projection(self) -> None:
        result = planning_service.project_net_worth(
            float(self.current_spin.value()),
            float(self.monthly_invest_spin.value()),
            float(self.proj_rate_spin.value()) / 100.0,
            float(self.years_spin.value()),
        )
        self.proj_result.setText(
            f"约 {money(result)} 元（含复利，年化 {self.proj_rate_spin.value():.2f}%）"
        )

    def _calc_saving(self) -> None:
        months = self._months_to_target()
        required = planning_service.required_monthly_saving(
            float(self.goal_amount_spin.value()),
            0.0,
            months,
            float(self.goal_rate_spin.value()) / 100.0,
        )
        self.saving_result.setText(
            f"每月需存约 {money(required)} 元（{months:.0f} 个月）"
        )

    def _months_to_target(self) -> float:
        target = self.goal_date_edit.date().toPython()
        today = date.today()
        return max(0.0, (target - today).days / 30.4375)

    def _goal_values(self) -> dict:
        return {
            "name": self.goal_name_edit.text().strip(),
            "target_amount": float(self.goal_target_spin.value()),
            "target_date": self.goal_date_edit.date().toString("yyyy-MM-dd"),
            "current_amount": float(self.goal_current_spin.value()),
            "monthly_saving": planning_service.required_monthly_saving(
                float(self.goal_target_spin.value()),
                float(self.goal_current_spin.value()),
                self._months_to_target(),
                float(self.goal_rate_spin.value()) / 100.0,
            ),
            "note": self.goal_note_edit.text().strip(),
        }

    def _add_goal(self) -> None:
        values = self._goal_values()
        if not values["name"]:
            QMessageBox.warning(self, "提示", "请填写目标名称")
            return
        repository.add_goal(self.conn, values)
        self.conn.commit()
        self._clear_goal_form()
        self.refresh()
        flash_saved(self.goal_add_button)
        self.on_change()

    def _update_goal(self) -> None:
        if self._editing_goal is None:
            QMessageBox.information(self, "提示", "请先在表格中选择一个目标")
            return
        repository.update_goal(self.conn, self._editing_goal, self._goal_values())
        self.conn.commit()
        self._clear_goal_form()
        self.refresh()
        flash_saved(self.goal_update_button)
        self.on_change()

    def _delete_goal(self) -> None:
        if self._editing_goal is None:
            return
        goal = None
        for item in repository.list_goals(self.conn):
            if item["id"] == self._editing_goal:
                goal = item
                break
        if goal is None or not confirm_delete(self, "删除目标", f"确定删除目标“{goal['name']}”？"):
            return
        repository.delete_goal(self.conn, self._editing_goal)
        self._deleted_goals.append(goal)
        self.conn.commit()
        self._clear_goal_form()
        self.refresh()
        self.on_change()

    def _undo_goal(self) -> None:
        if not self._deleted_goals:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        goal = self._deleted_goals.pop()
        goal_id = repository.add_goal(self.conn, goal)
        self.conn.commit()
        self._editing_goal = goal_id
        self.refresh()
        self.on_change()

    def _clear_goal_form(self) -> None:
        self._editing_goal = None
        self.goal_name_edit.clear()
        self.goal_target_spin.setValue(0.0)
        self.goal_current_spin.setValue(0.0)
        self.goal_note_edit.clear()
        self.goals_table.clearSelection()

    def _load_selected_goal(self) -> None:
        row = self.goals_table.currentRow()
        if row < 0 or row >= len(self._goal_ids):
            return
        goal_id = self._goal_ids[row]
        for goal in repository.list_goals(self.conn):
            if goal["id"] == goal_id:
                self._editing_goal = goal_id
                self.goal_name_edit.setText(goal["name"])
                self.goal_target_spin.setValue(goal["target_amount"])
                self.goal_date_edit.setDate(QDate.fromString(goal["target_date"], "yyyy-MM-dd"))
                self.goal_current_spin.setValue(goal["current_amount"])
                self.goal_note_edit.setText(goal["note"])
                return

    def _reload_goals(self) -> None:
        goals = repository.list_goals(self.conn)
        self._goal_ids = [g["id"] for g in goals]
        self.goals_table.setRowCount(len(goals))
        for r, goal in enumerate(goals):
            values = [
                goal["name"],
                money(goal["target_amount"]),
                goal["target_date"],
                money(goal["current_amount"]),
                money(goal["monthly_saving"]),
                goal["note"],
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(
                    Qt.AlignRight | Qt.AlignVCenter if c in (1, 3, 4) else Qt.AlignLeft | Qt.AlignVCenter
                )
                self.goals_table.setItem(r, c, item)
        self.goals_table.resizeColumnsToContents()

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
        self.on_change()

    def _undo_pension_delete(self) -> None:
        if not self._deleted_pension_jobs:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        job = self._deleted_pension_jobs.pop()
        job_id = repository.add_pension_job(self.conn, job)
        self.conn.commit()
        self._reload_pension()
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

    def refresh(self) -> None:
        self._reload_goals()
        self._reload_pension()
        self._calc_projection()
        self._calc_saving()
