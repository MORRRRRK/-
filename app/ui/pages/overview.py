from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...edition import is_customer
from ...services import calculations, transaction_service
from ..widgets import (
    StatCard,
    make_formula_button,
    money,
)

OVERVIEW_FORMULA_TEXT = (
    "净资产 = 累计存款 + 投资总持仓\n"
    "累计存款 = Σ 每月强制存款\n"
    "投资持仓 = Σ 各类持仓市值 + Σ 黄金账户市值\n"
    "累计收益 = Σ 各类累计收益 + Σ 黄金账户收益\n"
    "总收益率 = 累计收益 ÷ 投资持仓\n"
    "本年度收入 = Σ 导入交易中的收入\n"
    "本年度支出 = Σ 导入交易中的支出\n"
    "结余 = 收入 - 支出；强制存款 = Σ 该年每月强制存款"
)


class OverviewPage(QScrollArea):
    """极简资产总览：总额卡片 + 本年度汇总。"""

    def __init__(self, conn, on_change=None):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("资产总览")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)
        if not is_customer():
            header.addWidget(
                make_formula_button(
                    self, "资产总览计算公式", OVERVIEW_FORMULA_TEXT
                )
            )
        layout.addLayout(header)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
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
            card.setObjectName("bigStatCard")
            card.setMinimumHeight(126)
            cards_row.addWidget(card)
        layout.addLayout(cards_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("divider")
        layout.addWidget(divider)

        year_row = QHBoxLayout()
        year_row.addWidget(QLabel("年份"))
        self.year_combo = QComboBox()
        self.year_combo.currentIndexChanged.connect(self.refresh)
        self.year_combo.setFixedWidth(120)
        year_row.addWidget(self.year_combo)
        year_row.addStretch(1)
        layout.addLayout(year_row)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(14)
        self.year_income_card = StatCard("本年度收入")
        self.year_expense_card = StatCard("本年度支出")
        self.year_balance_card = StatCard("本年度结余")
        self.year_deposit_card = StatCard("本年度强制存款")
        for card in (
            self.year_income_card,
            self.year_expense_card,
            self.year_balance_card,
            self.year_deposit_card,
        ):
            card.setObjectName("summaryStatCard")
            card.setMinimumHeight(110)
            summary_row.addWidget(card)
        layout.addLayout(summary_row)
        layout.addStretch(1)

    def refresh(self) -> None:
        current_year = date.today().year
        years = sorted(
            {
                int(y["year"])
                for y in repository.list_years(self.conn)
                if int(y["year"]) >= 2000
            }
            | {current_year}
        )
        selected = (
            self.year_combo.currentData()
            if self.year_combo.count()
            else current_year
        )
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for year in sorted(years, reverse=True):
            self.year_combo.addItem(str(year), year)
        index = self.year_combo.findData(selected)
        self.year_combo.setCurrentIndex(max(0, index))
        self.year_combo.blockSignals(False)
        year = int(self.year_combo.currentData() or current_year)

        totals = calculations.totals(self.conn)
        invest = calculations.investment_summary(self.conn)
        deposits = totals["deposits"]
        self.net_worth_card.set_value(
            money(deposits + invest["total_holding"]), "存款 + 投资持仓"
        )
        self.deposit_card.set_value(money(deposits), "")
        self.holding_card.set_value(money(invest["total_holding"]), "")
        self.profit_card.set_value(money(invest["total_cumulative"]), "")
        self.rate_card.set_value(
            f"{invest['total_rate'] * 100:.2f}%", ""
        )

        year_summary = transaction_service.get_yearly_summary(self.conn, year)
        year_id = repository.ensure_year(self.conn, year)
        records = repository.get_monthly_records(self.conn, year_id)
        year_deposit = sum(
            float(rec.get("forced_deposit", 0.0) or 0.0)
            for rec in records.values()
        )
        self.year_income_card.set_value(
            money(year_summary["income"]), "仅统计导入的流水"
        )
        self.year_expense_card.set_value(
            money(year_summary["expense"]), "仅统计导入的流水"
        )
        self.year_balance_card.set_value(money(year_summary["balance"]), "")
        self.year_deposit_card.set_value(money(year_deposit), "")
