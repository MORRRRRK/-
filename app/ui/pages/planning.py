from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
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
from ...edition import is_customer
from ...services import planning as planning_service
from ..widgets import (
    Section,
    confirm_delete,
    flash_saved,
    line_edit,
    make_button,
    make_formula_button,
    make_money_spin,
    make_percent_spin,
    make_save_button,
    money,
)

PROJECTION_FORMULA_TEXT = (
    "终值 = 当前资产×(1+年化收益率)^年数 "
    "+ 每月投入×(((1+月收益率)^(年数×12)-1)/月收益率)"
)

SAVING_FORMULA_TEXT = (
    "目标月数 = (目标日期 - 今天) ÷ 30.4375\n"
    "每月需存 = (目标金额 - 已存金额×复利) 折算到目标月数的等额月供"
)

GOAL_FORMULA_TEXT = (
    "目标表格中“每月需存”与“目标倒推每月存款”公式一致：\n"
    "按目标金额、已存金额、目标月数和年化收益率计算等额月存"
)


class PlanningPage(QScrollArea):
    def __init__(self, conn, on_change):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._goal_ids: list[int] = []
        self._editing_goal: int | None = None
        self._deleted_goals: list[dict] = []
        self._formula_enabled = not is_customer()
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        projection_actions = []
        if self._formula_enabled:
            projection_actions.append(
                make_formula_button(
                    self, "净资产增长公式", PROJECTION_FORMULA_TEXT
                )
            )
        projection_section = Section(
            "净资产增长模拟",
            actions=projection_actions,
            info="模拟结果仅供参考，不构成收益承诺",
        )
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

        saving_actions = []
        if self._formula_enabled:
            saving_actions.append(
                make_formula_button(
                    self, "每月存款公式", SAVING_FORMULA_TEXT
                )
            )
        saving_section = Section("目标倒推每月存款", actions=saving_actions)
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

        goal_actions = []
        if self._formula_enabled:
            goal_actions.append(
                make_formula_button(
                    self, "储蓄目标公式", GOAL_FORMULA_TEXT
                )
            )
        goals_section = Section("储蓄目标管理", actions=goal_actions)
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
        self.goal_update_button = make_save_button("保存修改")
        self.goal_delete_button = make_button("删除")
        self.goal_undo_button = make_button("撤销删除")
        self.goal_add_button.clicked.connect(self._add_goal)
        self.goal_update_button.clicked.connect(self._update_goal)
        self.goal_delete_button.clicked.connect(self._delete_goal)
        self.goal_undo_button.clicked.connect(self._undo_goal)
        save_buttons = QHBoxLayout()
        save_buttons.addStretch(1)
        save_buttons.addWidget(self.goal_update_button)
        goals_section.add_layout(save_buttons)
        buttons.addWidget(self.goal_add_button)
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

    def refresh(self) -> None:
        self._reload_goals()
        self._calc_projection()
        self._calc_saving()

    def save(self) -> None:
        """全局保存：正在编辑时保存修改，否则新增目标。"""
        if self._editing_goal is not None:
            self._update_goal()
        else:
            self._add_goal()

    def undo(self) -> None:
        self._undo_goal()
