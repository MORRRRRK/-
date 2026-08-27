import json

SCHEMA_VERSION = 14

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
  account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
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
  account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  channel TEXT NOT NULL DEFAULT '',
  grams REAL NOT NULL DEFAULT 0,
  cost_basis REAL NOT NULL DEFAULT 0,
  last_price REAL,
  price_time TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('cash','bank','alipay','wechat','investment','credit_card','loan','other')),
  institution TEXT NOT NULL DEFAULT '',
  initial_balance REAL NOT NULL DEFAULT 0,
  current_balance REAL NOT NULL DEFAULT 0,
  is_liability INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS transaction_categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('expense','income')),
  parent_id INTEGER,
  icon TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_system INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trans_date TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('expense','income','transfer')),
  amount REAL NOT NULL DEFAULT 0,
  category_id INTEGER REFERENCES transaction_categories(id),
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  to_account_id INTEGER REFERENCES accounts(id),
  merchant TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  image_path TEXT NOT NULL DEFAULT '',
  is_reimbursable INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS holding_transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  holding_id INTEGER NOT NULL REFERENCES holdings(id) ON DELETE CASCADE,
  trans_type TEXT NOT NULL CHECK(trans_type IN ('buy','sell','dividend','subscription','redemption')),
  trans_date TEXT NOT NULL,
  shares REAL NOT NULL DEFAULT 0,
  price REAL NOT NULL DEFAULT 0,
  amount REAL NOT NULL DEFAULT 0,
  fee REAL NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
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

CREATE TABLE IF NOT EXISTS salary_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL DEFAULT '工资方案',
  year INTEGER NOT NULL DEFAULT 2026,
  is_open INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS ai_chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS ai_chat_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  summary TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
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
CREATE INDEX IF NOT EXISTS idx_trans_date ON transactions(trans_date);
CREATE INDEX IF NOT EXISTS idx_trans_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_trans_category ON transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_holding_trans_holding ON holding_transactions(holding_id);
CREATE INDEX IF NOT EXISTS idx_holding_trans_date ON holding_transactions(trans_date);
"""


def apply_schema(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    _ensure_columns(conn)
    _backfill_salary_coefficients(conn)
    _migrate_utilities_to_expense(conn)
    _migrate_salary_profiles(conn)
    _migrate_holdings_accounts(conn)
    seed_insurance_items(conn)
    _seed_categories(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def _migrate_salary_profiles(conn) -> None:
    """V4.4：把旧的按年份工资数据迁移成独立的工资方案。"""
    if conn.execute("SELECT 1 FROM salary_profiles LIMIT 1").fetchone():
        return
    row = conn.execute(
        """
        SELECT sp.year_id, y.year FROM social_insurance_params sp
        JOIN years y ON y.id = sp.year_id
        ORDER BY y.year DESC LIMIT 1
        """
    ).fetchone()
    if row:
        year_id, year = row["year_id"], int(row["year"])
        params = dict(conn.execute(
            "SELECT * FROM social_insurance_params WHERE year_id = ?", (year_id,)
        ).fetchone())
        params.pop("id", None)
        params.pop("year_id", None)
        items = [dict(r) for r in conn.execute(
            "SELECT * FROM insurance_items WHERE year_id = ? ORDER BY sort_order, id",
            (year_id,),
        ).fetchall()]
        salary_items = [dict(r) for r in conn.execute(
            "SELECT * FROM salary_items WHERE year_id = ? ORDER BY sort_order, id",
            (year_id,),
        ).fetchall()]
        tax = conn.execute(
            "SELECT * FROM tax_params WHERE year_id = ?", (year_id,)
        ).fetchone()
        tax_params = dict(tax) if tax else {}
        tax_params.pop("id", None)
        tax_params.pop("year_id", None)
        payload = {
            "year": year,
            "params": params,
            "items": items,
            "salary_items": salary_items,
            "tax_params": tax_params,
        }
    else:
        year = 2026
        payload = {
            "year": year,
            "params": {},
            "items": [],
            "salary_items": [],
            "tax_params": {},
        }
    conn.execute(
        """
        INSERT INTO salary_profiles(name, year, is_open, sort_order, payload)
        VALUES (?, ?, 1, 0, ?)
        """,
        ("默认方案", year, json.dumps(payload, ensure_ascii=False)),
    )


def _migrate_holdings_accounts(conn) -> None:
    """V4.4.1：把持仓/黄金账户的渠道自动转成账户并关联。"""
    for table in ("holdings", "gold_accounts"):
        rows = conn.execute(
            f"SELECT id, channel FROM {table} "
            "WHERE channel != '' AND account_id IS NULL"
        ).fetchall()
        for row in rows:
            name = str(row["channel"]).strip()
            if not name:
                continue
            account = conn.execute(
                "SELECT id FROM accounts WHERE name = ?", (name,)
            ).fetchone()
            if account:
                account_id = account["id"]
            else:
                account_id = conn.execute(
                    "INSERT INTO accounts(name, type, current_balance) "
                    "VALUES (?, 'investment', 0)",
                    (name,),
                ).lastrowid
            conn.execute(
                f"UPDATE {table} SET account_id = ? WHERE id = ?",
                (account_id, row["id"]),
            )


def _seed_categories(conn) -> None:
    """初始化内置交易分类，仅在分类表为空时执行。"""
    if conn.execute("SELECT 1 FROM transaction_categories LIMIT 1").fetchone():
        return
    defaults = [
        ("餐饮", "expense", ["正餐", "外卖", "零食", "饮料"]),
        ("交通", "expense", ["公交地铁", "打车", "加油", "停车", "高铁机票"]),
        ("购物", "expense", ["服饰", "数码", "家居", "日用"]),
        ("居住", "expense", ["房租", "水电燃气", "物业", "维修"]),
        ("娱乐", "expense", ["电影", "游戏", "旅游", "运动"]),
        ("医疗", "expense", ["门诊", "药品", "体检", "保险"]),
        ("教育", "expense", ["培训", "书籍", "会员"]),
        ("通讯", "expense", ["话费", "流量", "宽带"]),
        ("人情", "expense", ["红包", "礼物", "请客"]),
        ("其他支出", "expense", []),
        ("工资", "income", ["基本工资", "奖金", "补贴", "年终奖"]),
        ("投资收益", "income", ["基金", "股票", "黄金", "利息"]),
        ("兼职副业", "income", []),
        ("报销", "income", []),
        ("红包礼金", "income", []),
        ("其他收入", "income", []),
    ]
    order = 0
    for name, trans_type, children in defaults:
        order += 1
        parent = conn.execute(
            "INSERT INTO transaction_categories(name, type, sort_order, is_system) "
            "VALUES (?, ?, ?, 1)",
            (name, trans_type, order),
        ).lastrowid
        for child in children:
            order += 1
            conn.execute(
                "INSERT INTO transaction_categories"
                "(name, type, parent_id, sort_order, is_system) VALUES (?, ?, ?, ?, 1)",
                (child, trans_type, parent, order),
            )


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
    if "account_id" not in holding_columns:
        conn.execute(
            "ALTER TABLE holdings ADD COLUMN account_id INTEGER "
            "REFERENCES accounts(id) ON DELETE SET NULL"
        )
    gold_columns = {row[1] for row in conn.execute("PRAGMA table_info(gold_accounts)")}
    if "account_id" not in gold_columns:
        conn.execute(
            "ALTER TABLE gold_accounts ADD COLUMN account_id INTEGER "
            "REFERENCES accounts(id) ON DELETE SET NULL"
        )


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
