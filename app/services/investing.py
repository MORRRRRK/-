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


def get_holding_transactions(
    conn: sqlite3.Connection,
    holding_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """获取某持仓的交易历史。"""
    sql = "SELECT * FROM holding_transactions WHERE holding_id = ?"
    params: list = [holding_id]
    if start_date:
        sql += " AND trans_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND trans_date <= ?"
        params.append(end_date)
    sql += " ORDER BY trans_date, id"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _recalc_holding(conn: sqlite3.Connection, holding_id: int) -> None:
    holding = None
    for item in repository.list_holdings(conn):
        if item["id"] == holding_id:
            holding = item
            break
    if not holding:
        return
    transactions = get_holding_transactions(conn, holding_id)
    shares = 0.0
    cost = 0.0
    cumulative = float(holding.get("cumulative_profit") or 0)
    for trans in transactions:
        ttype = trans["trans_type"]
        amount = float(trans["amount"] or 0)
        fee = float(trans["fee"] or 0)
        if ttype in ("buy", "subscription"):
            shares += float(trans["shares"] or 0)
            cost += amount + fee
        elif ttype in ("sell", "redemption"):
            sell_cost = calculate_fifo_cost(conn, holding_id, float(trans["shares"] or 0))
            shares = max(0.0, shares - float(trans["shares"] or 0))
            cost = max(0.0, cost - sell_cost)
            cumulative += amount - fee - sell_cost
        elif ttype == "dividend":
            cumulative += amount
    price = float(holding.get("last_price") or 0)
    value = round(shares * price, 2) if price else float(holding.get("holding_value") or 0)
    update = dict(holding)
    update["shares"] = shares
    update["cost_basis"] = cost
    update["holding_value"] = value
    update["holding_profit"] = round(value - cost, 2)
    update["cumulative_profit"] = cumulative
    update["return_rate"] = cumulative / value if value else 0.0
    repository.update_holding(conn, holding_id, update)


def add_holding_transaction(
    conn: sqlite3.Connection,
    holding_id: int,
    trans_type: str,
    trans_date: str,
    shares: float = 0.0,
    price: float = 0.0,
    amount: float | None = None,
    fee: float = 0.0,
    note: str = "",
) -> int:
    """新增持仓交易：买入/卖出/分红/定投/赎回，并重算持仓。"""
    amount = amount if amount is not None else round(shares * price, 2)
    cur = conn.execute(
        """
        INSERT INTO holding_transactions(
          holding_id, trans_type, trans_date, shares, price, amount, fee, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (holding_id, trans_type, trans_date, shares, price, amount, fee, note),
    )
    trans_id = int(cur.lastrowid)
    _recalc_holding(conn, holding_id)
    return trans_id


def delete_holding_transaction(
    conn: sqlite3.Connection, transaction_id: int
) -> None:
    """删除持仓交易并重算持仓。"""
    row = conn.execute(
        "SELECT holding_id FROM holding_transactions WHERE id = ?", (transaction_id,)
    ).fetchone()
    if not row:
        return
    conn.execute("DELETE FROM holding_transactions WHERE id = ?", (transaction_id,))
    _recalc_holding(conn, row["holding_id"])


def calculate_fifo_cost(
    conn: sqlite3.Connection, holding_id: int, sell_shares: float
) -> float:
    """FIFO 卖出成本。"""
    remaining = float(sell_shares)
    total_cost = 0.0
    rows = conn.execute(
        """
        SELECT shares, amount, fee FROM holding_transactions
        WHERE holding_id = ? AND trans_type IN ('buy', 'subscription')
        ORDER BY trans_date, id
        """,
        (holding_id,),
    ).fetchall()
    for row in rows:
        if remaining <= 0:
            break
        batch_shares = float(row["shares"] or 0)
        if batch_shares <= 0:
            continue
        take = min(batch_shares, remaining)
        unit_cost = (float(row["amount"] or 0) + float(row["fee"] or 0)) / batch_shares
        total_cost += take * unit_cost
        remaining -= take
    return total_cost


def calculate_xirr(conn: sqlite3.Connection, holding_id: int) -> float:
    """简化收益率：有交易历史时用累计收益/总成本，保留 XIRR 接口。"""
    holding = None
    for item in repository.list_holdings(conn):
        if item["id"] == holding_id:
            holding = item
            break
    if not holding:
        return 0.0
    cost = float(holding.get("cost_basis") or 0)
    cumulative = float(holding.get("cumulative_profit") or 0)
    return cumulative / cost if cost else 0.0


def get_portfolio_summary(conn: sqlite3.Connection) -> dict:
    """投资组合汇总：总市值、总成本、总收益、总收益率、类别占比。"""
    from . import calculations

    result = calculations.investment_summary(conn)
    return {
        "total_value": result["total_holding"],
        "total_cost": sum(
            float(h.get("cost_basis") or 0)
            for h in repository.list_holdings(conn)
        ),
        "total_profit": result["total_cumulative"],
        "total_rate": result["total_rate"],
        "categories": result["categories"],
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
