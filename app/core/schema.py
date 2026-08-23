SCHEMA_VERSION = 6

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

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE INDEX IF NOT EXISTS idx_monthly_year ON monthly_records(year_id, month);
CREATE INDEX IF NOT EXISTS idx_large_year ON large_items(year_id);
CREATE INDEX IF NOT EXISTS idx_holdings_category ON holdings(category);
CREATE INDEX IF NOT EXISTS idx_monthly_images_year_month ON monthly_images(year_id, month);
CREATE INDEX IF NOT EXISTS idx_insurance_items_year ON insurance_items(year_id);
CREATE INDEX IF NOT EXISTS idx_invest_executions_holding ON invest_executions(holding_id);
CREATE INDEX IF NOT EXISTS idx_gold_accounts_channel ON gold_accounts(channel);
"""


def apply_schema(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    _ensure_columns(conn)
    seed_insurance_items(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def _ensure_columns(conn) -> None:
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
