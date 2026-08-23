from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QComboBox,
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
from ...services import calculations
from ...services.eastmoney import EastMoneyError, search_fund
from ...services.gold import GoldPriceError, fetch_gold_price
from ...services.investing import run_scheduled_investments
from ...services.market import MarketClient, MarketError, fetch_live_price
from ..widgets import (
    Section,
    confirm_delete,
    flash_saved,
    make_button,
    money,
    pct,
)

ASSET_TYPES = [
    ("股票 (A股)", "stock"),
    ("场内基金 (ETF/LOF)", "fund_exchange"),
    ("场外基金", "fund_otc"),
    ("黄金 ETF", "gold_etf"),
]

CATEGORIES = ["基金", "黄金", "股票"]
INVEST_TIMES = ["每日", "每周一", "每月1日", "暂停"]


class HoldingsPage(QScrollArea):
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
        self.setWidgetResizable(True)
        self._content = QWidget()
        self.setWidget(self._content)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(QLabel("分类筛选"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部"] + CATEGORIES)
        self.filter_combo.currentTextChanged.connect(self._reload_table)
        self.filter_combo.setFixedWidth(100)
        top.addWidget(self.filter_combo)
        top.addWidget(QLabel("渠道筛选"))
        self.channel_combo = QComboBox()
        self.channel_combo.currentTextChanged.connect(self._reload_table)
        self.channel_combo.setMinimumWidth(140)
        top.addWidget(self.channel_combo)
        top.addStretch(1)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("summaryValue")
        top.addWidget(self.summary_label)
        layout.addLayout(top)

        action_row = QHBoxLayout()
        self.add_row_button = make_button("新增持仓")
        self.delete_row_button = make_button("删除选中")
        self.undo_button = make_button("撤销删除")
        self.resolve_button = make_button("按名称解析代码")
        self.refresh_button = make_button("刷新实时行情")
        self.invest_button = make_button("执行今日定投")
        self.save_button = make_button("保存修改", primary=True)
        self.save_button.setMinimumSize(150, 42)
        self.add_row_button.clicked.connect(self._add_row)
        self.delete_row_button.clicked.connect(self._delete_row)
        self.undo_button.clicked.connect(self._undo_delete)
        self.resolve_button.clicked.connect(self._resolve_symbol)
        self.refresh_button.clicked.connect(lambda: self._refresh_market(show_popup=True))
        self.invest_button.clicked.connect(self._run_investments)
        self.save_button.clicked.connect(self._save_all)
        for button in (
            self.add_row_button,
            self.delete_row_button,
            self.undo_button,
            self.resolve_button,
            self.refresh_button,
            self.invest_button,
        ):
            action_row.addWidget(button)
        action_row.addStretch(1)
        action_row.addWidget(self.save_button)
        layout.addLayout(action_row)

        table_section = Section("持仓列表（直接在表格中修改，保存后全部生效）")
        self.table = QTableWidget(0, 14)
        self.table.setHorizontalHeaderLabels(
            [
                "类别", "渠道", "名称", "代码", "资产类型", "份额", "持仓",
                "持有收益", "累计收益", "收益率", "成本", "定投金额", "定投时间",
                "更新时间",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.table.setMinimumHeight(8 * 32 + 34)
        table_section.add(self.table)
        layout.addWidget(table_section)

        gold_section = Section("无代码黄金账户（积存金 / 易存金，按克参考实时金价）")
        gold_top = QHBoxLayout()
        self.gold_refresh_button = make_button("刷新实时金价")
        self.gold_add_button = make_button("新增黄金账户")
        self.gold_delete_button = make_button("删除选中")
        self.gold_undo_button = make_button("撤销删除")
        self.gold_save_button = make_button("保存黄金账户", primary=True)
        self.gold_refresh_button.clicked.connect(
            lambda: self._refresh_gold_prices(show_popup=True)
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
        gold_section.add_layout(gold_top)

        self.gold_table = QTableWidget(0, 8)
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

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self._refresh_market(show_popup=False))
        self.timer.start(60_000)
        self.refresh()

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
        channel_combo.setEditable(True)
        channel_combo.addItems(
            ["支付宝", "中信建投", "银河证券", "中国建设银行", "博时基金", "浙商银行"]
        )
        channel_combo.setCurrentText(holding["channel"] if holding else "")
        self.table.setCellWidget(row, 1, channel_combo)

        name_item = QTableWidgetItem(holding["name"] if holding else "")
        self.table.setItem(row, 2, name_item)
        symbol_item = QTableWidgetItem(holding["symbol"] if holding else "")
        self.table.setItem(row, 3, symbol_item)

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

        numeric_fields = {
            5: holding["shares"] if holding else 0.0,
            6: holding["holding_value"] if holding else 0.0,
            7: holding["holding_profit"] if holding else 0.0,
            8: holding["cumulative_profit"] if holding else 0.0,
            10: holding["cost_basis"] if holding else 0.0,
            11: holding["invest_plan"] if holding else 0.0,
        }
        for col, value in numeric_fields.items():
            numeric_item = QTableWidgetItem(
                _format_decimal(value, 4 if col == 5 else 2)
            )
            numeric_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, col, numeric_item)

        rate = holding["cumulative_profit"] / holding["holding_value"] if holding and holding["holding_value"] else 0.0
        rate_item = QTableWidgetItem(pct(rate) if holding else "")
        rate_item.setFlags(rate_item.flags() & ~Qt.ItemIsEditable)
        rate_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 9, rate_item)

        time_combo = QComboBox()
        time_combo.setEditable(True)
        time_combo.addItems(INVEST_TIMES)
        time_combo.setCurrentText(holding["invest_time"] if holding else "")
        self.table.setCellWidget(row, 12, time_combo)

        time_item = QTableWidgetItem(holding["price_time"] if holding else "")
        time_item.setFlags(time_item.flags() & ~Qt.ItemIsEditable)
        time_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 13, time_item)

    def _reload_table(self) -> None:
        holdings = repository.list_holdings(self.conn)
        category = self.filter_combo.currentText()
        channel = self.channel_combo.currentText()
        filtered = [
            h
            for h in holdings
            if category in ("全部", h["category"])
            and (channel in ("全部渠道", h["channel"]))
        ]
        self._rows = []
        self._row_ids = []
        self.table.setRowCount(0)
        for holding in filtered:
            self._append_row(holding)
        self.table.setMinimumHeight(max(8, len(filtered)) * 32 + 34)
        self.table.resizeColumnsToContents()

    def _add_row(self) -> None:
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
            channel = self.table.cellWidget(row, 1).currentText().strip()
            symbol = self.table.item(row, 3).text().strip()
            asset_type = self.table.cellWidget(row, 4).currentData() or self.table.cellWidget(
                row, 4
            ).currentText().strip()
            shares = _parse_decimal(self.table.item(row, 5).text())
            holding_value = _parse_decimal(self.table.item(row, 6).text())
            holding_profit = _parse_decimal(self.table.item(row, 7).text())
            cumulative_profit = _parse_decimal(self.table.item(row, 8).text())
            cost_basis = _parse_decimal(self.table.item(row, 10).text())
            invest_plan = _parse_decimal(self.table.item(row, 11).text())
            invest_time = self.table.cellWidget(row, 12).currentText().strip()

            update = {
                **base,
                "category": category,
                "channel": channel,
                "name": name,
                "symbol": symbol,
                "asset_type": asset_type,
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
        current = self.channel_combo.currentText()
        channels = sorted(
            {h["channel"] for h in repository.list_holdings(self.conn) if h["channel"]}
        )
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self.channel_combo.addItem("全部渠道")
        self.channel_combo.addItems(channels)
        index = self.channel_combo.findText(current)
        self.channel_combo.setCurrentIndex(max(0, index))
        self.channel_combo.blockSignals(False)
        self._reload_table()
        self._reload_gold()

    def _reload_gold(self) -> None:
        accounts = repository.list_gold_accounts(self.conn)
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
        channel_item = QTableWidgetItem(account["channel"] if account else "")
        self.gold_table.setItem(row, 1, channel_item)

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
                    "channel": self.gold_table.item(row, 1).text().strip(),
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

    def _refresh_gold_prices(self, show_popup: bool = True) -> None:
        try:
            price, date_text = fetch_gold_price()
        except GoldPriceError as exc:
            if show_popup:
                QMessageBox.warning(self, "金价刷新失败", str(exc))
            return
        self._gold_reference_price = price
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.gold_price_label.setText(
            f"实时金价：{money(price)} 元/克（{date_text or now}）"
        )
        for account in repository.list_gold_accounts(self.conn):
            update = dict(account)
            update["last_price"] = price
            update["price_time"] = date_text or now
            repository.update_gold_account(self.conn, account["id"], update)
        self.conn.commit()
        self._reload_gold()
        if show_popup:
            QMessageBox.information(
                self, "金价刷新完成", f"实时金价：{money(price)} 元/克"
            )

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
            if asset_type == "fund_otc":
                try:
                    fallback = search_fund(name)
                except EastMoneyError as exc:
                    QMessageBox.warning(self, "解析失败", str(exc))
                    return
                if fallback:
                    code = fallback[0]["code"]
                    self.table.item(row, 3).setText(code)
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
            self.table.item(row, 3).setText(candidate.get("thscode", ""))
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

    def _refresh_market(self, show_popup: bool = True) -> None:
        client = self._market_client(silent=not show_popup)
        if client is None:
            return
        holdings = repository.list_holdings(self.conn)
        updated = 0
        failed = []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for holding in holdings:
                symbol = (holding.get("symbol") or "").strip()
                if not symbol:
                    continue
                asset_type = holding.get("asset_type") or ""
                if not asset_type:
                    asset_type = {
                        "股票": "stock",
                        "黄金": "gold_etf",
                        "基金": "fund_exchange",
                    }.get(holding.get("category"), "")
                if not asset_type:
                    failed.append(f"{holding['name']}：未设置资产类型")
                    continue
                try:
                    price, price_time = fetch_live_price(client, asset_type, symbol)
                except MarketError as exc:
                    failed.append(f"{holding['name']}：{exc}")
                    continue
                if not price:
                    failed.append(f"{holding['name']}：接口未返回价格")
                    continue
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                update = dict(holding)
                update["last_price"] = price
                update["price_time"] = price_time or now
                shares = float(holding.get("shares") or 0)
                if shares > 0:
                    new_value = round(shares * price, 2)
                    update["holding_value"] = new_value
                    cost = holding.get("cost_basis")
                    if cost is not None and float(cost or 0) > 0:
                        update["holding_profit"] = round(new_value - float(cost), 2)
                    update["return_rate"] = (
                        float(update.get("cumulative_profit") or 0) / new_value
                        if new_value
                        else 0.0
                    )
                repository.update_holding(self.conn, holding["id"], update)
                updated += 1
            try:
                executed = run_scheduled_investments(self.conn, client)
            except Exception as exc:
                failed.append(f"定投：{exc}")
                executed = []
            self._refresh_gold_prices(show_popup=False)
        finally:
            QApplication.restoreOverrideCursor()
        self.conn.commit()
        self.refresh()
        self.on_change()
        if show_popup:
            message = f"刷新完成：成功 {updated} 条"
            if executed:
                message += "\n今日定投：" + "、".join(executed)
            if failed:
                message += "\n\n失败：\n" + "\n".join(failed[:10])
            QMessageBox.information(self, "实时行情", message)

    def _run_investments(self) -> None:
        client = self._market_client()
        if client is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            executed = run_scheduled_investments(self.conn, client)
        except Exception as exc:
            QMessageBox.warning(self, "定投失败", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh()
        self.on_change()
        QMessageBox.information(
            self, "定投结果", "今日定投：" + ("、".join(executed) if executed else "无")
        )


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
