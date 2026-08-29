"""SQLite 数据访问层。"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable


def list_years(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM years ORDER BY year")]


def list_salary_profiles(
    conn: sqlite3.Connection, include_closed: bool = True
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM salary_profiles"
    if not include_closed:
        sql += " WHERE is_open = 1"
    sql += " ORDER BY is_open DESC, sort_order, id"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def list_open_salary_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return list_salary_profiles(conn, include_closed=False)


def get_salary_profile(
    conn: sqlite3.Connection, profile_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM salary_profiles WHERE id = ?", (profile_id,)
    ).fetchone()
    return dict(row) if row else None


def add_salary_profile(
    conn: sqlite3.Connection,
    name: str,
    year: int,
    payload: dict[str, Any] | None = None,
    is_open: int = 1,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO salary_profiles(name, year, is_open, sort_order, payload)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            name,
            int(year),
            is_open,
            int(
                conn.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) FROM salary_profiles"
                ).fetchone()[0]
                + 1
            ),
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )
    return int(cur.lastrowid)


def save_salary_profile(
    conn: sqlite3.Connection,
    profile_id: int,
    name: str,
    year: int,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE salary_profiles SET
          name = ?, year = ?, payload = ?,
          updated_at = datetime('now', 'localtime')
        WHERE id = ?
        """,
        (
            str(name or "工资方案"),
            int(year),
            json.dumps(payload, ensure_ascii=False),
            profile_id,
        ),
    )


def set_salary_profile_open(
    conn: sqlite3.Connection, profile_id: int, is_open: int
) -> None:
    conn.execute(
        "UPDATE salary_profiles SET is_open = ? WHERE id = ?",
        (1 if is_open else 0, profile_id),
    )


def delete_salary_profile(conn: sqlite3.Connection, profile_id: int) -> None:
    conn.execute("DELETE FROM salary_profiles WHERE id = ?", (profile_id,))


def ensure_open_salary_profile(conn: sqlite3.Connection) -> dict[str, Any]:
    """至少保留一个打开的工资方案；没有时用默认空方案创建一个。"""
    profiles = list_open_salary_profiles(conn)
    if profiles:
        return profiles[0]
    profile_id = add_salary_profile(conn, "默认方案", 2026, {})
    conn.commit()
    return get_salary_profile(conn, profile_id)  # type: ignore[return-value]


def ensure_year(conn: sqlite3.Connection, year: int) -> int:
    row = conn.execute("SELECT id FROM years WHERE year = ?", (year,)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute("INSERT INTO years(year) VALUES (?)", (year,))
    return int(cur.lastrowid)


def get_monthly_records(
    conn: sqlite3.Connection, year_id: int
) -> dict[int, dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM monthly_records WHERE year_id = ? ORDER BY month", (year_id,)
    ).fetchall()
    return {int(r["month"]): dict(r) for r in rows}


def upsert_monthly_records(
    conn: sqlite3.Connection, year_id: int, records: Iterable[dict[str, Any]]
) -> None:
    for rec in records:
        values = {
            "year_id": year_id,
            "month": int(rec.get("month", 0)),
            "salary": float(rec.get("salary", 0.0) or 0.0),
            "year_end_bonus": float(rec.get("year_end_bonus", 0.0) or 0.0),
            "subsidies": float(rec.get("subsidies", 0.0) or 0.0),
            "reimbursements": float(rec.get("reimbursements", 0.0) or 0.0),
            "income_note": str(rec.get("income_note", "")),
            "rent": float(rec.get("rent", 0.0) or 0.0),
            "utilities": float(rec.get("utilities", 0.0) or 0.0),
            "housing_note": str(rec.get("housing_note", "")),
            "monthly_expense": float(rec.get("monthly_expense", 0.0) or 0.0),
            "forced_deposit": float(rec.get("forced_deposit", 0.0) or 0.0),
            "deposit_note": str(rec.get("deposit_note", "")),
        }
        conn.execute(
            """
            INSERT INTO monthly_records (
              year_id, month, salary, year_end_bonus, subsidies, reimbursements,
              income_note, rent, utilities, housing_note, monthly_expense,
              forced_deposit, deposit_note
            ) VALUES (
              :year_id, :month, :salary, :year_end_bonus, :subsidies, :reimbursements,
              :income_note, :rent, :utilities, :housing_note, :monthly_expense,
              :forced_deposit, :deposit_note
            )
            ON CONFLICT(year_id, month) DO UPDATE SET
              salary = excluded.salary,
              year_end_bonus = excluded.year_end_bonus,
              subsidies = excluded.subsidies,
              reimbursements = excluded.reimbursements,
              income_note = excluded.income_note,
              rent = excluded.rent,
              utilities = excluded.utilities,
              housing_note = excluded.housing_note,
              monthly_expense = excluded.monthly_expense,
              forced_deposit = excluded.forced_deposit,
              deposit_note = excluded.deposit_note
            """,
            values,
        )


def get_tax_params(
    conn: sqlite3.Connection, year_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM tax_params WHERE year_id = ?", (year_id,)
    ).fetchone()
    return dict(row) if row else None


def upsert_tax_params(
    conn: sqlite3.Connection, year_id: int, params: dict[str, Any]
) -> None:
    conn.execute(
        """
        INSERT INTO tax_params (
          year_id, rent_city, rent_province, rent_district, rent_tier, elderly_option,
          children_education_count, infant_care_count,
          continuing_education, mortgage_interest,
          severe_illness_annual, bonus_tax_method, custom_deduction
        ) VALUES (
          :year_id, :rent_city, :rent_province, :rent_district, :rent_tier, :elderly_option,
          :children_education_count, :infant_care_count,
          :continuing_education, :mortgage_interest,
          :severe_illness_annual, :bonus_tax_method, :custom_deduction
        )
        ON CONFLICT(year_id) DO UPDATE SET
          rent_city = excluded.rent_city,
          rent_province = excluded.rent_province,
          rent_district = excluded.rent_district,
          rent_tier = excluded.rent_tier,
          elderly_option = excluded.elderly_option,
          children_education_count = excluded.children_education_count,
          infant_care_count = excluded.infant_care_count,
          continuing_education = excluded.continuing_education,
          mortgage_interest = excluded.mortgage_interest,
          severe_illness_annual = excluded.severe_illness_annual,
          bonus_tax_method = excluded.bonus_tax_method,
          custom_deduction = excluded.custom_deduction
        """,
        {
            "year_id": year_id,
            "rent_city": str(params.get("rent_city", "")),
            "rent_province": str(params.get("rent_province", "")),
            "rent_district": str(params.get("rent_district", "")),
            "rent_tier": float(params.get("rent_tier", 0.0) or 0.0),
            "elderly_option": str(params.get("elderly_option", "only_child")),
            "children_education_count": int(params.get("children_education_count", 0) or 0),
            "infant_care_count": int(params.get("infant_care_count", 0) or 0),
            "continuing_education": int(params.get("continuing_education", 0) or 0),
            "mortgage_interest": int(params.get("mortgage_interest", 0) or 0),
            "severe_illness_annual": float(
                params.get("severe_illness_annual", 0.0) or 0.0
            ),
            "bonus_tax_method": str(params.get("bonus_tax_method", "separate")),
            "custom_deduction": float(params.get("custom_deduction", 0.0) or 0.0),
        },
    )


def get_large_items(conn: sqlite3.Connection, year_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM large_items WHERE year_id = ? ORDER BY id", (year_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def add_large_item(conn: sqlite3.Connection, year_id: int, item: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO large_items(year_id, item_type, item_date, name, amount, note)
        VALUES (:year_id, :item_type, :item_date, :name, :amount, :note)
        """,
        {**item, "year_id": year_id},
    )
    return int(cur.lastrowid)


def update_large_item(conn: sqlite3.Connection, item_id: int, item: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE large_items
        SET item_type = :item_type, item_date = :item_date, name = :name,
            amount = :amount, note = :note
        WHERE id = :id
        """,
        {**item, "id": item_id},
    )


def delete_large_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM large_items WHERE id = ?", (item_id,))


def get_insurance_params(
    conn: sqlite3.Connection, year_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM social_insurance_params WHERE year_id = ?", (year_id,)
    ).fetchone()
    return dict(row) if row else None


def upsert_insurance_params(
    conn: sqlite3.Connection, year_id: int, params: dict[str, Any]
) -> None:
    conn.execute(
        """
        INSERT INTO social_insurance_params (
          year_id, base, monthly_salary, thirteenth_month_months, year_end_bonus_months,
          thirteenth_coefficient, thirteenth_frequency,
          year_end_bonus_coefficient, year_end_bonus_frequency,
          thirteenth_amount, year_end_bonus_amount, housing_subsidy,
          housing_fund_personal_rate, housing_fund_company_rate,
          pension_personal_rate, pension_company_rate, medical_personal_rate,
          medical_company_rate, big_medical_personal, big_medical_company,
          maternity_personal_rate, maternity_company_rate, injury_personal_rate,
          injury_company_rate, unemployment_personal_rate, unemployment_company_rate
        ) VALUES (
          :year_id, :base, :monthly_salary, :thirteenth_month_months, :year_end_bonus_months,
          :thirteenth_coefficient, :thirteenth_frequency,
          :year_end_bonus_coefficient, :year_end_bonus_frequency,
          :thirteenth_amount, :year_end_bonus_amount, :housing_subsidy,
          :housing_fund_personal_rate, :housing_fund_company_rate,
          :pension_personal_rate, :pension_company_rate, :medical_personal_rate,
          :medical_company_rate, :big_medical_personal, :big_medical_company,
          :maternity_personal_rate, :maternity_company_rate, :injury_personal_rate,
          :injury_company_rate, :unemployment_personal_rate, :unemployment_company_rate
        )
        ON CONFLICT(year_id) DO UPDATE SET
          base = excluded.base,
          monthly_salary = excluded.monthly_salary,
          thirteenth_month_months = excluded.thirteenth_month_months,
          year_end_bonus_months = excluded.year_end_bonus_months,
          thirteenth_coefficient = excluded.thirteenth_coefficient,
          thirteenth_frequency = excluded.thirteenth_frequency,
          year_end_bonus_coefficient = excluded.year_end_bonus_coefficient,
          year_end_bonus_frequency = excluded.year_end_bonus_frequency,
          thirteenth_amount = excluded.thirteenth_amount,
          year_end_bonus_amount = excluded.year_end_bonus_amount,
          housing_subsidy = excluded.housing_subsidy,
          housing_fund_personal_rate = excluded.housing_fund_personal_rate,
          housing_fund_company_rate = excluded.housing_fund_company_rate,
          pension_personal_rate = excluded.pension_personal_rate,
          pension_company_rate = excluded.pension_company_rate,
          medical_personal_rate = excluded.medical_personal_rate,
          medical_company_rate = excluded.medical_company_rate,
          big_medical_personal = excluded.big_medical_personal,
          big_medical_company = excluded.big_medical_company,
          maternity_personal_rate = excluded.maternity_personal_rate,
          maternity_company_rate = excluded.maternity_company_rate,
          injury_personal_rate = excluded.injury_personal_rate,
          injury_company_rate = excluded.injury_company_rate,
          unemployment_personal_rate = excluded.unemployment_personal_rate,
          unemployment_company_rate = excluded.unemployment_company_rate
        """,
        {
            **params,
            "year_id": year_id,
            "thirteenth_coefficient": float(
                params.get("thirteenth_coefficient", 1.0) or 1.0
            ),
            "thirteenth_frequency": str(
                params.get("thirteenth_frequency", "annual")
            ),
            "year_end_bonus_coefficient": float(
                params.get("year_end_bonus_coefficient", 1.0) or 1.0
            ),
            "year_end_bonus_frequency": str(
                params.get("year_end_bonus_frequency", "annual")
            ),
        },
    )


def list_insurance_items(conn: sqlite3.Connection, year_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM insurance_items WHERE year_id = ? ORDER BY sort_order, id",
        (year_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def replace_insurance_items(
    conn: sqlite3.Connection, year_id: int, items: Iterable[dict[str, Any]]
) -> None:
    conn.execute("DELETE FROM insurance_items WHERE year_id = ?", (year_id,))
    for index, item in enumerate(items):
        conn.execute(
            """
            INSERT INTO insurance_items(
              year_id, name, base, personal_rate, company_rate, personal_fixed, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                year_id,
                item.get("name", ""),
                float(item.get("base", 0.0) or 0.0),
                float(item.get("personal_rate", 0.0) or 0.0),
                float(item.get("company_rate", 0.0) or 0.0),
                item.get("personal_fixed"),
                index,
            ),
        )


def list_salary_items(
    conn: sqlite3.Connection, year_id: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM salary_items WHERE year_id = ? ORDER BY sort_order, id",
        (year_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def replace_salary_items(
    conn: sqlite3.Connection, year_id: int, items: Iterable[dict[str, Any]]
) -> None:
    conn.execute("DELETE FROM salary_items WHERE year_id = ?", (year_id,))
    for index, item in enumerate(items):
        conn.execute(
            """
            INSERT INTO salary_items(
              year_id, item_type, name, amount, frequency, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                year_id,
                str(item.get("item_type", "performance")),
                str(item.get("name", "自定义")),
                float(item.get("amount", 0.0) or 0.0),
                str(item.get("frequency", "monthly")),
                index,
            ),
        )


def list_holdings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM holdings ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_holding(
    conn: sqlite3.Connection, holding_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM holdings WHERE id = ?", (holding_id,)
    ).fetchone()
    return dict(row) if row else None


def add_holding(conn: sqlite3.Connection, holding: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO holdings (
          account_id, category, channel, name, holding_value, holding_profit, cumulative_profit,
          return_rate, cost_basis, invest_plan, invest_time, note,
          symbol, asset_type, shares, last_price, price_time
        ) VALUES (
          :account_id, :category, :channel, :name, :holding_value, :holding_profit, :cumulative_profit,
          :return_rate, :cost_basis, :invest_plan, :invest_time, :note,
          :symbol, :asset_type, :shares, :last_price, :price_time
        )
        """,
        {
            "account_id": holding.get("account_id"),
            "category": holding.get("category", ""),
            "channel": holding.get("channel", ""),
            "name": holding.get("name", ""),
            "holding_value": float(holding.get("holding_value", 0.0) or 0.0),
            "holding_profit": float(holding.get("holding_profit", 0.0) or 0.0),
            "cumulative_profit": float(holding.get("cumulative_profit", 0.0) or 0.0),
            "return_rate": holding.get("return_rate"),
            "cost_basis": holding.get("cost_basis"),
            "invest_plan": holding.get("invest_plan", ""),
            "invest_time": holding.get("invest_time", ""),
            "note": holding.get("note", ""),
            "symbol": holding.get("symbol", ""),
            "asset_type": holding.get("asset_type", ""),
            "shares": float(holding.get("shares", 0.0) or 0.0),
            "last_price": holding.get("last_price"),
            "price_time": holding.get("price_time", ""),
        },
    )
    return int(cur.lastrowid)


def update_holding(conn: sqlite3.Connection, holding_id: int, holding: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE holdings SET
          account_id = COALESCE(:account_id, account_id),
          category = :category, channel = :channel, name = :name,
          holding_value = :holding_value, holding_profit = :holding_profit,
          cumulative_profit = :cumulative_profit, return_rate = :return_rate,
          cost_basis = :cost_basis, invest_plan = :invest_plan,
          invest_time = :invest_time, note = :note,
          symbol = :symbol, asset_type = :asset_type, shares = :shares,
          last_price = :last_price, price_time = :price_time
        WHERE id = :id
        """,
        {
            **{
                k: holding.get(k)
                for k in (
                    "account_id", "category", "channel", "name", "holding_value", "holding_profit",
                    "cumulative_profit", "return_rate", "cost_basis", "invest_plan",
                    "invest_time", "note", "symbol", "asset_type", "shares",
                    "last_price", "price_time",
                )
            },
            "id": holding_id,
        },
    )


def delete_holding(conn: sqlite3.Connection, holding_id: int) -> None:
    conn.execute("DELETE FROM holdings WHERE id = ?", (holding_id,))


def replace_holdings(conn: sqlite3.Connection, holdings: Iterable[dict[str, Any]]) -> None:
    conn.execute("DELETE FROM holdings")
    for holding in holdings:
        add_holding(conn, holding)


def list_goals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM goals ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def add_goal(conn: sqlite3.Connection, goal: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO goals(name, target_amount, target_date, current_amount, monthly_saving, note)
        VALUES (:name, :target_amount, :target_date, :current_amount, :monthly_saving, :note)
        """,
        goal,
    )
    return int(cur.lastrowid)


def update_goal(conn: sqlite3.Connection, goal_id: int, goal: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE goals SET
          name = :name, target_amount = :target_amount, target_date = :target_date,
          current_amount = :current_amount, monthly_saving = :monthly_saving, note = :note
        WHERE id = :id
        """,
        {**goal, "id": goal_id},
    )


def delete_goal(conn: sqlite3.Connection, goal_id: int) -> None:
    conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))


def list_pension_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM pension_jobs ORDER BY end_year, id"
    ).fetchall()
    return [dict(r) for r in rows]


def add_pension_job(conn: sqlite3.Connection, job: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO pension_jobs(
          name, province, start_year, end_year, monthly_base,
          personal_rate, company_rate, note
        ) VALUES (
          :name, :province, :start_year, :end_year, :monthly_base,
          :personal_rate, :company_rate, :note
        )
        """,
        {
            "name": job.get("name", ""),
            "province": job.get("province", ""),
            "start_year": int(job.get("start_year", 0)),
            "end_year": int(job.get("end_year", 0)),
            "monthly_base": float(job.get("monthly_base", 0.0) or 0.0),
            "personal_rate": float(job.get("personal_rate", 0.08) or 0.08),
            "company_rate": float(job.get("company_rate", 0.16) or 0.16),
            "note": job.get("note", ""),
        },
    )
    return int(cur.lastrowid)


def update_pension_job(
    conn: sqlite3.Connection, job_id: int, job: dict[str, Any]
) -> None:
    conn.execute(
        """
        UPDATE pension_jobs SET
          name = :name, province = :province,
          start_year = :start_year, end_year = :end_year,
          monthly_base = :monthly_base,
          personal_rate = :personal_rate, company_rate = :company_rate,
          note = :note
        WHERE id = :id
        """,
        {
            **job,
            "id": job_id,
        },
    )


def delete_pension_job(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute("DELETE FROM pension_jobs WHERE id = ?", (job_id,))


def list_ai_reports(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM ai_reports ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def add_ai_report(conn: sqlite3.Connection, report: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO ai_reports(
          report_type, title, period_start, period_end, content, model
        ) VALUES (
          :report_type, :title, :period_start, :period_end, :content, :model
        )
        """,
        {
            "report_type": report.get("report_type", ""),
            "title": report.get("title", ""),
            "period_start": report.get("period_start", ""),
            "period_end": report.get("period_end", ""),
            "content": report.get("content", ""),
            "model": report.get("model", ""),
        },
    )
    return int(cur.lastrowid)


def delete_ai_report(conn: sqlite3.Connection, report_id: int) -> None:
    conn.execute("DELETE FROM ai_reports WHERE id = ?", (report_id,))


def list_invest_executions(
    conn: sqlite3.Connection, holding_id: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM invest_executions WHERE holding_id = ? ORDER BY execute_date",
        (holding_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def has_invest_execution(
    conn: sqlite3.Connection, holding_id: int, execute_date: str
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM invest_executions WHERE holding_id = ? AND execute_date = ?",
        (holding_id, execute_date),
    ).fetchone()
    return row is not None


def add_invest_execution(
    conn: sqlite3.Connection,
    holding_id: int,
    execute_date: str,
    amount: float,
    shares: float,
    price: float,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO invest_executions(holding_id, execute_date, amount, shares, price)
        VALUES (?, ?, ?, ?, ?)
        """,
        (holding_id, execute_date, amount, shares, price),
    )
    return int(cur.lastrowid)


def list_gold_accounts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM gold_accounts ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def add_gold_account(conn: sqlite3.Connection, account: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO gold_accounts(
          account_id, name, channel, grams, cost_basis, last_price, price_time, note
        ) VALUES (
          :account_id, :name, :channel, :grams, :cost_basis, :last_price, :price_time, :note
        )
        """,
        {
            "account_id": account.get("account_id"),
            "name": account.get("name", ""),
            "channel": account.get("channel", ""),
            "grams": float(account.get("grams", 0.0) or 0.0),
            "cost_basis": float(account.get("cost_basis", 0.0) or 0.0),
            "last_price": account.get("last_price"),
            "price_time": account.get("price_time", ""),
            "note": account.get("note", ""),
        },
    )
    return int(cur.lastrowid)


def update_gold_account(
    conn: sqlite3.Connection, account_id: int, account: dict[str, Any]
) -> None:
    conn.execute(
        """
        UPDATE gold_accounts SET
          account_id = COALESCE(:account_id, account_id),
          name = :name, channel = :channel, grams = :grams,
          cost_basis = :cost_basis, last_price = :last_price,
          price_time = :price_time, note = :note
        WHERE id = :id
        """,
        {
            **account,
            "account_id": account.get("account_id"),
            "id": account_id,
        },
    )


def delete_gold_account(conn: sqlite3.Connection, account_id: int) -> None:
    conn.execute("DELETE FROM gold_accounts WHERE id = ?", (account_id,))


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def clear_imported_data(conn: sqlite3.Connection) -> None:
    """Excel 重新导入前清空由迁移产生的业务数据。"""
    conn.execute("DELETE FROM gold_accounts")
    conn.execute("DELETE FROM invest_executions")
    conn.execute("DELETE FROM goals")
    conn.execute("DELETE FROM pension_jobs")
    conn.execute("DELETE FROM monthly_images")
    conn.execute("DELETE FROM large_items")
    conn.execute("DELETE FROM monthly_records")
    conn.execute("DELETE FROM tax_params")
    conn.execute("DELETE FROM social_insurance_params")
    conn.execute("DELETE FROM salary_items")
    conn.execute("DELETE FROM holdings")
    conn.execute("DELETE FROM years")


def list_monthly_images(
    conn: sqlite3.Connection, year_id: int, month: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM monthly_images WHERE year_id = ? AND month = ? ORDER BY id",
        (year_id, month),
    ).fetchall()
    return [dict(r) for r in rows]


def add_monthly_image(
    conn: sqlite3.Connection,
    year_id: int,
    month: int,
    file_path: str,
    note: str = "",
) -> int:
    cur = conn.execute(
        "INSERT INTO monthly_images(year_id, month, file_path, note) VALUES (?, ?, ?, ?)",
        (year_id, month, file_path, note),
    )
    return int(cur.lastrowid)


def delete_monthly_image(conn: sqlite3.Connection, image_id: int) -> None:
    conn.execute("DELETE FROM monthly_images WHERE id = ?", (image_id,))


def list_chat_messages(
    conn: sqlite3.Connection, limit: int = 0
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM ai_chat_messages ORDER BY id DESC"
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    messages = [dict(r) for r in rows]
    messages.reverse()
    return messages


def add_chat_message(
    conn: sqlite3.Connection, role: str, content: str
) -> int:
    cur = conn.execute(
        "INSERT INTO ai_chat_messages(role, content) VALUES (?, ?)",
        (str(role), str(content)),
    )
    return int(cur.lastrowid)


def clear_chat_messages(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM ai_chat_messages")
    conn.execute(
        "INSERT INTO ai_chat_state(id, summary) VALUES (1, '') "
        "ON CONFLICT(id) DO UPDATE SET summary = '', "
        "updated_at = datetime('now', 'localtime')"
    )


def get_chat_summary(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT summary FROM ai_chat_state WHERE id = 1"
    ).fetchone()
    return str(row["summary"]) if row else ""


def save_chat_summary(conn: sqlite3.Connection, summary: str) -> None:
    conn.execute(
        "INSERT INTO ai_chat_state(id, summary) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET summary = ?, "
        "updated_at = datetime('now', 'localtime')",
        (str(summary), str(summary)),
    )


def list_spending_plans(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM spending_plans ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def get_spending_plan(
    conn: sqlite3.Connection, plan_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM spending_plans WHERE id = ?", (plan_id,)
    ).fetchone()
    return dict(row) if row else None


def add_spending_plan(
    conn: sqlite3.Connection,
    name: str,
    total_budget: float = 0.0,
    start_date: str = "",
    end_date: str = "",
    note: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO spending_plans(
          name, total_budget, start_date, end_date, note
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(name or "新计划"),
            float(total_budget or 0.0),
            str(start_date or ""),
            str(end_date or ""),
            str(note or ""),
        ),
    )
    plan_id = int(cur.lastrowid)
    conn.execute(
        """
        INSERT INTO spending_plan_items(
          plan_id, name, sort_order
        ) VALUES (?, '未分项', 0)
        """,
        (plan_id,),
    )
    return plan_id


def update_spending_plan(
    conn: sqlite3.Connection,
    plan_id: int,
    name: str,
    total_budget: float = 0.0,
    start_date: str = "",
    end_date: str = "",
    note: str = "",
) -> None:
    conn.execute(
        """
        UPDATE spending_plans SET
          name = ?, total_budget = ?, start_date = ?, end_date = ?, note = ?,
          updated_at = datetime('now', 'localtime')
        WHERE id = ?
        """,
        (
            str(name or "新计划"),
            float(total_budget or 0.0),
            str(start_date or ""),
            str(end_date or ""),
            str(note or ""),
            plan_id,
        ),
    )


def delete_spending_plan(
    conn: sqlite3.Connection, plan_id: int
) -> None:
    conn.execute("DELETE FROM spending_plans WHERE id = ?", (plan_id,))


def restore_spending_plan(
    conn: sqlite3.Connection, plan: dict[str, Any]
) -> int:
    cur = conn.execute(
        """
        INSERT INTO spending_plans(
          id, name, total_budget, start_date, end_date, note,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(plan["id"]),
            plan.get("name", "新计划"),
            float(plan.get("total_budget") or 0.0),
            plan.get("start_date", ""),
            plan.get("end_date", ""),
            plan.get("note", ""),
            plan.get("created_at", ""),
            plan.get("updated_at", ""),
        ),
    )
    return int(cur.lastrowid)


def list_spending_plan_items(
    conn: sqlite3.Connection, plan_id: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM spending_plan_items
        WHERE plan_id = ? ORDER BY sort_order, id
        """,
        (plan_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_spending_plan_item(
    conn: sqlite3.Connection, item_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM spending_plan_items WHERE id = ?", (item_id,)
    ).fetchone()
    return dict(row) if row else None


def add_spending_plan_item(
    conn: sqlite3.Connection,
    plan_id: int,
    name: str,
    planned_amount: float = 0.0,
    manual_actual: float = 0.0,
    note: str = "",
    completed: int = 0,
) -> int:
    sort_order = int(
        conn.execute(
            """
            SELECT COALESCE(MAX(sort_order), 0) FROM spending_plan_items
            WHERE plan_id = ?
            """,
            (plan_id,),
        ).fetchone()[0]
        + 1
    )
    cur = conn.execute(
        """
        INSERT INTO spending_plan_items(
          plan_id, name, planned_amount, manual_actual, note,
          completed, sort_order
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plan_id,
            str(name or "新分项"),
            float(planned_amount or 0.0),
            float(manual_actual or 0.0),
            str(note or ""),
            int(completed or 0),
            sort_order,
        ),
    )
    return int(cur.lastrowid)


def update_spending_plan_item(
    conn: sqlite3.Connection,
    item_id: int,
    name: str,
    planned_amount: float = 0.0,
    manual_actual: float = 0.0,
    note: str = "",
    completed: int = 0,
) -> None:
    conn.execute(
        """
        UPDATE spending_plan_items SET
          name = ?, planned_amount = ?, manual_actual = ?, note = ?,
          completed = ?
        WHERE id = ?
        """,
        (
            str(name or "新分项"),
            float(planned_amount or 0.0),
            float(manual_actual or 0.0),
            str(note or ""),
            int(completed or 0),
            item_id,
        ),
    )


def update_spending_plan_item_voucher(
    conn: sqlite3.Connection,
    item_id: int,
    voucher_path: str,
) -> None:
    conn.execute(
        "UPDATE spending_plan_items SET voucher_path = ? WHERE id = ?",
        (str(voucher_path or ""), item_id),
    )


def update_spending_plan_item_sort(
    conn: sqlite3.Connection, item_id: int, sort_order: int
) -> None:
    conn.execute(
        "UPDATE spending_plan_items SET sort_order = ? WHERE id = ?",
        (int(sort_order), item_id),
    )


def delete_spending_plan_item(
    conn: sqlite3.Connection, item_id: int
) -> None:
    conn.execute(
        "DELETE FROM spending_plan_items WHERE id = ?", (item_id,)
    )


def restore_spending_plan_item(
    conn: sqlite3.Connection, item: dict[str, Any]
) -> int:
    cur = conn.execute(
        """
        INSERT INTO spending_plan_items(
          id, plan_id, name, planned_amount, manual_actual, note,
          completed, voucher_path, sort_order
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(item["id"]),
            int(item["plan_id"]),
            item.get("name", "未分项"),
            float(item.get("planned_amount") or 0.0),
            float(item.get("manual_actual") or 0.0),
            item.get("note", ""),
            int(item.get("completed") or 0),
            item.get("voucher_path", ""),
            int(item.get("sort_order") or 0),
        ),
    )
    return int(cur.lastrowid)


def list_spending_plan_links(
    conn: sqlite3.Connection, plan_id: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT l.*, t.trans_date, t.amount, t.merchant, t.note,
               a.name AS account_name
        FROM spending_plan_links l
        JOIN transactions t ON t.id = l.transaction_id
        LEFT JOIN accounts a ON a.id = t.account_id
        WHERE l.plan_id = ? ORDER BY t.trans_date, t.id
        """,
        (plan_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def set_spending_item_links(
    conn: sqlite3.Connection,
    plan_id: int,
    item_id: int,
    transaction_ids: Iterable[int],
) -> None:
    conn.execute(
        "DELETE FROM spending_plan_links WHERE item_id = ?", (item_id,)
    )
    seen: set[int] = set()
    for transaction_id in transaction_ids:
        transaction_id = int(transaction_id)
        if transaction_id in seen:
            continue
        seen.add(transaction_id)
        conn.execute(
            "DELETE FROM spending_plan_links "
            "WHERE plan_id = ? AND transaction_id = ?",
            (plan_id, transaction_id),
        )
        conn.execute(
            """
            INSERT INTO spending_plan_links(
              plan_id, item_id, transaction_id
            ) VALUES (?, ?, ?)
            """,
            (plan_id, item_id, transaction_id),
        )


def restore_spending_plan_links(
    conn: sqlite3.Connection, links: Iterable[dict[str, Any]]
) -> None:
    for link in links:
        transaction_id = int(link.get("transaction_id") or 0)
        exists = conn.execute(
            "SELECT 1 FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        if not exists:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO spending_plan_links(
              plan_id, item_id, transaction_id
            ) VALUES (?, ?, ?)
            """,
            (
                int(link.get("plan_id") or 0),
                int(link.get("item_id") or 0),
                transaction_id,
            ),
        )


def spending_plan_summary(
    conn: sqlite3.Connection, plan_id: int
) -> dict[str, Any]:
    items = list_spending_plan_items(conn, plan_id)
    links = list_spending_plan_links(conn, plan_id)
    linked_by_item: dict[int, list[dict[str, Any]]] = {}
    for link in links:
        linked_by_item.setdefault(int(link["item_id"]), []).append(link)
    item_rows = []
    total_actual = 0.0
    total_planned = 0.0
    total_links = 0
    for item in items:
        item_links = linked_by_item.get(int(item["id"]), [])
        linked_total = sum(
            abs(float(link.get("amount") or 0.0)) for link in item_links
        )
        manual = float(item.get("manual_actual") or 0.0)
        actual = linked_total + manual
        planned = float(item.get("planned_amount") or 0.0)
        total_actual += actual
        total_planned += planned
        total_links += len(item_links)
        item_rows.append(
            {
                **item,
                "linked_count": len(item_links),
                "linked_total": linked_total,
                "actual": actual,
            }
        )
    plan = get_spending_plan(conn, plan_id) or {}
    budget = float(plan.get("total_budget") or 0.0)
    return {
        "plan": plan,
        "items": item_rows,
        "total_actual": total_actual,
        "total_planned": total_planned,
        "total_links": total_links,
        "budget": budget,
        "remaining": budget - total_actual if budget > 0 else 0.0,
    }
