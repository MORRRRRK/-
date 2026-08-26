from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...edition import is_customer
from ...services import account_service, calculations, transaction_service
from ..charts import bar_chart, pie_chart, update_bar_chart, update_pie_chart
from ..widgets import Section, StatCard, make_formula_button, money, pct

OVERVIEW_FORMULA_TEXT = (
    "净资产 = 累计存款 + 投资总持仓\n"
    "累计存款 = Σ 每月强制存款\n"
    "投资持仓 = Σ 各类持仓市值 + Σ 黄金账户市值\n"
    "累计收益 = Σ 各类累计收益 + Σ 黄金账户收益\n"
    "总收益率 = 累计收益 ÷ 投资持仓\n"
    "年度工资 = Σ 每月月工资\n"
    "年度收入 = Σ(月工资 + 年终奖 + 补贴 + 报销)\n"
    "住宿成本 = Σ 房租；理论结余 = 年度收入 + 住宿成本\n"
    "消费 = Σ 每月支出；储蓄率 = 存款 ÷ 收入"
)


class OverviewPage(QScrollArea):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._last_chart_signature: tuple | None = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        cards_row = QHBoxLayout()
        self.net_worth_card = StatCard("净资产（存款 + 持仓）")
        self.deposit_card = StatCard("累计存款")
        self.holding_card = StatCard("投资持仓")
        self.profit_card = StatCard("累计收益")
        self.rate_card = StatCard("总收益率")
        for card in (
            self.net_worth_card,
            self.deposit_card,
            self.holding_card,
            self.profit_card,
            self.rate_card,
        ):
            cards_row.addWidget(card)
        layout.addLayout(cards_row)

        charts_col = QVBoxLayout()
        self.trend_holder = QWidget()
        self.pie_holder = QWidget()
        self._trend_view = bar_chart(
            ["暂无"], {"收入": [0]}, "收入 / 结余 / 存款", height=340
        )
        self._pie_view = pie_chart(["暂无"], [0], "资产配置", height=300)
        trend_layout = QVBoxLayout(self.trend_holder)
        trend_layout.setContentsMargins(0, 0, 0, 0)
        trend_layout.addWidget(self._trend_view)
        pie_layout = QVBoxLayout(self.pie_holder)
        pie_layout.setContentsMargins(0, 0, 0, 0)
        pie_layout.addWidget(self._pie_view)
        charts_col.addWidget(self.trend_holder)
        charts_col.addWidget(self.pie_holder)
        layout.addLayout(charts_col)

        annual_actions = []
        if not is_customer():
            annual_actions.append(
                make_formula_button(
                    self, "资产总览计算公式", OVERVIEW_FORMULA_TEXT
                )
            )
        annual_section = Section("汇总明细", actions=annual_actions)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("显示方式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("按年汇总", "year")
        self.mode_combo.addItem("按月汇总", "month")
        self.mode_combo.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.mode_combo)
        controls.addWidget(QLabel("年份"))
        self.month_year_combo = QComboBox()
        self.month_year_combo.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.month_year_combo)
        controls.addStretch(1)
        annual_section.add_layout(controls)

        self.summary_table = QTableWidget(0, 7)
        self.summary_table.setHorizontalHeaderLabels(
            ["月份/年份", "工资", "收入", "住宿成本", "理论结余", "存款", "消费"]
        )
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.summary_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.summary_table.setMinimumHeight(220)
        annual_section.add(self.summary_table)
        layout.addWidget(annual_section)
        layout.addStretch(1)

    def refresh(self) -> None:
        has_accounts = bool(
            self.conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone()
        )
        has_transactions = bool(
            self.conn.execute("SELECT 1 FROM transactions LIMIT 1").fetchone()
        )
        totals = calculations.totals(self.conn)
        invest = calculations.investment_summary(self.conn)
        if has_accounts:
            account_summary = account_service.get_account_summary(self.conn)
            net_worth = account_summary["net_worth"]
        else:
            net_worth = totals["deposits"] + invest["total_holding"]
        self.net_worth_card.set_value(money(net_worth), "存款 + 投资持仓")
        self.deposit_card.set_value(money(totals["deposits"]), "")
        self.holding_card.set_value(money(invest["total_holding"]), "")
        self.profit_card.set_value(money(invest["total_cumulative"]), "")
        self.rate_card.set_value(pct(invest["total_rate"]), "")

        years = repository.list_years(self.conn)
        selected_year = (
            self.month_year_combo.currentData()
            if self.month_year_combo.count()
            else None
        )
        self.month_year_combo.blockSignals(True)
        self.month_year_combo.clear()
        for year in years:
            self.month_year_combo.addItem(str(year["year"]), year["year"])
        if selected_year is None and years:
            selected_year = years[-1]["year"]
        index = self.month_year_combo.findData(selected_year)
        self.month_year_combo.setCurrentIndex(max(0, index))
        self.month_year_combo.blockSignals(False)

        categories = []
        income_values = []
        balance_values = []
        deposit_values = []
        expense_values = []
        rows: list[list[str]] = []
        mode = self.mode_combo.currentData()
        if mode == "month":
            year_id = None
            if self.month_year_combo.count():
                year_value = self.month_year_combo.currentData()
                for year in years:
                    if year["year"] == year_value:
                        year_id = year["id"]
                        break
            if year_id is not None:
                records = repository.get_monthly_records(self.conn, year_id)
                for month in range(1, 13):
                    rec = records.get(month, {})
                    salary = float(rec.get("salary", 0.0) or 0.0)
                    income = salary + float(rec.get("year_end_bonus", 0.0) or 0.0) + float(
                        rec.get("subsidies", 0.0) or 0.0
                    ) + float(rec.get("reimbursements", 0.0) or 0.0)
                    housing = float(rec.get("rent", 0.0) or 0.0) + float(
                        rec.get("utilities", 0.0) or 0.0
                    )
                    deposits = float(rec.get("forced_deposit", 0.0) or 0.0)
                    expense = float(rec.get("monthly_expense", 0.0) or 0.0)
                    rows.append(
                        [
                            f"{month} 月",
                            money(salary),
                            money(income),
                            money(housing),
                            money(income + housing),
                            money(deposits),
                            money(expense),
                        ]
                    )
                    categories.append(f"{month}月")
                    income_values.append(income)
                    balance_values.append(income + housing)
                    deposit_values.append(deposits)
                    expense_values.append(expense)
        else:
            for year in years:
                summary = calculations.year_summary(self.conn, year["id"])
                rows.append(
                    [
                        str(year["year"]),
                        money(summary["salary"]),
                        money(summary["income"]),
                        money(summary["housing_cost"]),
                        money(summary["balance"]),
                        money(summary["deposits"]),
                        money(summary["monthly_expense"]),
                    ]
                )
                categories.append(str(year["year"]))
                income_values.append(summary["income"])
                balance_values.append(summary["balance"])
                deposit_values.append(summary["deposits"])
                expense_values.append(summary["monthly_expense"])

        self.summary_table.setRowCount(len(rows))
        self.summary_table.setMinimumHeight(max(len(rows), 4) * 32 + 34)
        for r, values in enumerate(rows):
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                self.summary_table.setItem(r, c, item)

        if has_accounts:
            allocation = {}
            for account in account_service.get_accounts(self.conn):
                allocation[account["name"]] = account["current_balance"]
        else:
            allocation = {
                "存款": totals["deposits"],
                "基金": invest["categories"].get("基金", {}).get("holding", 0),
                "黄金": invest["categories"].get("黄金", {}).get("holding", 0),
                "黄金账户": invest["categories"].get("黄金账户", {}).get("holding", 0),
                "股票": invest["categories"].get("股票", {}).get("holding", 0),
            }
        if has_transactions:
            for year in years:
                summary = transaction_service.get_yearly_summary(
                    self.conn, year["year"]
                )
                income_values = [
                    transaction_service.get_monthly_summary(
                        self.conn, year["year"], month
                    )["income"]
                    for month in range(1, 13)
                ]
                expense_values = [
                    transaction_service.get_monthly_summary(
                        self.conn, year["year"], month
                    )["expense"]
                    for month in range(1, 13)
                ]
        signature = (
            tuple(categories),
            tuple(round(value, 2) for value in income_values),
            tuple(round(value, 2) for value in balance_values),
            tuple(round(value, 2) for value in deposit_values),
            tuple(round(value, 2) for value in expense_values),
            tuple(allocation.keys()),
            tuple(round(value, 2) for value in allocation.values()),
        )
        if signature != self._last_chart_signature:
            update_bar_chart(
                self._trend_view,
                categories,
                {
                    "收入": income_values,
                    "结余": balance_values,
                    "存款": deposit_values,
                    "消费": expense_values,
                },
                "收入 / 结余 / 存款 / 消费",
            )
            update_pie_chart(
                self._pie_view,
                list(allocation.keys()),
                list(allocation.values()),
                "资产配置",
            )
            self._last_chart_signature = signature
