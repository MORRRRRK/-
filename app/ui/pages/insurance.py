from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...edition import is_customer
from ...services import salary as salary_service
from ...services import tax as tax_service
from ..widgets import (
    NoWheelSpinBox,
    Section,
    confirm_delete,
    flash_saved,
    info_label,
    make_button,
    make_money_spin,
    make_year_combo,
    money,
)


class InsurancePage(QWidget):
    """工资管理：多工资方案标签页，可新增、收起与历史查询。"""

    def __init__(self, conn, on_change=None):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._reloading = False
        self._build()
        self._reload_profiles()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        self.add_profile_button = make_button("新增方案", primary=True)
        self.history_button = make_button("历史查询")
        self.add_profile_button.clicked.connect(self._new_profile)
        self.history_button.clicked.connect(self._show_history)
        toolbar.addWidget(self.add_profile_button)
        toolbar.addWidget(self.history_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)

    def _reload_profiles(self) -> None:
        self._reloading = True
        try:
            self.tabs.blockSignals(True)
            self.tabs.clear()
            profiles = repository.list_open_salary_profiles(self.conn)
            if not profiles:
                repository.ensure_open_salary_profile(self.conn)
                self.conn.commit()
                profiles = repository.list_open_salary_profiles(self.conn)
            for profile in profiles:
                tab = SalaryProfileTab(self.conn, profile, self.on_change)
                self.tabs.addTab(tab, profile["name"])
        finally:
            self.tabs.blockSignals(False)
            self._reloading = False
        if self.tabs.count():
            self.tabs.setCurrentIndex(0)

    def _on_tab_changed(self, _index: int) -> None:
        if self._reloading:
            return
        self._persist_all_tabs()

    def _persist_all_tabs(self) -> None:
        for index in range(self.tabs.count()):
            self._persist_tab(index)

    def _persist_tab(self, index: int) -> None:
        tab = self.tabs.widget(index)
        if not isinstance(tab, SalaryProfileTab):
            return
        payload = tab.current_payload()
        repository.save_salary_profile(
            self.conn,
            tab.profile_id,
            tab.profile_name,
            payload["year"],
            payload,
        )
        self.conn.commit()

    def _close_tab(self, index: int) -> None:
        if self.tabs.count() <= 1:
            QMessageBox.information(self, "提示", "至少保留一个工资方案")
            return
        tab = self.tabs.widget(index)
        if not isinstance(tab, SalaryProfileTab):
            return
        self._persist_tab(index)
        repository.set_salary_profile_open(self.conn, tab.profile_id, 0)
        self.conn.commit()
        self.tabs.removeTab(index)

    def _new_profile(self) -> None:
        count = (
            len(repository.list_salary_profiles(self.conn)) + 1
        )
        name, ok = QInputDialog.getText(
            self, "新增工资方案", "方案名称：", text=f"新方案{count}"
        )
        if not ok or not name.strip():
            return
        self._persist_all_tabs()
        active = self.tabs.currentWidget()
        if isinstance(active, SalaryProfileTab):
            year = active.current_payload()["year"]
            payload = active.current_payload()
        else:
            year = 2026
            payload = salary_service.default_payload(year)
        payload["year"] = year
        profile_id = repository.add_salary_profile(
            self.conn, name.strip(), year, payload
        )
        self.conn.commit()
        profile = repository.get_salary_profile(self.conn, profile_id)
        tab = SalaryProfileTab(self.conn, profile, self.on_change)
        index = self.tabs.addTab(tab, profile["name"])
        self.tabs.setCurrentIndex(index)

    def _show_history(self) -> None:
        dialog = HistoryDialog(self.conn, self)
        dialog.exec()
        if dialog.changed:
            self._reload_profiles()

    def refresh(self) -> None:
        self._reload_profiles()

    def save(self) -> None:
        tab = self.tabs.currentWidget()
        if isinstance(tab, SalaryProfileTab):
            tab.save()

    def undo(self) -> None:
        tab = self.tabs.currentWidget()
        if isinstance(tab, SalaryProfileTab):
            tab.undo()


class HistoryDialog(QDialog):
    """已收起的工资方案：可恢复，可永久删除。"""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.changed = False
        self.setWindowTitle("已收起的工资方案")
        self.setMinimumSize(680, 420)
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "年份", "更新时间", "操作"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        close_button = make_button("关闭")
        close_button.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self._reload()

    def _reload(self) -> None:
        rows = [
            p
            for p in repository.list_salary_profiles(self.conn)
            if not p["is_open"]
        ]
        self.table.setRowCount(len(rows))
        for r, profile in enumerate(rows):
            name_item = QTableWidgetItem(profile["name"])
            name_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, name_item)
            year_item = QTableWidgetItem(str(profile["year"]))
            year_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 1, year_item)
            time_item = QTableWidgetItem(str(profile["updated_at"] or ""))
            time_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 2, time_item)

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)
            restore_button = make_button("恢复")
            restore_button.clicked.connect(
                lambda _=False, pid=profile["id"]: self._restore(pid)
            )
            delete_button = make_button("删除")
            delete_button.clicked.connect(
                lambda _=False, pid=profile["id"]: self._delete(pid)
            )
            actions_layout.addWidget(restore_button)
            actions_layout.addWidget(delete_button)
            actions_layout.addStretch(1)
            self.table.setCellWidget(r, 3, actions)

    def _restore(self, profile_id: int) -> None:
        repository.set_salary_profile_open(self.conn, profile_id, 1)
        self.conn.commit()
        self.changed = True
        self._reload()

    def _delete(self, profile_id: int) -> None:
        profile = repository.get_salary_profile(self.conn, profile_id)
        if not profile or not confirm_delete(
            self, "删除工资方案", f"确定删除“{profile['name']}”？删除后不可恢复。"
        ):
            return
        repository.delete_salary_profile(self.conn, profile_id)
        self.conn.commit()
        self.changed = True
        self._reload()


class SalaryProfileTab(QScrollArea):
    """单个工资方案页面：工资详情、N险N金、专项附加、个税汇总与退休金。"""

    def __init__(self, conn, profile: dict, on_change=None):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self.profile_id = int(profile["id"])
        self.profile_name = str(profile["name"] or "工资方案")
        self.payload = salary_service.decode_payload(profile.get("payload"))
        self._deleted_rows: list[dict] = []
        self._deleted_salary_rows: list[dict] = []
        self._loading = False
        self._formula_enabled = not is_customer()
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(QLabel("年份"))
        years = sorted(
            {
                int(self.payload.get("year") or 2026),
                *[
                    int(y["year"])
                    for y in repository.list_years(self.conn)
                    if int(y["year"]) >= 2000
                ],
            },
            reverse=True,
        )
        self.year_combo = make_year_combo(years) if years else QComboBox()
        self.year_combo.setEditable(True)
        self.year_combo.lineEdit().setValidator(QIntValidator(2000, 2100))
        self.year_combo.setFixedWidth(120)
        self.year_combo.currentTextChanged.connect(
            lambda _: self._refresh_all_calculated()
        )
        top.addWidget(self.year_combo)
        top.addStretch(1)
        layout.addLayout(top)

        self._build_salary_section(layout)
        self._build_insurance_section(layout)
        self._build_deduction_section(layout)
        self._build_result_section(layout)

        note = QLabel(
            "工资详情中的绩效、补贴和奖金均可选择按月/按季/按年发放，"
            "总工资按发放频率折算到年度；个税按累计预扣预缴估算。"
        )
        note.setObjectName("fieldLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

    def _build_salary_section(self, layout) -> None:
        self.performance_button = make_button("新增绩效")
        self.subsidy_button = make_button("新增补贴")
        self.salary_delete_button = make_button("删除选中")
        self.salary_undo_button = make_button("撤销删除")
        self.salary_save_button = make_button("保存工资详情", primary=True)
        self.performance_button.clicked.connect(self._add_performance_row)
        self.subsidy_button.clicked.connect(self._add_subsidy_row)
        self.salary_delete_button.clicked.connect(self._delete_salary_row)
        self.salary_undo_button.clicked.connect(self._undo_salary_row)
        self.salary_save_button.clicked.connect(self._save_salary)
        section = Section(
            "工资详情",
            actions=[
                self.performance_button,
                self.subsidy_button,
                self.salary_delete_button,
                self.salary_undo_button,
                self.salary_save_button,
            ],
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)

        self.base_spin = make_money_spin()
        self.thirteen_coef_spin = self._coefficient_spin(1.0)
        self.thirteen_freq_combo = self._frequency_combo("annual")
        self.bonus_coef_spin = self._coefficient_spin(1.0)
        self.bonus_freq_combo = self._frequency_combo("annual")

        grid.addWidget(info_label("基本工资", "按月发放的基本工资金额"), 0, 0)
        grid.addWidget(self.base_spin, 0, 1)
        grid.addWidget(QLabel("13薪 xN"), 0, 2)
        grid.addWidget(self.thirteen_coef_spin, 0, 3)
        grid.addWidget(QLabel("发放频率"), 0, 4)
        grid.addWidget(self.thirteen_freq_combo, 0, 5)
        grid.addWidget(QLabel("年终奖 xN"), 1, 2)
        grid.addWidget(self.bonus_coef_spin, 1, 3)
        grid.addWidget(QLabel("发放频率"), 1, 4)
        grid.addWidget(self.bonus_freq_combo, 1, 5)
        for spin in (self.base_spin, self.thirteen_coef_spin, self.bonus_coef_spin):
            spin.valueChanged.connect(lambda _: self._refresh_all_calculated())
        self.thirteen_freq_combo.currentIndexChanged.connect(
            lambda _: self._refresh_all_calculated()
        )
        self.bonus_freq_combo.currentIndexChanged.connect(
            lambda _: self._refresh_all_calculated()
        )
        section.add_layout(grid)

        self.salary_table = QTableWidget(0, 4)
        self.salary_table._enter_save = True
        self.salary_table.setHorizontalHeaderLabels(
            ["类型", "名称", "金额", "发放频率"]
        )
        self.salary_table.verticalHeader().setVisible(False)
        self.salary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.salary_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.salary_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.salary_table.itemChanged.connect(
            lambda _: self._refresh_all_calculated()
        )
        section.add(self.salary_table)
        layout.addWidget(section)

    def _build_insurance_section(self, layout) -> None:
        self.add_item_button = make_button("新增险种")
        self.delete_item_button = make_button("删除选中行")
        self.undo_delete_button = make_button("撤销删除")
        self.items_save_button = make_button("保存N险N金", primary=True)
        self.add_item_button.clicked.connect(self._add_item_row)
        self.delete_item_button.clicked.connect(self._delete_item_row)
        self.undo_delete_button.clicked.connect(self._undo_delete_row)
        self.items_save_button.clicked.connect(self._save_insurance)
        section = Section(
            "N险N金",
            info="包含五险一金与其他可自定义险种；可新增、删除、撤销删除",
            actions=[
                self.add_item_button,
                self.delete_item_button,
                self.undo_delete_button,
                self.items_save_button,
            ],
        )
        self.items_table = QTableWidget(0, 5)
        self.items_table._enter_save = True
        self.items_table.setHorizontalHeaderLabels(
            ["名称", "基数", "个人比例(%)", "公司比例(%)", "个人固定金额"]
        )
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.items_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.items_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.items_table.itemChanged.connect(self._on_insurance_changed)
        section.add(self.items_table)
        layout.addWidget(section, 1)

    def _build_deduction_section(self, layout) -> None:
        self.deduction_save_button = make_button("保存专项附加扣除", primary=True)
        self.deduction_save_button.clicked.connect(self._save_deduction)
        section = Section(
            "专项附加扣除",
            info="个税专项附加扣除项目，可按实际情况选择或填写",
            actions=[self.deduction_save_button],
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)

        self.province_combo = QComboBox()
        self.province_combo.addItem("不享受住房租金扣除", "")
        for province in tax_service.PROVINCE_CITIES:
            self.province_combo.addItem(province, province)
        self.city_combo = QComboBox()
        self.district_combo = QComboBox()
        self.province_combo.currentIndexChanged.connect(self._province_changed)
        self.city_combo.currentIndexChanged.connect(self._city_changed)

        self.elderly_combo = QComboBox()
        self.elderly_combo.addItem("不享受", "none")
        self.elderly_combo.addItem("独生子女 3000元/月", "only_child")
        self.elderly_combo.addItem("非独生子女分摊 1500元/月", "shared")

        self.children_spin = self._count_spin(0.0, 10)
        self.infant_spin = self._count_spin(0.0, 10)
        self.continuing_combo = QComboBox()
        self.continuing_combo.addItem("不享受", 0)
        self.continuing_combo.addItem("学历继续教育 400元/月", 1)
        self.mortgage_combo = QComboBox()
        self.mortgage_combo.addItem("不享受", 0)
        self.mortgage_combo.addItem("首套房贷 1000元/月", 1)
        self.severe_combo = QComboBox()
        self.severe_combo.addItem("不享受", 0)
        self.severe_combo.addItem("享受", 1)
        self.severe_spin = make_money_spin(0.0, 0.0, 1e6)
        self.custom_spin = make_money_spin(0.0, 0.0, 1e6)

        for spin in (
            self.children_spin,
            self.infant_spin,
            self.severe_spin,
            self.custom_spin,
        ):
            spin.valueChanged.connect(lambda _: self._refresh_all_calculated())
        for combo in (
            self.elderly_combo,
            self.continuing_combo,
            self.mortgage_combo,
            self.severe_combo,
        ):
            combo.currentIndexChanged.connect(
                lambda _: self._refresh_all_calculated()
            )

        col = 0
        for title, widget in (
            ("省/直辖市", self.province_combo),
            ("市", self.city_combo),
            ("区/县", self.district_combo),
        ):
            grid.addWidget(QLabel(title), 0, col)
            grid.addWidget(widget, 0, col + 1)
            col += 2

        deduction_items = [
            ("赡养老人", self.elderly_combo),
            ("子女教育", self.children_spin),
            ("婴幼儿照护", self.infant_spin),
            ("继续教育", self.continuing_combo),
            ("住房贷款利息", self.mortgage_combo),
            ("大病医疗", self.severe_combo),
            ("大病医疗年度金额", self.severe_spin),
            ("其他扣除", self.custom_spin),
        ]
        deduction_info = {
            "赡养老人": "独生子女 3000元/月；非独生子女分摊 1500元/月",
            "子女教育": "每个子女 2000元/月，按人数填写",
            "婴幼儿照护": "每个婴幼儿 2000元/月，按人数填写",
            "继续教育": "学历继续教育 400元/月",
            "住房贷款利息": "首套房贷 1000元/月",
            "大病医疗": "大病医疗扣除按年度金额填写",
            "大病医疗年度金额": "仅在选择享受大病医疗时生效",
            "其他扣除": "其他可抵扣项目，按每月金额填写",
        }
        for index, (title, widget) in enumerate(deduction_items):
            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.addWidget(
                info_label(title, deduction_info.get(title, title))
            )
            cell.addWidget(widget)
            grid.addLayout(cell, index // 4 + 1, index % 4)
        note = QLabel(
            "租房扣除按省-市-区逐级选择，城市档位自动带入："
            "直辖市/省会/计划单列市 1500元，人口100万以上城市 1100元，其他城市 800元。"
        )
        note.setObjectName("fieldLabel")
        note.setWordWrap(True)
        grid.addWidget(note, 3, 0, 1, 4)
        section.add_layout(grid)
        layout.addWidget(section)

    def _build_result_section(self, layout) -> None:
        section = Section("自动计算结果与全年个税汇总")
        top = QHBoxLayout()
        top.addWidget(QLabel("年终奖计税方式"))
        self.bonus_method_combo = QComboBox()
        self.bonus_method_combo.addItem("单独计税", "separate")
        self.bonus_method_combo.addItem("并入综合所得", "combined")
        self.bonus_method_combo.currentIndexChanged.connect(
            lambda _: self._refresh_all_calculated()
        )
        top.addWidget(self.bonus_method_combo)
        top.addStretch(1)
        section.add_layout(top)

        grid = QGridLayout()
        self.result_labels: dict[str, QLabel] = {}
        rows = [
            ("total_salary", "总工资", "按年合计的总工资"),
            ("personal_total", "个人缴纳合计", "按每月缴纳合计"),
            ("company_total", "公司缴纳合计", "按每月缴纳合计"),
            ("gross_income", "税前总收入", "按年计算的税前总收入"),
            ("total_package", "总包", "按年计算的公司总成本"),
            ("total_income", "全年应税收入", "按实际月度流水汇总"),
            ("taxable_income", "全年应纳税所得额", "扣除起征点与专项附加后的应税所得"),
            ("wage_tax", "工资个税", "按累计预扣预缴估算"),
            ("bonus_tax", "年终奖个税", "按所选计税方式计算"),
            ("total_tax", "全年应缴个税", "工资个税 + 年终奖个税"),
            ("net_income", "全年税后收入", "应税收入 - 五险一金 - 个税"),
            ("monthly_net", "月均税后收入", "全年税后收入 ÷ 12"),
        ]
        for row, (key, title, info) in enumerate(rows):
            self.result_labels[key] = self._add_result_row(
                grid, row, key, title, info
            )
        section.add_layout(grid)

        self.actual_table = QTableWidget(12, 8)
        self.actual_table.setHorizontalHeaderLabels(
            [
                "月份",
                "当月收入",
                "个人五险一金",
                "当月专项附加",
                "累计应税所得",
                "累计已缴",
                "当月个税",
                "税后净收入",
            ]
        )
        self.actual_table.verticalHeader().setVisible(False)
        self.actual_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.actual_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.actual_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.actual_table.setMinimumHeight(12 * 32 + 34)
        for row in range(12):
            for col in range(8):
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignCenter)
                self.actual_table.setItem(row, col, item)
        section.add(self.actual_table)
        layout.addWidget(section)

    @staticmethod
    def _count_spin(value: float, maximum: int = 24) -> NoWheelSpinBox:
        spin = NoWheelSpinBox()
        spin.setDecimals(0)
        spin.setRange(0, maximum)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignRight)
        return spin

    @staticmethod
    def _coefficient_spin(value: float) -> NoWheelSpinBox:
        spin = NoWheelSpinBox()
        spin.setDecimals(2)
        spin.setRange(0.0, 24.0)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignRight)
        return spin

    @staticmethod
    def _frequency_combo(value: str = "annual") -> QComboBox:
        combo = QComboBox()
        combo.addItem("按月发放", "monthly")
        combo.addItem("按季发放", "quarterly")
        combo.addItem("按年发放", "annual")
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))
        return combo

    def _current_year(self) -> int:
        try:
            return int(float(self.year_combo.currentText().strip()))
        except ValueError:
            return int(self.payload.get("year") or 2026)

    def _load(self) -> None:
        params = salary_service.params(self.payload)
        self._loading = True
        try:
            index = self.year_combo.findData(self._current_year())
            if index < 0:
                index = self.year_combo.findText(str(self._current_year()))
            self.year_combo.setCurrentIndex(max(0, index))
            self.base_spin.setValue(float(params.get("monthly_salary") or 0.0))
            self.thirteen_coef_spin.setValue(
                float(params.get("thirteenth_coefficient") or 1.0)
            )
            self._set_frequency(
                self.thirteen_freq_combo,
                str(params.get("thirteenth_frequency") or "annual"),
            )
            self.bonus_coef_spin.setValue(
                float(params.get("year_end_bonus_coefficient") or 1.0)
            )
            self._set_frequency(
                self.bonus_freq_combo,
                str(params.get("year_end_bonus_frequency") or "annual"),
            )

            self.items_table.blockSignals(True)
            self.items_table.setRowCount(0)
            for item in salary_service.items(self.payload):
                self._append_item_row(item)
            self.items_table.blockSignals(False)

            self.salary_table.blockSignals(True)
            self.salary_table.setRowCount(0)
            for item in salary_service.salary_items(self.payload):
                self._append_salary_row(
                    str(item.get("item_type") or "performance"), item
                )
            self.salary_table.blockSignals(False)

            self._load_tax_params()
        finally:
            self._loading = False
        self._refresh_all_calculated()
        self._resize_items_table()
        self._resize_salary_table()

    def _set_frequency(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def _load_tax_params(self) -> None:
        params = salary_service.tax_params(self.payload)
        province = str(params.get("rent_province") or "")
        city = str(params.get("rent_city") or "")
        tier = float(params.get("rent_tier") or 0.0)
        district = str(params.get("rent_district") or "")
        if not city and tier > 0:
            city, province, tier = self._find_city_by_tier(tier)

        self.province_combo.blockSignals(True)
        self.city_combo.blockSignals(True)
        self.district_combo.blockSignals(True)
        try:
            province_index = self.province_combo.findData(province)
            if city and (province_index < 0 or not province):
                found_province, found_city, found_tier = self._find_city_data(
                    city, tier
                )
                if found_province:
                    province = found_province
                    city = found_city
                    tier = found_tier
                    province_index = self.province_combo.findData(province)
            self.province_combo.setCurrentIndex(max(0, province_index))
            self._populate_cities(province)
            city_index = self._find_city_index(city, tier)
            if city_index < 0 and tier > 0:
                city_index = self._fallback_city_index(tier)
            self.city_combo.setCurrentIndex(max(0, city_index))
            self._populate_districts(city)
            district_index = self.district_combo.findText(district)
            self.district_combo.setCurrentIndex(max(0, district_index))

            self.elderly_combo.setCurrentIndex(
                max(
                    0,
                    self.elderly_combo.findData(
                        str(params.get("elderly_option") or "only_child")
                    ),
                )
            )
            self.children_spin.setValue(
                int(params.get("children_education_count") or 0)
            )
            self.infant_spin.setValue(int(params.get("infant_care_count") or 0))
            self.continuing_combo.setCurrentIndex(
                max(
                    0,
                    self.continuing_combo.findData(
                        int(params.get("continuing_education") or 0)
                    ),
                )
            )
            self.mortgage_combo.setCurrentIndex(
                max(
                    0,
                    self.mortgage_combo.findData(
                        int(params.get("mortgage_interest") or 0)
                    ),
                )
            )
            severe_annual = float(params.get("severe_illness_annual") or 0.0)
            self.severe_combo.setCurrentIndex(1 if severe_annual > 0 else 0)
            self.severe_spin.setValue(severe_annual)
            self.custom_spin.setValue(
                float(params.get("custom_deduction") or 0.0)
            )
            self._set_frequency(
                self.bonus_method_combo,
                str(params.get("bonus_tax_method") or "separate"),
            )
        finally:
            self.province_combo.blockSignals(False)
            self.city_combo.blockSignals(False)
            self.district_combo.blockSignals(False)

    @staticmethod
    def _find_city_data(city: str, tier: float) -> tuple[str, str, float]:
        city_key = str(city or "").rstrip("市")
        for province, cities in tax_service.PROVINCE_CITIES.items():
            for name, city_tier in cities:
                if (name.rstrip("市") == city_key) and (
                    tier <= 0 or abs(city_tier - tier) < 1
                ):
                    return province, name, city_tier
        if tier > 0:
            return SalaryProfileTab._find_city_by_tier(tier)
        return "", "", 0.0

    @staticmethod
    def _find_city_by_tier(tier: float) -> tuple[str, str, float]:
        if tier >= 1500.0:
            return "北京市", "北京市", 1500.0
        if tier >= 1100.0:
            return "", "人口100万以上城市", 1100.0
        return "", "其他城市", 800.0

    def _fallback_city_index(self, tier: float) -> int:
        target = self._find_city_by_tier(tier)
        return max(0, self._find_city_index(target[1], target[2]))

    def _find_city_index(self, city: str, tier: float) -> int:
        for index in range(self.city_combo.count()):
            data = self.city_combo.itemData(index)
            if (
                isinstance(data, tuple)
                and len(data) == 2
                and data[0] == city
                and abs(float(data[1]) - float(tier)) < 0.01
            ):
                return index
        return -1

    def _province_changed(self) -> None:
        province = self.province_combo.currentData()
        self._populate_cities(province)
        city_data = self.city_combo.currentData() or ("", 0.0)
        self._populate_districts(city_data[0])
        self._refresh_all_calculated()

    def _city_changed(self) -> None:
        city_data = self.city_combo.currentData() or ("", 0.0)
        city = city_data[0]
        self._populate_districts(city)
        self._refresh_all_calculated()

    def _populate_cities(self, province: str) -> None:
        self.city_combo.blockSignals(True)
        try:
            self.city_combo.clear()
            if not province:
                self.city_combo.addItem("不享受", ("", 0.0))
                return
            for city, tier in tax_service.PROVINCE_CITIES.get(province, []):
                self.city_combo.addItem(
                    f"{city} · {tier:.0f}元/月", (city, tier)
                )
            self.city_combo.addItem(
                "人口100万以上城市 · 1100元/月",
                ("人口100万以上城市", 1100.0),
            )
            self.city_combo.addItem(
                "其他城市 · 800元/月", ("其他城市", 800.0)
            )
        finally:
            self.city_combo.blockSignals(False)

    def _populate_districts(self, city: str) -> None:
        self.district_combo.blockSignals(True)
        try:
            self.district_combo.clear()
            if not city:
                self.district_combo.addItem("不享受", "")
                return
            for district in ("市辖区", "县/县级市", "其他"):
                self.district_combo.addItem(district, district)
        finally:
            self.district_combo.blockSignals(False)

    def _append_item_row(self, item: dict | None = None) -> None:
        self.items_table.blockSignals(True)
        try:
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)
            values = [
                item.get("name", "") if item else "自定义险种",
                f"{float(item.get('base') or 0):.2f}" if item else "0",
                (
                    f"{float(item.get('personal_rate') or 0) * 100:.2f}"
                    if item
                    else "0"
                ),
                (
                    f"{float(item.get('company_rate') or 0) * 100:.2f}"
                    if item
                    else "0"
                ),
                (
                    f"{float(item['personal_fixed']):.2f}"
                    if item and item.get("personal_fixed") is not None
                    else ""
                ),
            ]
            for col, text in enumerate(values):
                table_item = QTableWidgetItem(text)
                table_item.setTextAlignment(Qt.AlignCenter)
                self.items_table.setItem(row, col, table_item)
        finally:
            self.items_table.blockSignals(False)
        self._resize_items_table()

    def _add_item_row(self) -> None:
        self._append_item_row()
        self.items_table.setCurrentCell(self.items_table.rowCount() - 1, 0)
        self._refresh_all_calculated()

    def _delete_item_row(self) -> None:
        row = self.items_table.currentRow()
        if row < 0:
            return
        item = self._item_from_row(row)
        if not confirm_delete(self, "删除险种", f"确定删除“{item['name']}”？"):
            return
        self._deleted_rows.append(item)
        self.items_table.removeRow(row)
        self._refresh_all_calculated()
        self._resize_items_table()

    def _undo_delete_row(self) -> None:
        if not self._deleted_rows:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        self._append_item_row(self._deleted_rows.pop())
        self._refresh_all_calculated()

    def _append_salary_row(
        self, item_type: str, item: dict | None = None
    ) -> None:
        self.salary_table.blockSignals(True)
        try:
            row = self.salary_table.rowCount()
            self.salary_table.insertRow(row)
            type_item = QTableWidgetItem(
                "补贴" if item_type == "subsidy" else "绩效"
            )
            type_item.setTextAlignment(Qt.AlignCenter)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.salary_table.setItem(row, 0, type_item)
            name_item = QTableWidgetItem(
                item.get("name", "") if item else "自定义"
            )
            name_item.setTextAlignment(Qt.AlignCenter)
            self.salary_table.setItem(row, 1, name_item)
            amount_item = QTableWidgetItem(
                f"{float(item.get('amount') or 0):.2f}" if item else "0"
            )
            amount_item.setTextAlignment(Qt.AlignCenter)
            self.salary_table.setItem(row, 2, amount_item)
            frequency = (
                str(item.get("frequency") or "monthly") if item else "monthly"
            )
            combo = self._frequency_combo(frequency)
            combo.currentIndexChanged.connect(
                lambda _: self._refresh_all_calculated()
            )
            self.salary_table.setCellWidget(row, 3, combo)
        finally:
            self.salary_table.blockSignals(False)
        self._resize_salary_table()

    def _add_performance_row(self) -> None:
        self._append_salary_row("performance")
        self.salary_table.setCurrentCell(self.salary_table.rowCount() - 1, 1)
        self._refresh_all_calculated()

    def _add_subsidy_row(self) -> None:
        self._append_salary_row("subsidy")
        self.salary_table.setCurrentCell(self.salary_table.rowCount() - 1, 1)
        self._refresh_all_calculated()

    def _delete_salary_row(self) -> None:
        row = self.salary_table.currentRow()
        if row < 0:
            return
        item = self._salary_item_from_row(row)
        if not confirm_delete(
            self, "删除工资项", f"确定删除“{item['name']}”？"
        ):
            return
        self._deleted_salary_rows.append(item)
        self.salary_table.removeRow(row)
        self._refresh_all_calculated()
        self._resize_salary_table()

    def _undo_salary_row(self) -> None:
        if not self._deleted_salary_rows:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        item = self._deleted_salary_rows.pop()
        self._append_salary_row(item.get("item_type", "performance"), item)
        self._refresh_all_calculated()

    def _salary_item_from_row(self, row: int) -> dict:
        type_item = self.salary_table.item(row, 0)
        combo = self.salary_table.cellWidget(row, 3)
        return {
            "item_type": (
                "subsidy"
                if type_item and type_item.text() == "补贴"
                else "performance"
            ),
            "name": (
                self.salary_table.item(row, 1).text().strip() or "自定义"
            ),
            "amount": _parse_float(self.salary_table.item(row, 2).text()),
            "frequency": combo.currentData() if combo else "monthly",
        }

    def _item_from_row(self, row: int) -> dict:
        fixed_text = self.items_table.item(row, 4).text().strip()
        return {
            "name": self.items_table.item(row, 0).text().strip(),
            "base": _parse_float(self.items_table.item(row, 1).text()),
            "personal_rate": (
                _parse_float(self.items_table.item(row, 2).text()) / 100.0
            ),
            "company_rate": (
                _parse_float(self.items_table.item(row, 3).text()) / 100.0
            ),
            "personal_fixed": (
                _parse_float(fixed_text) if fixed_text else None
            ),
        }

    def _salary_params(self) -> dict:
        params = salary_service.default_params()
        params.update(
            {
                "monthly_salary": float(self.base_spin.value()),
                "thirteenth_coefficient": float(
                    self.thirteen_coef_spin.value()
                ),
                "thirteenth_frequency": self.thirteen_freq_combo.currentData(),
                "year_end_bonus_coefficient": float(
                    self.bonus_coef_spin.value()
                ),
                "year_end_bonus_frequency": self.bonus_freq_combo.currentData(),
            }
        )
        return params

    def _items_from_table(self) -> list[dict]:
        items = []
        for row in range(self.items_table.rowCount()):
            name = self.items_table.item(row, 0).text().strip()
            if not name:
                continue
            items.append(self._item_from_row(row))
        return items

    def _salary_items_from_table(self) -> list[dict]:
        items = []
        for row in range(self.salary_table.rowCount()):
            name = self.salary_table.item(row, 1).text().strip()
            if not name:
                continue
            items.append(self._salary_item_from_row(row))
        return items

    def current_payload(self) -> dict:
        return {
            "year": self._current_year(),
            "params": self._salary_params(),
            "items": self._items_from_table(),
            "salary_items": self._salary_items_from_table(),
            "tax_params": self._tax_params_from_form(),
        }

    def _save_salary(self) -> None:
        self._save_payload()
        flash_saved(self.salary_save_button)

    def _save_insurance(self) -> None:
        self._save_payload()
        flash_saved(self.items_save_button)

    def _save_deduction(self) -> None:
        self._save_payload()
        flash_saved(self.deduction_save_button)

    def save(self) -> None:
        """全局保存：根据焦点保存工资详情、N险N金或专项附加扣除。"""
        focus = QApplication.focusWidget()
        if _widget_in_table(focus, self.salary_table):
            self._save_salary()
        elif _widget_in_table(focus, self.items_table):
            self._save_insurance()
        else:
            self._save_deduction()

    def undo(self) -> None:
        """全局撤销：优先恢复工资项，其次恢复险种。"""
        if self._deleted_salary_rows:
            self._undo_salary_row()
        elif self._deleted_rows:
            self._undo_delete_row()

    def _save_payload(self) -> None:
        payload = self.current_payload()
        repository.save_salary_profile(
            self.conn,
            self.profile_id,
            self.profile_name,
            payload["year"],
            payload,
        )
        self.conn.commit()

    def _on_insurance_changed(self, *_args) -> None:
        self._refresh_all_calculated()
        self._resize_items_table()

    def _refresh_all_calculated(self) -> None:
        if self._loading or not hasattr(self, "result_labels"):
            return
        payload = self.current_payload()
        social = salary_service.social_result(payload)
        values = {
            "total_salary": money(social["total_salary"]),
            "personal_total": money(social["personal_total"]),
            "company_total": money(social["company_total"]),
            "gross_income": money(social["gross_income"]),
            "total_package": money(social["total_package"]),
        }
        for key, text in values.items():
            self.result_labels[key].setText(text)

        actual = tax_service.monthly_schedule_profile(
            self.conn,
            payload["year"],
            payload,
            self.bonus_method_combo.currentData(),
        )
        actual_values = {
            "total_income": money(actual["total_income"]),
            "taxable_income": money(actual["taxable_income"]),
            "wage_tax": money(actual["wage_tax"]),
            "bonus_tax": money(actual["bonus_tax"]),
            "total_tax": money(actual["total_tax"]),
            "net_income": money(actual["net_income"]),
            "monthly_net": money(actual["monthly_net"]),
        }
        for key, text in actual_values.items():
            self.result_labels[key].setText(text)
        for row, item in enumerate(actual["monthly_schedule"]):
            for col, key in [
                (1, "gross"),
                (2, "personal_insurance"),
                (3, "special_deduction"),
                (4, "taxable_income"),
                (5, "cumulative_tax"),
                (6, "month_tax"),
                (7, "net_income"),
            ]:
                self.actual_table.item(row, col).setText(money(item[key]))
            self.actual_table.item(row, 0).setText(f"{row + 1} 月")

    def _tax_params_from_form(self) -> dict:
        rent_city, rent_tier = self.city_combo.currentData() or ("", 0.0)
        return {
            "rent_city": str(rent_city or ""),
            "rent_province": str(self.province_combo.currentData() or ""),
            "rent_district": str(self.district_combo.currentText() or ""),
            "rent_tier": float(rent_tier or 0.0),
            "elderly_option": self.elderly_combo.currentData(),
            "children_education_count": int(self.children_spin.value()),
            "infant_care_count": int(self.infant_spin.value()),
            "continuing_education": int(self.continuing_combo.currentData()),
            "mortgage_interest": int(self.mortgage_combo.currentData()),
            "severe_illness_annual": (
                float(self.severe_spin.value())
                if int(self.severe_combo.currentData())
                else 0.0
            ),
            "bonus_tax_method": self.bonus_method_combo.currentData(),
            "custom_deduction": float(self.custom_spin.value()),
        }

    def _resize_items_table(self) -> None:
        if not hasattr(self, "items_table"):
            return
        self.items_table.resizeRowsToContents()
        total = (
            sum(
                self.items_table.rowHeight(row)
                for row in range(self.items_table.rowCount())
            )
            + self.items_table.horizontalHeader().height()
            + 4
        )
        self.items_table.setMinimumHeight(max(total, 4 * 32 + 34))

    def _resize_salary_table(self) -> None:
        if not hasattr(self, "salary_table"):
            return
        self.salary_table.resizeRowsToContents()
        total = (
            sum(
                self.salary_table.rowHeight(row)
                for row in range(self.salary_table.rowCount())
            )
            + self.salary_table.horizontalHeader().height()
            + 4
        )
        self.salary_table.setMinimumHeight(max(total, 2 * 32 + 34))

    def _add_result_row(
        self, grid, row: int, key: str, title: str, info: str = ""
    ) -> QLabel:
        label_widget = info_label(title, info)
        grid.addWidget(label_widget, row, 0)
        value = QLabel("-")
        value.setObjectName("summaryValue")
        grid.addWidget(value, row, 1)
        button = self._formula_button(key)
        if button is not None:
            grid.addWidget(button, row, 2)
        return value

    def _formula_button(self, key: str) -> QPushButton | None:
        if not self._formula_enabled:
            return None
        button = make_button("查看公式")
        button.clicked.connect(
            lambda _=False, k=key: QMessageBox.information(
                self, "计算公式", self._formula_text(k)
            )
        )
        return button

    @staticmethod
    def _formula_text(key: str) -> str:
        texts = {
            "total_salary": (
                "总工资 = 基本工资×12 + 13薪×基本工资×发放次数\n"
                "+ 年终奖×基本工资×发放次数\n"
                "+ Σ(绩效金额×发放次数) + Σ(补贴金额×发放次数)\n"
                "发放次数：按月=12，按季=4，按年=1"
            ),
            "personal_total": "个人五险一金（月） = Σ(险种基数×个人比例) + Σ个人固定金额",
            "company_total": "公司五险一金（月） = Σ(险种基数×公司比例)",
            "gross_income": "税前总收入 = 总工资 - 个人五险一金×12",
            "total_package": "总包 = 税前总收入 + 公司五险一金×12",
            "total_income": "全年应税收入 = Σ(月工资 + 年终奖 + 各类补贴)",
            "taxable_income": (
                "全年应纳税所得额 = 全年应税收入 - 个人五险一金×12\n"
                "- 60000（起征点5000×12）- 专项附加扣除×12 - 大病医疗"
            ),
            "wage_tax": (
                "工资个税按累计预扣预缴：逐月累计应税所得，"
                "按月计算累计应缴个税后减去已预缴"
            ),
            "bonus_tax": (
                "年终奖单独计税：年终奖÷12 查月度税率表\n"
                "税额 = 年终奖×税率 - 速算扣除数"
            ),
            "total_tax": "全年应缴个税 = 工资个税 + 年终奖个税",
            "net_income": (
                "全年税后收入 = 全年应税收入 - 个人五险一金×12 - 全年应缴个税"
            ),
            "monthly_net": "月均税后收入 = 全年税后收入 ÷ 12",
        }
        return texts.get(key, key)


def _widget_in_table(widget, table) -> bool:
    current = widget
    while current is not None:
        if current is table:
            return True
        current = current.parentWidget()
    return False


def _parse_float(text: str) -> float:
    text = text.strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
