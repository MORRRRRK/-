"""SQLite 数据访问层。"""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable


def list_years(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM years ORDER BY year")]


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
        conn.execute(
            """
            INSERT INTO monthly_records (
              year_id, month, salary, year_end_bonus, subsidies, reimbursements,
              income_note, rent, utilities, housing_note, forced_deposit, deposit_note
            ) VALUES (
              :year_id, :month, :salary, :year_end_bonus, :subsidies, :reimbursements,
              :income_note, :rent, :utilities, :housing_note, :forced_deposit, :deposit_note
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
              forced_deposit = excluded.forced_deposit,
              deposit_note = excluded.deposit_note
            """,
            {**rec, "year_id": year_id},
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
          thirteenth_amount, year_end_bonus_amount, housing_subsidy,
          housing_fund_personal_rate, housing_fund_company_rate,
          pension_personal_rate, pension_company_rate, medical_personal_rate,
          medical_company_rate, big_medical_personal, big_medical_company,
          maternity_personal_rate, maternity_company_rate, injury_personal_rate,
          injury_company_rate, unemployment_personal_rate, unemployment_company_rate
        ) VALUES (
          :year_id, :base, :monthly_salary, :thirteenth_month_months, :year_end_bonus_months,
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
        {**params, "year_id": year_id},
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


def list_holdings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM holdings ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def add_holding(conn: sqlite3.Connection, holding: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO holdings (
          category, channel, name, holding_value, holding_profit, cumulative_profit,
          return_rate, cost_basis, invest_plan, invest_time, note,
          symbol, asset_type, shares, last_price, price_time
        ) VALUES (
          :category, :channel, :name, :holding_value, :holding_profit, :cumulative_profit,
          :return_rate, :cost_basis, :invest_plan, :invest_time, :note,
          :symbol, :asset_type, :shares, :last_price, :price_time
        )
        """,
        {
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
                    "category", "channel", "name", "holding_value", "holding_profit",
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
          name, province, start_year, end_year, monthly_base, note
        ) VALUES (
          :name, :province, :start_year, :end_year, :monthly_base, :note
        )
        """,
        {
            "name": job.get("name", ""),
            "province": job.get("province", ""),
            "start_year": int(job.get("start_year", 0)),
            "end_year": int(job.get("end_year", 0)),
            "monthly_base": float(job.get("monthly_base", 0.0) or 0.0),
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
          monthly_base = :monthly_base, note = :note
        WHERE id = :id
        """,
        {
            **job,
            "id": job_id,
        },
    )


def delete_pension_job(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute("DELETE FROM pension_jobs WHERE id = ?", (job_id,))


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
          name, channel, grams, cost_basis, last_price, price_time, note
        ) VALUES (
          :name, :channel, :grams, :cost_basis, :last_price, :price_time, :note
        )
        """,
        {
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
          name = :name, channel = :channel, grams = :grams,
          cost_basis = :cost_basis, last_price = :last_price,
          price_time = :price_time, note = :note
        WHERE id = :id
        """,
        {
            **account,
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
    conn.execute("DELETE FROM social_insurance_params")
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
