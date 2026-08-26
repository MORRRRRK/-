"""汇总与财务指标计算，保持与 gongzi.xlsx 的公式一致。"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..core import repository


def _row_many(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql)]


def year_summary(conn: sqlite3.Connection, year_id: int) -> dict[str, Any]:
    year_row = conn.execute(
        "SELECT year FROM years WHERE id = ?", (year_id,)
    ).fetchone()
    year = int(year_row["year"]) if year_row else 0
    trans_count = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE trans_date LIKE ?",
        (f"{year}%",),
    ).fetchone()[0]
    has_transactions = trans_count > 0
    if has_transactions:
        trans_rows = conn.execute(
            """
            SELECT type, amount FROM transactions
            WHERE trans_date LIKE ?
            """,
            (f"{year}%",),
        ).fetchall()
        trans_income = sum(
            float(r["amount"] or 0) for r in trans_rows if r["type"] == "income"
        )
        trans_expense = sum(
            float(r["amount"] or 0) for r in trans_rows if r["type"] == "expense"
        )
    row = conn.execute(
        """
        SELECT
          COALESCE(SUM(salary), 0) AS salary,
          COALESCE(SUM(salary + year_end_bonus + subsidies + reimbursements), 0) AS income,
          COALESCE(SUM(rent), 0) AS housing_cost,
          COALESCE(SUM(monthly_expense), 0) AS monthly_expense,
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
    monthly_expense = float(row["monthly_expense"])
    deposits = float(row["deposits"])
    if has_transactions:
        income = trans_income
        monthly_expense = trans_expense
        balance = trans_income - trans_expense
    else:
        balance = income + housing_cost
    return {
        "salary": salary,
        "income": income,
        "housing_cost": housing_cost,
        "monthly_expense": monthly_expense,
        "avg_monthly_expense": monthly_expense / 12.0,
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
    p: dict[str, Any],
    items: list[dict[str, Any]],
    salary_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    monthly = float(p.get("monthly_salary") or 0)
    salary_items = salary_items or []
    base_annual = monthly * 12
    thirteen_coefficient = float(p.get("thirteenth_coefficient") or 1.0)
    thirteen_frequency = str(p.get("thirteenth_frequency") or "annual")
    bonus_coefficient = float(p.get("year_end_bonus_coefficient") or 1.0)
    bonus_frequency = str(p.get("year_end_bonus_frequency") or "annual")
    thirteen_annual = (
        monthly
        * thirteen_coefficient
        * _frequency_factor(thirteen_frequency)
    )
    bonus_annual = (
        monthly
        * bonus_coefficient
        * _frequency_factor(bonus_frequency)
    )
    performance_annual = 0.0
    subsidy_annual = 0.0
    salary_detail = []
    for item in salary_items:
        amount = float(item.get("amount") or 0.0)
        frequency = str(item.get("frequency") or "monthly")
        annual = amount * _frequency_factor(frequency)
        if str(item.get("item_type") or "performance") == "subsidy":
            subsidy_annual += annual
        else:
            performance_annual += annual
        salary_detail.append(
            {
                "item_type": item.get("item_type", "performance"),
                "name": item.get("name", ""),
                "amount": amount,
                "frequency": frequency,
                "annual": annual,
            }
        )
    total_salary = (
        base_annual
        + thirteen_annual
        + bonus_annual
        + performance_annual
        + subsidy_annual
    )

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

    gross_income = total_salary - personal_total * 12
    total_package = total_salary - personal_total * 12 + company_total * 12
    return {
        "params": p,
        "items": detail,
        "salary_items": salary_detail,
        "personal_total": personal_total,
        "company_total": company_total,
        "base_annual": base_annual,
        "thirteen_annual": thirteen_annual,
        "bonus_annual": bonus_annual,
        "performance_annual": performance_annual,
        "subsidy_annual": subsidy_annual,
        "total_salary": total_salary,
        "gross_income": gross_income,
        "total_package": total_package,
    }


def social_insurance(conn: sqlite3.Connection, year_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM social_insurance_params WHERE year_id = ?", (year_id,)
    ).fetchone()
    items = repository.list_insurance_items(conn, year_id)
    salary_items = repository.list_salary_items(conn, year_id)
    if row is None:
        return {"has_params": False, "items": items, "salary_items": salary_items}
    return {
        "has_params": True,
        **social_insurance_from_data(dict(row), items, salary_items),
    }


def _frequency_factor(frequency: str) -> float:
    if frequency == "monthly":
        return 12.0
    if frequency == "quarterly":
        return 4.0
    return 1.0
