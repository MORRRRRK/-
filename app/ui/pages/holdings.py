from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QAbstractScrollArea,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...core.paths import db_path
from ...edition import is_customer
from ...services import account_service, calculations
from ...services.eastmoney import EastMoneyError, search_fund
from ...services import investing
from ...services.market import MarketClient, MarketError, fetch_live_price
from ...services.market_refresh import MarketRefreshWorker
from ..widgets import (
    Section,
    confirm_delete,
    flash_saved,
    make_button,
    make_formula_button,
    money,
    pct,
)
from .accounts import AccountDialog
from .holdings_chat import HoldingsChatPanel

ASSET_TYPES = [
    ("股票 (A股)", "stock"),
    ("场内基金 (ETF/LOF)", "fund_exchange"),
    ("场外基金", "fund_otc"),
    ("黄金 ETF", "gold_etf"),
]

CATEGORIES = ["基金", "黄金", "股票"]
INVEST_TIMES = ["每日", "每周一", "每月1日", "暂停"]

HOLDINGS_FORMULA_TEXT = (
    "净值：股票=实时价格，场内基金/ETF=最新价，场外基金=单位净值，黄金 ETF=实时价格\n"
    "持仓市值 = 份额 × 净值\n"
    "持有收益 = 持仓市值 - 成本\n"
    "累计收益 = 用户累计确认的收益快照（含已赎回收益）\n"
    "收益率 = 累计收益 ÷ 持仓市值\n"
    "总持仓 = Σ 各类持仓市值 + Σ 黄金账户市值\n"
    "总累计收益 = Σ 各类累计收益 + Σ 黄金账户收益\n"
    "总收益率 = 总累计收益 ÷ 总持仓\n"
    "定投执行：份额 += 定投金额 ÷ 净值；成本 += 定投金额"
)

GOLD_FORMULA_TEXT = (
    "黄金账户当前市值 = 克数 × 参考金价\n"
    "黄金账户收益 = 当前市值 - 成本\n"
    "实时金价来自新浪/公开金价接口，仅为参考"
)


class HoldingsPage(QWidget):
    def __init__(self, conn, on_change):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._rows: list[dict] = []
        self._row_ids: list[int | None] = []
        self._deleted_holdings: list[dict] = []
        self._gold_rows: list[dict] = []
        self._gold_ids: list[int | None] = []
        self._deleted_gold: list[dict] = []
        self._gold_reference_price: float | None = None
        self._refresh_worker: MarketRefreshWorker | None = None
        self._formula_enabled = not is_customer()
        self._content = QWidget()
        self._build()

    def _build(self) -> None:
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)

        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setWidget(self._content)

        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._build_accounts_section(layout)

        top = QHBoxLayout()
        top.addStretch(1)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("summaryValue")
        top.addWidget(self.summary_label)
        if self._formula_enabled:
            top.addWidget(
                make_formula_button(
                    self, "持仓计算公式", HOLDINGS_FORMULA_TEXT
                )
            )
        layout.addLayout(top)

        action_row = QHBoxLayout()
        self.add_row_button = make_button("新增持仓")
        self.delete_row_button = make_button("删除选中")
        self.undo_button = make_button("撤销删除")
        self.resolve_button = make_button("按名称解析代码")
        self.refresh_button = make_button("刷新实时行情")
        self.history_button = make_button("查看交易")
        self.save_button = make_button("保存修改", primary=True)
        self.save_button.setMinimumSize(150, 42)
        self.add_row_button.clicked.connect(self._add_row)
        self.delete_row_button.clicked.connect(self._delete_row)
        self.undo_button.clicked.connect(self._undo_delete)
        self.resolve_button.clicked.connect(self._resolve_symbol)
        self.refresh_button.clicked.connect(lambda: self._refresh_market(show_popup=True))
        self.history_button.clicked.connect(self._show_history)
        self.save_button.clicked.connect(self._save_all)
        for button in (
            self.add_row_button,
            self.delete_row_button,
            self.undo_button,
            self.resolve_button,
            self.refresh_button,
            self.history_button,
        ):
            action_row.addWidget(button)
        action_row.addStretch(1)
        action_row.addWidget(self.save_button)
        layout.addLayout(action_row)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部"] + CATEGORIES)
        self.filter_combo.currentTextChanged.connect(self._reload_table)
        self.filter_combo.setFixedWidth(96)
        self.account_combo = QComboBox()
        self.account_combo.currentIndexChanged.connect(self._reload_table)
        self.account_combo.setMinimumWidth(120)
        self.asset_combo = QComboBox()
        self.asset_combo.addItems(
            ["全部"] + [label for label, _value in ASSET_TYPES]
        )
        self.asset_combo.currentTextChanged.connect(self._reload_table)
        self.asset_combo.setMinimumWidth(120)
        table_section = Section(
            "持仓列表",
            actions=[
                self.filter_combo,
                self.account_combo,
                self.asset_combo,
            ],
            info="直接在表格中修改，点右上角“保存修改”后全部生效",
        )
        self.table = QTableWidget(0, 15)
        self.table._enter_save = True
        self.table.setHorizontalHeaderLabels(
            [
                "类别", "渠道", "名称", "代码", "资产类型", "净值", "份额",
                "持仓", "持有收益", "累计收益", "收益率", "成本", "定投金额",
                "定投时间", "更新时间",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.table.setMinimumHeight(8 * 32 + 34)
        table_section.add(self.table)
        layout.addWidget(table_section)

        gold_section = Section(
            "黄金账户",
            info="积存金 / 易存金按克记录，参考实时金价",
        )
        gold_top = QHBoxLayout()
        self.gold_refresh_button = make_button("刷新实时金价")
        self.gold_add_button = make_button("新增黄金账户")
        self.gold_delete_button = make_button("删除选中")
        self.gold_undo_button = make_button("撤销删除")
        self.gold_save_button = make_button("保存黄金账户", primary=True)
        self.gold_refresh_button.clicked.connect(
            lambda: self._refresh_market(show_popup=True)
        )
        self.gold_add_button.clicked.connect(self._add_gold_row)
        self.gold_delete_button.clicked.connect(self._delete_gold_row)
        self.gold_undo_button.clicked.connect(self._undo_gold_delete)
        self.gold_save_button.clicked.connect(self._save_gold)
        self.gold_price_label = QLabel("实时金价：未获取")
        self.gold_price_label.setObjectName("summaryValue")
        gold_top.addWidget(self.gold_refresh_button)
        gold_top.addWidget(self.gold_add_button)
        gold_top.addWidget(self.gold_delete_button)
        gold_top.addWidget(self.gold_undo_button)
        gold_top.addWidget(self.gold_save_button)
        gold_top.addStretch(1)
        gold_top.addWidget(self.gold_price_label)
        if self._formula_enabled:
            gold_top.addWidget(
                make_formula_button(
                    self, "黄金账户计算公式", GOLD_FORMULA_TEXT
                )
            )
        gold_section.add_layout(gold_top)

        self.gold_table = QTableWidget(0, 8)
        self.gold_table._enter_save = True
        self.gold_table.setHorizontalHeaderLabels(
            ["名称", "渠道", "克数", "参考金价", "当前市值", "成本", "收益", "备注"]
        )
        self.gold_table.verticalHeader().setVisible(False)
        self.gold_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.gold_table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.gold_table.setMinimumHeight(4 * 32 + 34)
        gold_section.add(self.gold_table)
        layout.addWidget(gold_section)
        layout.addStretch(1)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self._left_scroll)
        self.chat_panel = HoldingsChatPanel(self.conn, self.on_change)
        self.splitter.addWidget(self.chat_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([900, 420])
        page_layout.addWidget(self.splitter, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self._refresh_market(show_popup=False))
        self.timer.start(60_000)
        self.refresh()
        QTimer.singleShot(1200, lambda: self._refresh_market(show_popup=False))

    def _build_accounts_section(self, layout) -> None:
        section = Section(
            "账户管理",
            info="先建立账户，才能在下方的持仓列表中选择渠道",
        )
        buttons = QHBoxLayout()
        self.account_add_button = make_button("新增账户", primary=True)
        self.account_edit_button = make_button("编辑账户")
        self.account_delete_button = make_button("删除账户")
        self.account_add_button.clicked.connect(self._add_account)
        self.account_edit_button.clicked.connect(self._edit_account)
        self.account_delete_button.clicked.connect(self._delete_account)
        buttons.addWidget(self.account_add_button)
        buttons.addWidget(self.account_edit_button)
        buttons.addWidget(self.account_delete_button)
        buttons.addStretch(1)
        section.add_layout(buttons)

        self.accounts_table = QTableWidget(0, 5)
        self.accounts_table.setHorizontalHeaderLabels(
            ["名称", "类型", "机构", "当前余额", "备注"]
        )
        self.accounts_table.verticalHeader().setVisible(False)
        self.accounts_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.accounts_table.doubleClicked.connect(
            lambda _: self._edit_account()
        )
        self.accounts_table.setMinimumHeight(8 * 34 + 34)
        section.add(self.accounts_table)
        layout.addWidget(section)

    def _reload_accounts(self) -> None:
        accounts = account_service.get_accounts(self.conn)
        self._account_ids = [a["id"] for a in accounts]
        self.accounts_table.setRowCount(len(accounts))
        type_names = {
            "cash": "现金", "bank": "银行卡", "alipay": "支付宝",
            "wechat": "微信", "investment": "投资账户",
            "credit_card": "信用卡", "loan": "贷款", "other": "其他",
        }
        for r, account in enumerate(accounts):
            values = [
                account["name"],
                type_names.get(account["type"], account["type"]),
                account["institution"],
                money(account["current_balance"]),
                account["note"],
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(
                    Qt.AlignRight | Qt.AlignVCenter
                    if c == 3
                    else Qt.AlignCenter
                )
                self.accounts_table.setItem(r, c, item)

        current = self.account_combo.currentData()
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        self.account_combo.addItem("全部账户", None)
        for account in accounts:
            self.account_combo.addItem(account["name"], account["id"])
        index = self.account_combo.findData(current)
        self.account_combo.setCurrentIndex(max(0, index))
        self.account_combo.blockSignals(False)

    def _selected_account_id(self) -> int | None:
        row = self.accounts_table.currentRow()
        if 0 <= row < len(self._account_ids):
            return self._account_ids[row]
        return None

    def _add_account(self) -> None:
        dialog = AccountDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        account_service.add_account(self.conn, **dialog.values())
        self.conn.commit()
        self.refresh()
        self.on_change()

    def _edit_account(self) -> None:
        account_id = self._selected_account_id()
        if account_id is None:
            QMessageBox.information(self, "提示", "请先选择账户")
            return
        account = account_service.get_account(self.conn, account_id)
        dialog = AccountDialog(self, account)
        if dialog.exec() != QDialog.Accepted:
            return
        account_service.update_account(
            self.conn, account_id, **dialog.values()
        )
        self.conn.commit()
        self.refresh()
        self.on_change()

    def _delete_account(self) -> None:
        account_id = self._selected_account_id()
        if account_id is None:
            QMessageBox.information(self, "提示", "请先选择账户")
            return
        account = account_service.get_account(self.conn, account_id)
        if not confirm_delete(
            self, "删除账户", f"确定删除账户“{account['name']}”？"
        ):
            return
        try:
            account_service.delete_account(self.conn, account_id)
        except ValueError as exc:
            QMessageBox.warning(self, "无法删除", str(exc))
            return
        self.conn.commit()
        self.refresh()
        self.on_change()

    def _append_row(self, holding: dict | None = None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._rows.append(dict(holding) if holding else {})
        self._row_ids.append(holding["id"] if holding else None)

        category_combo = QComboBox()
        category_combo.setEditable(True)
        category_combo.addItems(CATEGORIES)
        category_combo.setCurrentText(holding["category"] if holding else "基金")
        self.table.setCellWidget(row, 0, category_combo)

        channel_combo = QComboBox()
        for account in account_service.get_accounts(self.conn):
            channel_combo.addItem(account["name"], account["id"])
        if holding:
            if holding.get("account_id"):
                index = channel_combo.findData(holding["account_id"])
                channel_combo.setCurrentIndex(max(0, index))
            else:
                channel_combo.setCurrentText(holding.get("channel") or "")
        self.table.setCellWidget(row, 1, channel_combo)

        name_item = QTableWidgetItem(holding["name"] if holding else "")
        self.table.setItem(row, 2, name_item)
        symbol_edit = QLineEdit(holding["symbol"] if holding else "")
        symbol_edit._enter_save = False
        symbol_edit.setAlignment(Qt.AlignCenter)
        symbol_edit.returnPressed.connect(
            lambda _row=row: self._auto_fill_symbol(_row)
        )
        self.table.setCellWidget(row, 3, symbol_edit)

        asset_combo = QComboBox()
        asset_combo.setEditable(True)
        for label, value in ASSET_TYPES:
            asset_combo.addItem(label, value)
        if holding and holding["asset_type"]:
            index = asset_combo.findData(holding["asset_type"])
            if index >= 0:
                asset_combo.setCurrentIndex(index)
            else:
                asset_combo.setCurrentText(holding["asset_type"])
        self.table.setCellWidget(row, 4, asset_combo)

        net_value = (
            float(holding["last_price"])
            if holding and holding.get("last_price") is not None
            else None
        )
        if (
            net_value is None
            and holding
            and float(holding.get("shares") or 0) > 0
        ):
            net_value = float(holding.get("holding_value") or 0) / float(
                holding["shares"]
            )
        net_value_item = QTableWidgetItem(
            f"{net_value:.4f}" if net_value is not None else ""
        )
        net_value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 5, net_value_item)

        numeric_fields = {
            6: holding["shares"] if holding else 0.0,
            7: holding["holding_value"] if holding else 0.0,
            8: holding["holding_profit"] if holding else 0.0,
            9: holding["cumulative_profit"] if holding else 0.0,
            11: holding["cost_basis"] if holding else 0.0,
            12: holding["invest_plan"] if holding else 0.0,
        }
        for col, value in numeric_fields.items():
            numeric_item = QTableWidgetItem(
                _format_decimal(value, 4 if col == 6 else 2)
            )
            numeric_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, col, numeric_item)

        rate = holding["cumulative_profit"] / holding["holding_value"] if holding and holding["holding_value"] else 0.0
        rate_item = QTableWidgetItem(pct(rate) if holding else "")
        rate_item.setFlags(rate_item.flags() & ~Qt.ItemIsEditable)
        rate_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 10, rate_item)

        time_combo = QComboBox()
        time_combo.setEditable(True)
        time_combo.addItems(INVEST_TIMES)
        time_combo.setCurrentText(holding["invest_time"] if holding else "")
        self.table.setCellWidget(row, 13, time_combo)

        time_item = QTableWidgetItem(holding["price_time"] if holding else "")
        time_item.setFlags(time_item.flags() & ~Qt.ItemIsEditable)
        time_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 14, time_item)

    def _reload_table(self) -> None:
        holdings = repository.list_holdings(self.conn)
        category = self.filter_combo.currentText()
        account_id = (
            self.account_combo.currentData()
            if self.account_combo.count()
            else None
        )
        asset_label = self.asset_combo.currentText()
        asset_value = dict(ASSET_TYPES).get(asset_label, "")
        filtered = [
            h
            for h in holdings
            if category in ("全部", h["category"])
            and (account_id is None or h.get("account_id") == account_id)
            and (not asset_value or h.get("asset_type") == asset_value)
        ]
        self._rows = []
        self._row_ids = []
        self.table.setRowCount(0)
        for holding in filtered:
            self._append_row(holding)
        self.table.setMinimumHeight(max(8, len(filtered)) * 32 + 34)
        self.table.resizeColumnsToContents()

    def _add_row(self) -> None:
        if not account_service.get_accounts(self.conn):
            QMessageBox.information(
                self,
                "提示",
                "请先在“账户管理”创建一个账户，再添加持仓。",
            )
            return
        self._append_row()
        self.table.setCurrentCell(self.table.rowCount() - 1, 2)

    def _delete_row(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._row_ids):
            QMessageBox.information(self, "提示", "请先选择要删除的行")
            return
        name = self.table.item(row, 2).text().strip() or "未命名持仓"
        if not confirm_delete(self, "删除持仓", f"确定删除“{name}”？"):
            return
        holding_id = self._row_ids[row]
        if holding_id is not None:
            holding = self._rows[row]
            repository.delete_holding(self.conn, holding_id)
            self._deleted_holdings.append(dict(holding))
            self.conn.commit()
        self._rows.pop(row)
        self._row_ids.pop(row)
        self.table.removeRow(row)
        self.refresh()
        self.on_change()

    def _undo_delete(self) -> None:
        if not self._deleted_holdings:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        holding = self._deleted_holdings.pop()
        repository.add_holding(self.conn, holding)
        self.conn.commit()
        self.refresh()
        self.on_change()

    def _save_all(self) -> None:
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 2).text().strip()
            if not name:
                continue
            base = dict(self._rows[row])
            category = self.table.cellWidget(row, 0).currentText().strip()
            channel_combo = self.table.cellWidget(row, 1)
            channel = channel_combo.currentText().strip()
            account_id = channel_combo.currentData()
            symbol = self.table.cellWidget(row, 3).text().strip()
            asset_type = self.table.cellWidget(row, 4).currentData() or self.table.cellWidget(
                row, 4
            ).currentText().strip()
            net_value_text = self.table.item(row, 5).text().strip()
            net_value = float(net_value_text) if net_value_text else None
            shares = _parse_decimal(self.table.item(row, 6).text())
            holding_value = _parse_decimal(self.table.item(row, 7).text())
            holding_profit = _parse_decimal(self.table.item(row, 8).text())
            cumulative_profit = _parse_decimal(self.table.item(row, 9).text())
            cost_basis = _parse_decimal(self.table.item(row, 11).text())
            invest_plan = _parse_decimal(self.table.item(row, 12).text())
            invest_time = self.table.cellWidget(row, 13).currentText().strip()

            update = {
                **base,
                "account_id": account_id,
                "category": category,
                "channel": channel,
                "name": name,
                "symbol": symbol,
                "asset_type": asset_type,
                "last_price": net_value,
                "shares": shares,
                "holding_value": holding_value,
                "holding_profit": holding_profit,
                "cumulative_profit": cumulative_profit,
                "return_rate": cumulative_profit / holding_value if holding_value else 0.0,
                "cost_basis": cost_basis if cost_basis else None,
                "invest_plan": invest_plan,
                "invest_time": invest_time,
            }
            if self._row_ids[row] is None:
                repository.add_holding(self.conn, update)
            else:
                repository.update_holding(self.conn, self._row_ids[row], update)
        self.conn.commit()
        flash_saved(self.save_button)
        self.refresh()
        self.on_change()

    def refresh(self) -> None:
        invest = calculations.investment_summary(self.conn)
        self.summary_label.setText(
            f"总持仓 {money(invest['total_holding'])}  |  "
            f"累计收益 {money(invest['total_cumulative'])}  |  "
            f"总收益率 {pct(invest['total_rate'])}"
        )
        self._reload_accounts()
        self._reload_table()
        self._reload_gold()

    def save(self) -> None:
        """全局保存：根据当前焦点保存持仓列表或黄金账户。"""
        focus = QApplication.focusWidget()
        if _widget_in_table(focus, self.gold_table):
            self._save_gold()
        else:
            self._save_all()

    def undo(self) -> None:
        """全局撤销：优先恢复最近删除的黄金账户，其次恢复持仓。"""
        if self._deleted_gold:
            self._undo_gold_delete()
        elif self._deleted_holdings:
            self._undo_delete()

    def shutdown(self) -> None:
        """退出前停止后台行情刷新，避免线程在进程退出时仍运行。"""
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            self._refresh_worker.cancel()
            self._refresh_worker.wait(5000)

    def _reload_gold(self) -> None:
        accounts = repository.list_gold_accounts(self.conn)
        account_id = (
            self.account_combo.currentData()
            if self.account_combo.count()
            else None
        )
        if account_id is not None:
            accounts = [
                a for a in accounts if a.get("account_id") == account_id
            ]
        self._gold_rows = []
        self._gold_ids = []
        self.gold_table.setRowCount(0)
        for account in accounts:
            self._append_gold_row(account)
        self.gold_table.setMinimumHeight(max(4, len(accounts)) * 32 + 34)
        self.gold_table.resizeColumnsToContents()

    def _append_gold_row(self, account: dict | None = None) -> None:
        row = self.gold_table.rowCount()
        self.gold_table.insertRow(row)
        self._gold_rows.append(dict(account) if account else {})
        self._gold_ids.append(account["id"] if account else None)

        name_item = QTableWidgetItem(account["name"] if account else "")
        self.gold_table.setItem(row, 0, name_item)
        channel_combo = QComboBox()
        for item in account_service.get_accounts(self.conn):
            channel_combo.addItem(item["name"], item["id"])
        if account:
            if account.get("account_id"):
                index = channel_combo.findData(account["account_id"])
                channel_combo.setCurrentIndex(max(0, index))
            else:
                channel_combo.setCurrentText(account.get("channel") or "")
        self.gold_table.setCellWidget(row, 1, channel_combo)

        grams_item = QTableWidgetItem(
            f"{float(account['grams'] or 0.0):.4f}" if account else ""
        )
        grams_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.gold_table.setItem(row, 2, grams_item)

        price_item = QTableWidgetItem(
            f"{float(account['last_price']):.2f}" if account and account["last_price"] else ""
        )
        price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.gold_table.setItem(row, 3, price_item)
        value_item = QTableWidgetItem("")
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.gold_table.setItem(row, 4, value_item)

        cost_item = QTableWidgetItem(
            f"{float(account['cost_basis'] or 0.0):.2f}" if account else ""
        )
        cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.gold_table.setItem(row, 5, cost_item)

        profit_item = QTableWidgetItem("")
        profit_item.setFlags(profit_item.flags() & ~Qt.ItemIsEditable)
        profit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.gold_table.setItem(row, 6, profit_item)
        note_item = QTableWidgetItem(account["note"] if account else "")
        self.gold_table.setItem(row, 7, note_item)
        self._update_gold_row(row)

    def _update_gold_row(self, row: int) -> None:
        grams = _parse_decimal(self.gold_table.item(row, 2).text())
        price_text = self.gold_table.item(row, 3).text().strip()
        try:
            price = float(price_text)
        except ValueError:
            price = 0.0
        cost = _parse_decimal(self.gold_table.item(row, 5).text())
        value = grams * price
        self.gold_table.item(row, 4).setText(money(value))
        self.gold_table.item(row, 6).setText(money(value - cost))

    def _add_gold_row(self) -> None:
        self._append_gold_row()
        self.gold_table.setCurrentCell(self.gold_table.rowCount() - 1, 0)

    def _delete_gold_row(self) -> None:
        row = self.gold_table.currentRow()
        if row < 0 or row >= len(self._gold_ids):
            QMessageBox.information(self, "提示", "请先选择要删除的黄金账户")
            return
        name = self.gold_table.item(row, 0).text().strip() or "未命名黄金账户"
        if not confirm_delete(self, "删除黄金账户", f"确定删除“{name}”？"):
            return
        account_id = self._gold_ids[row]
        if account_id is not None:
            self._deleted_gold.append(dict(self._gold_rows[row]))
            repository.delete_gold_account(self.conn, account_id)
            self.conn.commit()
        self._gold_rows.pop(row)
        self._gold_ids.pop(row)
        self.gold_table.removeRow(row)

    def _undo_gold_delete(self) -> None:
        if not self._deleted_gold:
            QMessageBox.information(self, "提示", "没有可撤销的删除")
            return
        repository.add_gold_account(self.conn, self._deleted_gold.pop())
        self.conn.commit()
        self._reload_gold()

    def _save_gold(self) -> None:
        for row in range(self.gold_table.rowCount()):
            name = self.gold_table.item(row, 0).text().strip()
            if not name:
                continue
            update = dict(self._gold_rows[row])
            update.update(
                {
                    "name": name,
                    "account_id": self.gold_table.cellWidget(
                        row, 1
                    ).currentData(),
                    "channel": self.gold_table.cellWidget(
                        row, 1
                    ).currentText().strip(),
                    "grams": _parse_decimal(self.gold_table.item(row, 2).text()),
                    "last_price": (
                        float(self.gold_table.item(row, 3).text().strip())
                        if self.gold_table.item(row, 3).text().strip()
                        else None
                    ),
                    "cost_basis": _parse_decimal(self.gold_table.item(row, 5).text()),
                    "note": self.gold_table.item(row, 7).text().strip(),
                }
            )
            if self._gold_ids[row] is None:
                repository.add_gold_account(self.conn, update)
            else:
                repository.update_gold_account(self.conn, self._gold_ids[row], update)
        self.conn.commit()
        flash_saved(self.gold_save_button)
        self._reload_gold()

    def _market_client(self, silent: bool = False) -> MarketClient | None:
        api_key = repository.get_setting(self.conn, "hithink_api_key", "")
        if not api_key:
            if not silent:
                QMessageBox.information(
                    self,
                    "需要 API Key",
                    "请先在“设置”中填写同花顺 API Key，"
                    "再到 https://fuyao.aicubes.cn/admin 获取。",
                )
            return None
        return MarketClient(api_key)

    def _resolve_symbol(self) -> None:
        client = self._market_client()
        if client is None:
            return
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一行持仓")
            return
        name = self.table.item(row, 2).text().strip()
        if not name:
            QMessageBox.information(self, "提示", "请先填写名称")
            return
        asset_type = self.table.cellWidget(row, 4).currentData() or ""
        search_type = {
            "stock": "a-share",
            "fund_exchange": "fund-etf,fund-lof",
            "fund_otc": "fund-otc",
            "gold_etf": "fund-etf",
        }.get(asset_type, "")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            candidates = client.search_ticker(name, search_type)
        except MarketError as exc:
            QMessageBox.warning(self, "解析失败", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not candidates:
            try:
                fallback = search_fund(name)
            except EastMoneyError as exc:
                QMessageBox.warning(self, "解析失败", str(exc))
                return
            if fallback:
                code = fallback[0]["code"]
                self.table.cellWidget(row, 3).setText(code)
                index = self.table.cellWidget(row, 4).findData("fund_otc")
                self.table.cellWidget(row, 4).setCurrentIndex(index)
                QMessageBox.information(
                    self,
                    "解析成功",
                    f"{fallback[0]['name']}：{code}（东财兜底）",
                )
                return
            QMessageBox.information(self, "未找到", "没有匹配的代码，请手动填写")
            return
        if len(candidates) == 1:
            candidate = candidates[0]
            self.table.cellWidget(row, 3).setText(
                candidate.get("thscode", "")
            )
            mapped = _asset_type_from_candidate(candidate.get("asset_type", ""))
            if mapped:
                index = self.table.cellWidget(row, 4).findData(mapped)
                if index >= 0:
                    self.table.cellWidget(row, 4).setCurrentIndex(index)
            QMessageBox.information(
                self,
                "解析成功",
                f"{candidate.get('name')}：{candidate.get('thscode')}",
            )
            return
        lines = "\n".join(
            f"{item.get('name')}  {item.get('thscode')}  {item.get('asset_type')}"
            for item in candidates[:10]
        )
        QMessageBox.information(self, "请手动选择", "匹配到多个代码：\n" + lines)

    def _auto_fill_symbol(self, row: int) -> None:
        """按代码自动填充名称、资产类型与净值（回车触发）。"""
        client = self._market_client()
        if client is None:
            return
        symbol = self.table.cellWidget(row, 3).text().strip()
        if not symbol:
            QMessageBox.information(self, "提示", "请先填写代码")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            candidates = client.search_ticker(symbol)
        except MarketError as exc:
            QMessageBox.warning(self, "自动填充失败", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not candidates:
            QMessageBox.information(
                self,
                "未找到",
                f"未找到代码 {symbol} 的行情信息，请检查代码格式。",
            )
            return
        candidate = candidates[0]
        name = str(candidate.get("name") or "")
        thscode = str(candidate.get("thscode") or symbol)
        asset_type = _asset_type_from_candidate(
            str(candidate.get("asset_type") or "")
        )
        if name:
            self.table.item(row, 2).setText(name)
        self.table.cellWidget(row, 3).setText(thscode)
        if asset_type:
            index = self.table.cellWidget(row, 4).findData(asset_type)
            if index >= 0:
                self.table.cellWidget(row, 4).setCurrentIndex(index)
        else:
            asset_type = (
                self.table.cellWidget(row, 4).currentData()
                or {
                    "股票": "stock",
                    "黄金": "gold_etf",
                    "基金": "fund_exchange",
                }.get(self.table.cellWidget(row, 0).currentText(), "")
            )
        try:
            price, _ = fetch_live_price(client, asset_type, thscode)
        except MarketError as exc:
            QMessageBox.information(
                self,
                "已填充基础信息",
                f"名称/类型已自动填充，但净值获取失败：{exc}",
            )
            return
        self.table.item(row, 5).setText(f"{price:.4f}")
        QMessageBox.information(
            self,
            "自动填充完成",
            f"{name or thscode}：净值 {money(price)}",
        )

    def _refresh_market(self, show_popup: bool = True) -> None:
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            if show_popup:
                QMessageBox.information(self, "提示", "正在刷新行情，请稍候")
            return
        api_key = repository.get_setting(
            self.conn, "hithink_api_key", ""
        ).strip()
        self.summary_label.setText("正在后台刷新实时行情…")
        worker = MarketRefreshWorker(str(db_path()), api_key, self)
        worker.finished.connect(
            lambda result: self._on_market_refreshed(result, show_popup)
        )
        self._refresh_worker = worker
        worker.start()

    def _on_market_refreshed(self, result: dict, show_popup: bool) -> None:
        self._refresh_worker = None
        gold_price = result.get("gold_price")
        if gold_price:
            self._gold_reference_price = float(gold_price)
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.gold_price_label.setText(
                f"实时金价：{money(float(gold_price))} 元/克"
                f"（{result.get('gold_date') or now}）"
            )
        editing = (
            self.table.state() == QAbstractItemView.EditingState
            or self.gold_table.state() == QAbstractItemView.EditingState
        )
        if not editing:
            self._reload_table()
            self._reload_gold()
        invest = calculations.investment_summary(self.conn)
        self.summary_label.setText(
            f"总持仓 {money(invest['total_holding'])}  |  "
            f"累计收益 {money(invest['total_cumulative'])}  |  "
            f"总收益率 {pct(invest['total_rate'])}"
        )
        if show_popup:
            updated = int(result.get("updated") or 0)
            failed = result.get("failed") or []
            executed = result.get("executed") or []
            message = f"刷新完成：成功 {updated} 条"
            if executed:
                message += "\n今日定投：" + "、".join(executed)
            if failed:
                message += "\n\n失败：\n" + "\n".join(failed[:10])
            QMessageBox.information(self, "实时行情", message)

    def _show_history(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._row_ids) or self._row_ids[row] is None:
            QMessageBox.information(self, "提示", "请先选择一行已保存的持仓")
            return
        dialog = HoldingTransactionDialog(
            self.conn, self._row_ids[row], self.refresh, self
        )
        dialog.exec()

def _widget_in_table(widget, table) -> bool:
    current = widget
    while current is not None:
        if current is table:
            return True
        current = current.parentWidget()
    return False


def _format_decimal(value, decimals: int = 2) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.{decimals}f}"


def _parse_decimal(text: str) -> float:
    text = (text or "").strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _asset_type_from_candidate(asset_type: str) -> str:
    if asset_type == "a-share":
        return "stock"
    if asset_type in ("fund-etf", "fund-lof"):
        return "fund_exchange"
    if asset_type in ("fund-otc", "fund-reits"):
        return "fund_otc"
    return ""


class HoldingTransactionDialog(QDialog):
    """持仓交易历史：买入/卖出/分红/定投/赎回。"""

    def __init__(self, conn, holding_id: int, on_changed, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.holding_id = holding_id
        self.on_changed = on_changed
        self._ids: list[int] = []
        self.setWindowTitle("持仓交易历史")
        self.resize(760, 480)
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.add_buy = make_button("买入/定投", primary=True)
        self.add_sell = make_button("卖出/赎回")
        self.add_dividend = make_button("分红")
        self.delete_button = make_button("删除")
        self.add_buy.clicked.connect(lambda: self._add("buy"))
        self.add_sell.clicked.connect(lambda: self._add("sell"))
        self.add_dividend.clicked.connect(lambda: self._add("dividend"))
        self.delete_button.clicked.connect(self._delete)
        for button in (self.add_buy, self.add_sell, self.add_dividend, self.delete_button):
            top.addWidget(button)
        top.addStretch(1)
        layout.addLayout(top)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["日期", "类型", "份额", "价格", "金额", "手续费", "备注"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("summaryValue")
        layout.addWidget(self.summary_label)
        self._reload()

    def _reload(self) -> None:
        rows = investing.get_holding_transactions(self.conn, self.holding_id)
        self._ids = [row["id"] for row in rows]
        self.table.setRowCount(len(rows))
        type_names = {
            "buy": "买入", "sell": "卖出", "dividend": "分红",
            "subscription": "定投", "redemption": "赎回",
        }
        for r, row in enumerate(rows):
            values = [
                row["trans_date"],
                type_names.get(row["trans_type"], row["trans_type"]),
                f"{float(row['shares'] or 0):.4f}",
                f"{float(row['price'] or 0):.4f}",
                f"{float(row['amount'] or 0):.2f}",
                f"{float(row['fee'] or 0):.2f}",
                row["note"],
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)
        holding = None
        for item in repository.list_holdings(self.conn):
            if item["id"] == self.holding_id:
                holding = item
                break
        if holding:
            value = float(holding.get("holding_value") or 0)
            cost = float(holding.get("cost_basis") or 0)
            profit = float(holding.get("cumulative_profit") or 0)
            self.summary_label.setText(
                f"总市值 {money(value)}  总成本 {money(cost)}  "
                f"累计收益 {money(profit)}  XIRR/简单收益率 {pct(investing.calculate_xirr(self.conn, self.holding_id))}"
            )

    def _add(self, trans_type: str) -> None:
        dialog = HoldingTradeDialog(self.conn, self.holding_id, trans_type, self)
        if dialog.exec() != QDialog.Accepted:
            return
        investing.add_holding_transaction(self.conn, self.holding_id, **dialog.values())
        self.conn.commit()
        self._reload()
        self.on_changed()

    def _delete(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            return
        if not confirm_delete(self, "删除交易", "确定删除选中的持仓交易？"):
            return
        investing.delete_holding_transaction(self.conn, self._ids[row])
        self.conn.commit()
        self._reload()
        self.on_changed()


class HoldingTradeDialog(QDialog):
    def __init__(self, conn, holding_id, trans_type, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.holding_id = holding_id
        self.setWindowTitle("新增持仓交易")
        self.setMinimumWidth(360)
        layout = QGridLayout(self)
        self.type_combo = QComboBox()
        for label, value in [
            ("买入", "buy"), ("卖出", "sell"), ("分红", "dividend"),
            ("定投", "subscription"), ("赎回", "redemption"),
        ]:
            self.type_combo.addItem(label, value)
        index = self.type_combo.findData(trans_type)
        self.type_combo.setCurrentIndex(max(0, index))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.shares_spin = QDoubleSpinBox()
        self.shares_spin.setDecimals(4)
        self.shares_spin.setRange(0, 1e9)
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setDecimals(4)
        self.price_spin.setRange(0, 1e9)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setDecimals(2)
        self.amount_spin.setRange(0, 1e9)
        self.fee_spin = QDoubleSpinBox()
        self.fee_spin.setDecimals(2)
        self.fee_spin.setRange(0, 1e9)
        self.note_edit = QLineEdit()
        fields = [
            ("类型", self.type_combo),
            ("日期", self.date_edit),
            ("份额", self.shares_spin),
            ("价格", self.price_spin),
            ("金额", self.amount_spin),
            ("手续费", self.fee_spin),
            ("备注", self.note_edit),
        ]
        for row, (title, widget) in enumerate(fields):
            label = QLabel(title)
            label.setObjectName("fieldLabel")
            layout.addWidget(label, row, 0)
            layout.addWidget(widget, row, 1)
        buttons = QHBoxLayout()
        ok = make_button("确定", primary=True)
        cancel = make_button("取消")
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons, len(fields), 0, 1, 2)

    def _accept(self) -> None:
        if self.amount_spin.value() <= 0:
            self.amount_spin.setValue(round(self.shares_spin.value() * self.price_spin.value(), 2))
        if self.amount_spin.value() <= 0:
            QMessageBox.warning(self, "提示", "金额必须大于 0")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "trans_type": self.type_combo.currentData(),
            "trans_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "shares": float(self.shares_spin.value()),
            "price": float(self.price_spin.value()),
            "amount": float(self.amount_spin.value()),
            "fee": float(self.fee_spin.value()),
            "note": self.note_edit.text().strip(),
        }
