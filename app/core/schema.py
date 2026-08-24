SCHEMA_VERSION = 11

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS years (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL UNIQUE,
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS monthly_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year_id INTEGER NOT NULL REFERENCES years(id) ON DELETE CASCADE,
  month INTEGER NOT NULL,
  salary REAL NOT NULL DEFAULT 0,
  year_end_bonus REAL NOT NULL DEFAULT 0,
  subsidies REAL NOT NULL DEFAULT 0,
  reimbursements REAL NOT NULL DEFAULT 0,
  income_note TEXT NOT NULL DEFAULT '',
  rent REAL NOT NULL DEFAULT 0,
  utilities REAL NOT NULL DEFAULT 0,
  housing_note TEXT NOT NULL DEFAULT '',
  monthly_expense REAL NOT NULL DEFAULT 0,
  forced_deposit REAL NOT NULL DEFAULT 0,
  deposit_note TEXT NOT NULL DEFAULT '',
  UNIQUE(year_id, month)
);

CREATE TABLE IF NOT EXISTS large_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year_id INTEGER NOT NULL REFERENCES years(id) ON DELETE CASCADE,
  item_type TEXT NOT NULL CHECK(item_type IN ('expense', 'income')),
  item_date TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS social_insurance_params (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year_id INTEGER NOT NULL UNIQUE REFERENCES years(id) ON DELETE CASCADE,
  base REAL NOT NULL DEFAULT 0,
  monthly_salary REAL NOT NULL DEFAULT 0,
  thirteenth_month_months REAL NOT NULL DEFAULT 1,
  year_end_bonus_months REAL NOT NULL DEFAULT 1,
  thirteenth_coefficient REAL NOT NULL DEFAULT 1,
  thirteenth_frequency TEXT NOT NULL DEFAULT 'annual',
  year_end_bonus_coefficient REAL NOT NULL DEFAULT 1,
  year_end_bonus_frequency TEXT NOT NULL DEFAULT 'annual',
  housing_subsidy REAL NOT NULL DEFAULT 0,
  housing_fund_personal_rate REAL NOT NULL DEFAULT 0.09,
  housing_fund_company_rate REAL NOT NULL DEFAULT 0.09,
  pension_personal_rate REAL NOT NULL DEFAULT 0.08,
  pension_company_rate REAL NOT NULL DEFAULT 0.16,
  medical_personal_rate REAL NOT NULL DEFAULT 0.02,
  medical_company_rate REAL NOT NULL DEFAULT 0.07,
  big_medical_personal REAL NOT NULL DEFAULT 5,
  big_medical_company REAL NOT NULL DEFAULT 0,
  maternity_personal_rate REAL NOT NULL DEFAULT 0,
  maternity_company_rate REAL NOT NULL DEFAULT 0.008,
  injury_personal_rate REAL NOT NULL DEFAULT 0,
  injury_company_rate REAL NOT NULL DEFAULT 0.0135,
  unemployment_personal_rate REAL NOT NULL DEFAULT 0.005,
  unemployment_company_rate REAL NOT NULL DEFAULT 0.005
);

CREATE TABLE IF NOT EXISTS tax_params (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year_id INTEGER NOT NULL UNIQUE REFERENCES years(id) ON DELETE CASCADE,
  rent_city TEXT NOT NULL DEFAULT '',
  rent_province TEXT NOT NULL DEFAULT '',
  rent_district TEXT NOT NULL DEFAULT '',
  rent_tier REAL NOT NULL DEFAULT 0,
  elderly_option TEXT NOT NULL DEFAULT 'only_child',
  children_education_count INTEGER NOT NULL DEFAULT 0,
  infant_care_count INTEGER NOT NULL DEFAULT 0,
  continuing_education INTEGER NOT NULL DEFAULT 0,
  mortgage_interest INTEGER NOT NULL DEFAULT 0,
  severe_illness_annual REAL NOT NULL DEFAULT 0,
  bonus_tax_method TEXT NOT NULL DEFAULT 'separate',
  custom_deduction REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS holdings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL CHECK(category IN ('基金', '黄金', '股票')),
  channel TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL,
  holding_value REAL NOT NULL DEFAULT 0,
  holding_profit REAL NOT NULL DEFAULT 0,
  cumulative_profit REAL NOT NULL DEFAULT 0,
  return_rate REAL,
  cost_basis REAL,
  invest_plan TEXT NOT NULL DEFAULT '',
  invest_time TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS holdings_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_date TEXT NOT NULL DEFAULT (date('now')),
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS monthly_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year_id INTEGER NOT NULL REFERENCES years(id) ON DELETE CASCADE,
  month INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS insurance_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year_id INTEGER NOT NULL REFERENCES years(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  base REAL NOT NULL DEFAULT 0,
  personal_rate REAL NOT NULL DEFAULT 0,
  company_rate REAL NOT NULL DEFAULT 0,
  personal_fixed REAL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS salary_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year_id INTEGER NOT NULL REFERENCES years(id) ON DELETE CASCADE,
  item_type TEXT NOT NULL CHECK(item_type IN ('performance', 'subsidy')),
  name TEXT NOT NULL DEFAULT '',
  amount REAL NOT NULL DEFAULT 0,
  frequency TEXT NOT NULL DEFAULT 'monthly',
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invest_executions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  holding_id INTEGER NOT NULL REFERENCES holdings(id) ON DELETE CASCADE,
  execute_date TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  shares REAL NOT NULL DEFAULT 0,
  price REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  UNIQUE(holding_id, execute_date)
);

CREATE TABLE IF NOT EXISTS gold_accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  channel TEXT NOT NULL DEFAULT '',
  grams REAL NOT NULL DEFAULT 0,
  cost_basis REAL NOT NULL DEFAULT 0,
  last_price REAL,
  price_time TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS goals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  target_amount REAL NOT NULL DEFAULT 0,
  target_date TEXT NOT NULL DEFAULT '',
  current_amount REAL NOT NULL DEFAULT 0,
  monthly_saving REAL NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pension_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  province TEXT NOT NULL DEFAULT '',
  start_year INTEGER NOT NULL,
  end_year INTEGER NOT NULL,
  monthly_base REAL NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ai_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_type TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  period_start TEXT NOT NULL DEFAULT '',
  period_end TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE INDEX IF NOT EXISTS idx_monthly_year ON monthly_records(year_id, month);
CREATE INDEX IF NOT EXISTS idx_large_year ON large_items(year_id);
CREATE INDEX IF NOT EXISTS idx_holdings_category ON holdings(category);
CREATE INDEX IF NOT EXISTS idx_monthly_images_year_month ON monthly_images(year_id, month);
CREATE INDEX IF NOT EXISTS idx_insurance_items_year ON insurance_items(year_id);
CREATE INDEX IF NOT EXISTS idx_salary_items_year ON salary_items(year_id);
CREATE INDEX IF NOT EXISTS idx_invest_executions_holding ON invest_executions(holding_id);
CREATE INDEX IF NOT EXISTS idx_gold_accounts_channel ON gold_accounts(channel);
CREATE INDEX IF NOT EXISTS idx_pension_jobs_end_year ON pension_jobs(end_year);
CREATE INDEX IF NOT EXISTS idx_ai_reports_created ON ai_reports(created_at);
"""


def apply_schema(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    _ensure_columns(conn)
    _backfill_salary_coefficients(conn)
    _migrate_utilities_to_expense(conn)
    seed_insurance_items(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def _ensure_columns(conn) -> None:
    monthly_columns = {row[1] for row in conn.execute("PRAGMA table_info(monthly_records)")}
    if "monthly_expense" not in monthly_columns:
        conn.execute(
            "ALTER TABLE monthly_records "
            "ADD COLUMN monthly_expense REAL NOT NULL DEFAULT 0"
        )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(social_insurance_params)")}
    if "thirteenth_amount" not in columns:
        conn.execute(
            "ALTER TABLE social_insurance_params "
            "ADD COLUMN thirteenth_amount REAL NOT NULL DEFAULT 0"
        )
    if "year_end_bonus_amount" not in columns:
        conn.execute(
            "ALTER TABLE social_insurance_params "
            "ADD COLUMN year_end_bonus_amount REAL NOT NULL DEFAULT 0"
        )
    social_adds = {
        "thirteenth_coefficient": "REAL NOT NULL DEFAULT 1",
        "thirteenth_frequency": "TEXT NOT NULL DEFAULT 'annual'",
        "year_end_bonus_coefficient": "REAL NOT NULL DEFAULT 1",
        "year_end_bonus_frequency": "TEXT NOT NULL DEFAULT 'annual'",
    }
    for name, definition in social_adds.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE social_insurance_params ADD COLUMN {name} {definition}")
    tax_columns = {row[1] for row in conn.execute("PRAGMA table_info(tax_params)")}
    tax_adds = {
        "rent_province": "TEXT NOT NULL DEFAULT ''",
        "rent_district": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in tax_adds.items():
        if name not in tax_columns:
            conn.execute(f"ALTER TABLE tax_params ADD COLUMN {name} {definition}")
    holding_columns = {row[1] for row in conn.execute("PRAGMA table_info(holdings)")}
    holding_adds = {
        "symbol": "TEXT NOT NULL DEFAULT ''",
        "asset_type": "TEXT NOT NULL DEFAULT ''",
        "shares": "REAL NOT NULL DEFAULT 0",
        "last_price": "REAL",
        "price_time": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in holding_adds.items():
        if name not in holding_columns:
            conn.execute(f"ALTER TABLE holdings ADD COLUMN {name} {definition}")


def _backfill_salary_coefficients(conn) -> None:
    """把旧版 13薪/年终奖金额与月数折算成新版的“基本工资 x N”系数。"""
    rows = conn.execute("SELECT * FROM social_insurance_params").fetchall()
    for row in rows:
        p = dict(row)
        monthly = float(p.get("monthly_salary") or 0.0)
        if monthly <= 0:
            continue
        thirteenth_old = float(p.get("thirteenth_amount") or 0.0)
        thirteenth_months = float(p.get("thirteenth_month_months") or 0.0)
        if (
            float(p.get("thirteenth_coefficient") or 1.0) == 1.0
            and thirteenth_old > 0
        ):
            coefficient = thirteenth_old * thirteenth_months / monthly
            conn.execute(
                "UPDATE social_insurance_params SET thirteenth_coefficient = ? "
                "WHERE year_id = ?",
                (max(0.0, coefficient), p["year_id"]),
            )
        bonus_old = float(p.get("year_end_bonus_amount") or 0.0)
        bonus_months = float(p.get("year_end_bonus_months") or 0.0)
        if (
            float(p.get("year_end_bonus_coefficient") or 1.0) == 1.0
            and bonus_old > 0
        ):
            coefficient = bonus_old * bonus_months / monthly
            conn.execute(
                "UPDATE social_insurance_params SET year_end_bonus_coefficient = ? "
                "WHERE year_id = ?",
                (max(0.0, coefficient), p["year_id"]),
            )
        subsidy = float(p.get("housing_subsidy") or 0.0)
        if subsidy > 0:
            exists = conn.execute(
                "SELECT 1 FROM salary_items WHERE year_id = ? AND item_type = 'subsidy' "
                "AND name = '租房补贴' LIMIT 1",
                (p["year_id"],),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO salary_items"
                    "(year_id, item_type, name, amount, frequency, sort_order)"
                    " VALUES (?, 'subsidy', '租房补贴', ?, 'monthly', 0)",
                    (p["year_id"], subsidy),
                )


def _migrate_utilities_to_expense(conn) -> None:
    """V3.5：水电列改为每月支出，历史水电数据并入月支出。"""
    rows = conn.execute(
        "SELECT id, utilities, monthly_expense FROM monthly_records "
        "WHERE utilities != 0"
    ).fetchall()
    for row in rows:
        row_id, utilities, monthly_expense = row[0], row[1], row[2]
        conn.execute(
            "UPDATE monthly_records SET monthly_expense = ?, utilities = 0 WHERE id = ?",
            (
                float(monthly_expense or 0.0) + float(utilities or 0.0),
                row_id,
            ),
        )


def seed_insurance_items(conn) -> None:
    rows = conn.execute("SELECT * FROM social_insurance_params").fetchall()
    for row in rows:
        p = dict(row)
        year_id = p["year_id"]
        exists = conn.execute(
            "SELECT 1 FROM insurance_items WHERE year_id = ? LIMIT 1", (year_id,)
        ).fetchone()
        if exists:
            continue
        monthly = float(p.get("monthly_salary") or 0)
        base = float(p.get("base") or 0)
        if monthly:
            conn.execute(
                "UPDATE social_insurance_params SET thirteenth_amount = ? "
                "WHERE year_id = ? AND thirteenth_amount = 0",
                (monthly, year_id),
            )
            conn.execute(
                "UPDATE social_insurance_params SET year_end_bonus_amount = ? "
                "WHERE year_id = ? AND year_end_bonus_amount = 0",
                (monthly, year_id),
            )
        items = [
            ("公积金", monthly, p.get("housing_fund_personal_rate") or 0,
             p.get("housing_fund_company_rate") or 0, None),
            ("养老", base, p.get("pension_personal_rate") or 0,
             p.get("pension_company_rate") or 0, None),
            ("医保", base, p.get("medical_personal_rate") or 0,
             p.get("medical_company_rate") or 0, None),
            ("大额医疗", 0.0, 0.0, 0.0, p.get("big_medical_personal") or 0),
            ("生育", base, p.get("maternity_personal_rate") or 0,
             p.get("maternity_company_rate") or 0, None),
            ("工伤", base, p.get("injury_personal_rate") or 0,
             p.get("injury_company_rate") or 0, None),
            ("失业", base, p.get("unemployment_personal_rate") or 0,
             p.get("unemployment_company_rate") or 0, None),
        ]
        for index, (name, item_base, personal_rate, company_rate, fixed) in enumerate(items):
            conn.execute(
                "INSERT INTO insurance_items"
                "(year_id, name, base, personal_rate, company_rate, personal_fixed, sort_order)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (year_id, name, item_base, personal_rate, company_rate, fixed, index),
            )
