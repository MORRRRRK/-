"""定投自动执行：按交易日与开市时间联动持仓。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from ..core import repository
from .market import MarketClient, fetch_live_price

WEEKDAYS = {
    "周一": 0,
    "周二": 1,
    "周三": 2,
    "周四": 3,
    "周五": 4,
    "周六": 5,
    "周日": 6,
}


def is_trading_day(client: MarketClient, today: datetime | None = None) -> bool:
    today = today or datetime.now()
    try:
        dates = client.trading_days()
        return today.strftime("%Y%m%d") in dates
    except Exception:
        return today.weekday() < 5


def should_execute_today(invest_time: str, today: datetime | None = None) -> bool:
    today = today or datetime.now()
    text = (invest_time or "").strip()
    if not text or text == "暂停":
        return False
    if "每日" in text:
        return True
    if "每周" in text:
        for name, weekday in WEEKDAYS.items():
            if name in text:
                return today.weekday() == weekday
        return today.weekday() < 5
    if "每月" in text:
        for digit in "123456789":
            if f"{digit}日" in text:
                return today.day == int(digit)
        return today.day <= 28
    return False


def market_has_opened(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    minute = now.hour * 60 + now.minute
    return minute >= 570  # 09:30


def run_scheduled_investments(
    conn: sqlite3.Connection,
    client: MarketClient,
    now: datetime | None = None,
) -> list[str]:
    """按定投设置执行当日定投，返回已执行记录描述。"""
    now = now or datetime.now()
    if not market_has_opened(now) or not is_trading_day(client, now):
        return []
    today = now.strftime("%Y-%m-%d")
    executed = []
    for holding in repository.list_holdings(conn):
        plan = float(holding.get("invest_plan") or 0)
        invest_time = holding.get("invest_time") or ""
        if plan <= 0 or not should_execute_today(invest_time, now):
            continue
        if repository.has_invest_execution(conn, holding["id"], today):
            continue
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
            continue
        try:
            price, _ = fetch_live_price(client, asset_type, symbol)
        except Exception:
            continue
        if not price:
            continue
        update = dict(holding)
        old_shares = float(holding.get("shares") or 0)
        new_shares = old_shares + plan / price
        new_value = round(new_shares * price, 2)
        update["shares"] = new_shares
        update["holding_value"] = new_value
        update["cost_basis"] = float(holding.get("cost_basis") or 0) + plan
        update["holding_profit"] = round(new_value - float(update["cost_basis"]), 2)
        update["last_price"] = price
        update["price_time"] = now.strftime("%Y-%m-%d %H:%M")
        update["return_rate"] = (
            float(update.get("cumulative_profit") or 0) / new_value
            if new_value
            else 0.0
        )
        repository.update_holding(conn, holding["id"], update)
        repository.add_invest_execution(
            conn, holding["id"], today, plan, round(new_shares - old_shares, 6), price
        )
        executed.append(f"{holding['name']} {plan:.2f} 元")
    conn.commit()
    return executed
