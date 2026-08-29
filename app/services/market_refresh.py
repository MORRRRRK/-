"""后台行情刷新工作线程，避免网络请求阻塞界面。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from ..core import repository
from .eastmoney import EastMoneyError, search_fund
from .gold import GoldPriceError, fetch_gold_price
from .investing import run_scheduled_investments
from .market import MarketClient, MarketError, fetch_live_price


def _fetch_or_resolve(
    conn: sqlite3.Connection,
    client: MarketClient,
    holding: dict,
) -> tuple[float, str, dict]:
    """拉取行情；失败时尝试修正 6 位基金代码与资产类型后重试。"""
    symbol = (holding.get("symbol") or "").strip()
    asset_type = holding.get("asset_type") or ""
    if not asset_type:
        asset_type = {
            "股票": "stock",
            "黄金": "gold_etf",
            "基金": "fund_exchange",
        }.get(holding.get("category"), "")
    try:
        price, price_time = fetch_live_price(client, asset_type, symbol)
        return price, price_time, holding
    except MarketError:
        name = str(holding.get("name") or "").strip()
        if not symbol or not name:
            raise
        if asset_type in ("stock", "") and symbol.isdigit() and len(symbol) == 6:
            try:
                candidates = search_fund(name)
            except EastMoneyError:
                candidates = []
            if candidates:
                code = candidates[0]["code"]
                update = dict(holding)
                update["symbol"] = code
                update["asset_type"] = "fund_otc"
                repository.update_holding(conn, holding["id"], update)
                resolved = {**holding, "symbol": code, "asset_type": "fund_otc"}
                price, price_time = fetch_live_price(client, "fund_otc", code)
                return price, price_time, resolved
        raise


class MarketRefreshWorker(QThread):
    """在后台线程刷新持仓净值、定投与黄金参考金价。"""

    finished = Signal(object)

    def __init__(self, db_path: str, api_key: str, parent=None):
        super().__init__(parent)
        self._db_path = str(db_path)
        self._api_key = api_key
        self._abort = False

    def cancel(self) -> None:
        self._abort = True

    def run(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            result = self._refresh(conn)
        except Exception as exc:  # 兜底：任何异常都不能让线程崩溃
            result = {
                "updated": 0,
                "failed": [str(exc)],
                "executed": [],
                "gold_price": None,
                "gold_date": "",
            }
        finally:
            try:
                conn.commit()
            except sqlite3.Error:
                pass
            conn.close()
        self.finished.emit(result)

    def _refresh(self, conn: sqlite3.Connection) -> dict:
        client = MarketClient(self._api_key)
        holdings = repository.list_holdings(conn)
        updated = 0
        failed: list[str] = []
        for holding in holdings:
            if self._abort:
                break
            symbol = (holding.get("symbol") or "").strip()
            if not symbol:
                failed.append(f"{holding.get('name')}：未填写代码")
                continue
            asset_type = holding.get("asset_type") or ""
            if not asset_type:
                asset_type = {
                    "股票": "stock",
                    "黄金": "gold_etf",
                    "基金": "fund_exchange",
                }.get(holding.get("category"), "")
            if not asset_type:
                failed.append(f"{holding.get('name')}：未设置资产类型")
                continue
            try:
                price, _, resolved = _fetch_or_resolve(
                    conn, client, holding
                )
            except MarketError as exc:
                failed.append(f"{holding.get('name')}：{exc}")
                continue
            if not price:
                failed.append(f"{holding.get('name')}：接口未返回价格")
                continue
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            update = dict(resolved)
            update["last_price"] = price
            update["price_time"] = now
            shares = float(holding.get("shares") or 0)
            if shares > 0:
                new_value = round(shares * price, 2)
                update["holding_value"] = new_value
                cost = holding.get("cost_basis")
                if cost is not None and float(cost or 0) > 0:
                    update["holding_profit"] = round(
                        new_value - float(cost), 2
                    )
                update["return_rate"] = (
                    float(update.get("cumulative_profit") or 0) / new_value
                    if new_value
                    else 0.0
                )
            repository.update_holding(conn, holding["id"], update)
            updated += 1

        if not self._abort:
            try:
                executed = run_scheduled_investments(conn, client)
            except Exception as exc:
                failed.append(f"定投：{exc}")
                executed = []

            gold_price = None
            gold_date = ""
            try:
                gold_price, gold_date = fetch_gold_price()
            except GoldPriceError as exc:
                failed.append(f"金价：{exc}")
            if gold_price:
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                for account in repository.list_gold_accounts(conn):
                    update = dict(account)
                    update["last_price"] = gold_price
                    update["price_time"] = gold_date or now
                    repository.update_gold_account(conn, account["id"], update)
            conn.commit()
        else:
            executed = []
            gold_price = None
            gold_date = ""
        return {
            "updated": updated,
            "failed": failed,
            "executed": executed,
            "gold_price": gold_price,
            "gold_date": gold_date,
        }
