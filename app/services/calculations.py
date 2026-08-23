"""汇总与财务指标计算，保持与 gongzi.xlsx 的公式一致。"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..core import repository


def _row_many(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql)]


def year_summary(conn: sqlite3.Connection, year_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
          COALESCE(SUM(salary), 0) AS salary,
          COALESCE(SUM(salary + year_end_bonus + subsidies + reimbursements), 0) AS income,
          COALESCE(SUM(rent + utilities), 0) AS housing_cost,
          COALESCE(SUM(forced_deposit), 0) AS deposits
        FROM monthly_records WHERE year_id = ?
        """,
        (year_id,),
    ).fetchone()
    expenses = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM large_items "
        "WHERE year_id = ? AND item_type = 'expense'",
        (year_id,),
    ).fetchone()[0]
    large_income = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM large_items "
        "WHERE year_id = ? AND item_type = 'income'",
        (year_id,),
    ).fetchone()[0]

    salary = float(row["salary"])
    income = float(row["income"])
    housing_cost = float(row["housing_cost"])
    deposits = float(row["deposits"])
    balance = income + housing_cost
    return {
        "salary": salary,
        "income": income,
        "housing_cost": housing_cost,
        "balance": balance,
        "deposits": deposits,
        "savings_rate": deposits / income if income else 0.0,
        "large_expenses": float(expenses),
        "large_income": float(large_income),
    }


def totals(conn: sqlite3.Connection) -> dict[str, float]:
    wages, income, deposits = conn.execute(
        """
        SELECT
          COALESCE(SUM(salary), 0),
          COALESCE(SUM(salary + year_end_bonus + subsidies + reimbursements), 0),
          COALESCE(SUM(forced_deposit), 0)
        FROM monthly_records
        """
    ).fetchone()
    return {
        "wages": float(wages),
        "income": float(income),
        "deposits": float(deposits),
    }


def investment_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _row_many(
        conn,
        """
        SELECT category,
               COALESCE(SUM(holding_value), 0) AS holding,
               COALESCE(SUM(holding_profit), 0) AS holding_profit,
               COALESCE(SUM(cumulative_profit), 0) AS cumulative
        FROM holdings GROUP BY category
        """,
    )
    categories = {"基金": {}, "黄金": {}, "黄金账户": {}, "股票": {}}
    total_holding = total_profit = total_cumulative = 0.0
    for row in rows:
        categories[row["category"]] = {
            "holding": row["holding"],
            "holding_profit": row["holding_profit"],
            "cumulative": row["cumulative"],
            "rate": row["cumulative"] / row["holding"] if row["holding"] else 0.0,
        }
        total_holding += row["holding"]
        total_profit += row["holding_profit"]
        total_cumulative += row["cumulative"]
    gold_holding = 0.0
    gold_profit = 0.0
    for account in repository.list_gold_accounts(conn):
        price = account.get("last_price")
        grams = float(account.get("grams") or 0)
        cost = float(account.get("cost_basis") or 0)
        value = grams * float(price) if price else cost
        gold_holding += value
        gold_profit += value - cost
    categories["黄金账户"] = {
        "holding": gold_holding,
        "holding_profit": gold_profit,
        "cumulative": gold_profit,
        "rate": gold_profit / gold_holding if gold_holding else 0.0,
    }
    total_holding += gold_holding
    total_profit += gold_profit
    total_cumulative += gold_profit
    return {
        "categories": categories,
        "total_holding": total_holding,
        "total_holding_profit": total_profit,
        "total_cumulative": total_cumulative,
        "total_rate": total_cumulative / total_holding if total_holding else 0.0,
    }


def social_insurance_from_data(
    p: dict[str, Any], items: list[dict[str, Any]]
) -> dict[str, Any]:
    monthly = float(p.get("monthly_salary") or 0)
    thirteenth_amount = float(p.get("thirteenth_amount") or monthly)
    year_bonus_amount = float(p.get("year_end_bonus_amount") or monthly)
    thirteenth_months = float(p.get("thirteenth_month_months") or 0)
    year_bonus_months = float(p.get("year_end_bonus_months") or 0)
    subsidy = float(p.get("housing_subsidy") or 0)

    detail = []
    personal_total = 0.0
    company_total = 0.0
    for item in items:
        base = float(item.get("base") or 0)
        personal_rate = float(item.get("personal_rate") or 0)
        company_rate = float(item.get("company_rate") or 0)
        personal_fixed = item.get("personal_fixed")
        personal = (
            float(personal_fixed)
            if personal_fixed is not None
            else base * personal_rate
        )
        company = base * company_rate
        personal_total += personal
        company_total += company
        detail.append(
            {
                "name": item.get("name", ""),
                "base": base,
                "personal_rate": personal_rate,
                "company_rate": company_rate,
                "personal_fixed": personal_fixed,
                "personal": personal,
                "company": company,
            }
        )

    gross_income = (
        monthly * 12
        + thirteenth_amount * thirteenth_months
        + year_bonus_amount * year_bonus_months
        + subsidy * 12
        - personal_total * 12
    )
    # 与 Excel 汇总页一致：总包在税前收入基础上再加公司缴纳与租房补贴 12 个月。
    total_package = gross_income + company_total * 12 + subsidy * 12
    return {
        "params": p,
        "items": detail,
        "personal_total": personal_total,
        "company_total": company_total,
        "gross_income": gross_income,
        "total_package": total_package,
    }


def social_insurance(conn: sqlite3.Connection, year_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM social_insurance_params WHERE year_id = ?", (year_id,)
    ).fetchone()
    items = repository.list_insurance_items(conn, year_id)
    if row is None:
        return {"has_params": False, "items": items}
    return {
        "has_params": True,
        **social_insurance_from_data(dict(row), items),
    }
