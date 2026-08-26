from __future__ import annotations

import json
import hashlib
import os
import secrets
import sys
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from . import db  # noqa: E402

app = FastAPI(title="个人财务 V4 同步服务", version="0.1.0")

SERVER_PASSWORD = os.environ.get("FINANCE_SERVER_PASSWORD", "finance-v4")
SERVER_PORT = 8766  # 固定端口，后续版本保持 8766，避免客户端反复改配置
APP_VERSION = "4.3.1"
APP_NOTES = (
    "V4.3.1：移除历史汇总，修复坚果云 WebDAV 目录权限，"
    "修复记账按钮反馈，支持 BlueCoins 中文 CSV 导入。"
)
APK_URL = os.environ.get("FINANCE_APK_URL", "")


def _hithink_key() -> str:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM server_settings WHERE key = 'hithink_api_key'"
        ).fetchone()
    finally:
        conn.close()
    return str(row["value"] or "") if row else os.environ.get("HITHINK_API_KEY", "")


def _llm_config() -> tuple[str, str, str]:
    conn = db.get_conn()
    try:
        values = {
            row["key"]: str(row["value"] or "")
            for row in conn.execute("SELECT key, value FROM server_settings").fetchall()
        }
    finally:
        conn.close()
    return (
        values.get("llm_base_url", "https://api.deepseek.com/v1"),
        values.get("llm_api_key", os.environ.get("LLM_API_KEY", "")),
        values.get("llm_model", "deepseek-chat"),
    )


def _report_context() -> dict:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT table_name, data_json FROM entities WHERE deleted = 0"
        ).fetchall()
    finally:
        conn.close()
    tables: dict[str, list[dict]] = {}
    for row in rows:
        tables.setdefault(row["table_name"], []).append(
            json.loads(row["data_json"] or "{}")
        )
    monthly = tables.get("monthly_records", [])
    large_items = tables.get("large_items", [])
    holdings = tables.get("holdings", [])
    gold = tables.get("gold_accounts", [])
    goals = tables.get("goals", [])
    deposits = sum(float(r.get("forced_deposit") or 0) for r in monthly)
    salary = sum(float(r.get("salary") or 0) for r in monthly)
    expense = sum(float(r.get("monthly_expense") or 0) for r in monthly)
    holding_value = sum(float(r.get("holding_value") or 0) for r in holdings)
    cumulative = sum(float(r.get("cumulative_profit") or 0) for r in holdings)
    gold_value = sum(
        float(r.get("grams") or 0) * float(r.get("last_price") or 0) for r in gold
    )
    return {
        "totals": {
            "wages": salary,
            "income": salary,
            "deposits": deposits,
            "monthly_expense": expense,
        },
        "investment_summary": {
            "total_holding": holding_value + gold_value,
            "total_cumulative": cumulative,
            "total_rate": (
                cumulative / (holding_value + gold_value)
                if holding_value + gold_value
                else 0
            ),
        },
        "monthly_records": monthly,
        "large_items": large_items,
        "holdings": holdings,
        "gold_accounts": gold,
        "goals": goals,
    }


class TokenRequest(BaseModel):
    password: str


class ChangeItem(BaseModel):
    table: str
    row_id: int
    data: dict = {}
    deleted: bool = False
    updated_at: float


class PushRequest(BaseModel):
    changes: list[ChangeItem]


class ReportRequest(BaseModel):
    report_type: str = "year"
    period_label: str = "2026 年"


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000
    ).hex()
    return f"{salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000
    ).hex()
    return candidate == digest


def require_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Token")
    token = authorization.removeprefix("Bearer ").strip()
    conn = db.get_conn()
    try:
        if not db.token_exists(conn, token):
            raise HTTPException(status_code=401, detail="Token 无效")
    finally:
        conn.close()
    return token


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}


@app.post("/api/v1/auth/token")
def create_token(req: TokenRequest) -> dict:
    if req.password != SERVER_PASSWORD:
        raise HTTPException(status_code=401, detail="密码错误")
    token = secrets.token_hex(16)
    conn = db.get_conn()
    try:
        db.register_token(conn, token)
    finally:
        conn.close()
    return {"token": token}


@app.post("/api/v1/auth/register")
def register(req: RegisterRequest) -> dict:
    username = req.username.strip()
    if len(username) < 2 or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="用户名至少 2 位，密码至少 6 位")
    conn = db.get_conn()
    try:
        if db.get_user(conn, username):
            raise HTTPException(status_code=409, detail="用户名已存在")
        db.add_user(conn, username, _hash_password(req.password))
    finally:
        conn.close()
    return {"ok": True}


@app.post("/api/v1/auth/login")
def login(req: LoginRequest) -> dict:
    username = req.username.strip()
    conn = db.get_conn()
    try:
        user = db.get_user(conn, username)
        if not user or not _verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        token = secrets.token_hex(16)
        db.register_token(conn, token)
    finally:
        conn.close()
    return {"token": token, "username": username}


@app.get("/api/v1/sync/snapshot")
def snapshot(_: str = Depends(require_token)) -> dict:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT table_name, row_id, data_json, deleted, updated_at "
            "FROM entities ORDER BY table_name, row_id"
        ).fetchall()
        tables: dict[str, list[dict]] = {}
        for row in rows:
            tables.setdefault(row["table_name"], []).append(
                {
                    "row_id": row["row_id"],
                    "data": json.loads(row["data_json"] or "{}"),
                    "deleted": bool(row["deleted"]),
                    "updated_at": row["updated_at"],
                }
            )
        last = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM changes").fetchone()[0]
        return {"tables": tables, "since": int(last)}
    finally:
        conn.close()


@app.post("/api/v1/sync/push")
def push(req: PushRequest, _: str = Depends(require_token)) -> dict:
    conn = db.get_conn()
    try:
        accepted = 0
        for item in req.changes:
            existing = conn.execute(
                "SELECT updated_at FROM entities WHERE table_name = ? AND row_id = ?",
                (item.table, item.row_id),
            ).fetchone()
            if existing is not None and existing["updated_at"] >= item.updated_at:
                continue
            conn.execute(
                """
                INSERT INTO entities(table_name, row_id, data_json, deleted, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(table_name, row_id) DO UPDATE SET
                  data_json = excluded.data_json,
                  deleted = excluded.deleted,
                  updated_at = excluded.updated_at
                """,
                (
                    item.table,
                    item.row_id,
                    json.dumps(item.data, ensure_ascii=False),
                    1 if item.deleted else 0,
                    item.updated_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO changes(table_name, row_id, data_json, deleted, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item.table,
                    item.row_id,
                    json.dumps(item.data, ensure_ascii=False),
                    1 if item.deleted else 0,
                    item.updated_at,
                ),
            )
            accepted += 1
        conn.commit()
        last = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM changes").fetchone()[0]
        return {"accepted": accepted, "since": int(last)}
    finally:
        conn.close()


@app.get("/api/v1/sync/pull")
def pull(since: int = 0, _: str = Depends(require_token)) -> dict:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT seq, table_name, row_id, data_json, deleted, updated_at
            FROM changes WHERE seq > ? ORDER BY seq
            """,
            (since,),
        ).fetchall()
        last = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM changes").fetchone()[0]
        return {
            "changes": [
                {
                    "seq": row["seq"],
                    "table": row["table_name"],
                    "row_id": row["row_id"],
                    "data": json.loads(row["data_json"] or "{}"),
                    "deleted": bool(row["deleted"]),
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ],
            "since": int(last),
        }
    finally:
        conn.close()


@app.get("/api/v1/market/quote")
def quote(symbol: str, asset_type: str, _: str = Depends(require_token)) -> dict:
    api_key = _hithink_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="服务端未配置同花顺 API Key")
    from app.services.market import MarketClient, fetch_live_price

    try:
        price, price_time = fetch_live_price(MarketClient(api_key), asset_type, symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"symbol": symbol, "asset_type": asset_type, "price": price, "time": price_time}


@app.get("/api/v1/market/gold")
def gold(_: str = Depends(require_token)) -> dict:
    from app.services.gold import fetch_gold_price

    try:
        price, price_time = fetch_gold_price()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"price": price, "time": price_time}


@app.post("/api/v1/invest/run")
def invest_run(_: str = Depends(require_token)) -> dict:
    """MVP：按持仓定投计划执行一次。详细交易日判断后续版本完善。"""
    api_key = _hithink_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="服务端未配置同花顺 API Key")
    from app.services.market import MarketClient, fetch_live_price

    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT row_id, data_json FROM entities "
            "WHERE table_name = 'holdings' AND deleted = 0"
        ).fetchall()
        executed = []
        for row in rows:
            holding = json.loads(row["data_json"] or "{}")
            plan = float(holding.get("invest_plan") or 0)
            if plan <= 0:
                continue
            symbol = (holding.get("symbol") or "").strip()
            asset_type = holding.get("asset_type") or ""
            if not symbol or not asset_type:
                continue
            try:
                price, _ = fetch_live_price(
                    MarketClient(api_key), asset_type, symbol
                )
            except Exception:
                continue
            if not price:
                continue
            shares = float(holding.get("shares") or 0) + plan / price
            value = round(shares * price, 2)
            holding["shares"] = shares
            holding["holding_value"] = value
            holding["cost_basis"] = float(holding.get("cost_basis") or 0) + plan
            holding["last_price"] = price
            holding["updated_at"] = time.time()
            conn.execute(
                """
                INSERT INTO entities(table_name, row_id, data_json, deleted, updated_at)
                VALUES ('holdings', ?, ?, 0, ?)
                ON CONFLICT(table_name, row_id) DO UPDATE SET
                  data_json = excluded.data_json, updated_at = excluded.updated_at
                """,
                (
                    row["row_id"],
                    json.dumps(holding, ensure_ascii=False),
                    holding["updated_at"],
                ),
            )
            conn.execute(
                """
                INSERT INTO changes(table_name, row_id, data_json, deleted, updated_at)
                VALUES ('holdings', ?, ?, 0, ?)
                """,
                (
                    row["row_id"],
                    json.dumps(holding, ensure_ascii=False),
                    holding["updated_at"],
                ),
            )
            executed.append(holding.get("name", "持仓"))
        conn.commit()
        return {"executed": executed}
    finally:
        conn.close()


@app.post("/api/v1/report/generate")
def report_generate(
    req: ReportRequest, _: str = Depends(require_token)
) -> dict:
    base_url, api_key, model = _llm_config()
    if not api_key:
        raise HTTPException(status_code=400, detail="服务端未配置大模型 API Key")
    from app.services import llm

    try:
        content = llm.generate_report_text(
            _report_context(),
            req.report_type,
            req.period_label,
            base_url,
            api_key,
            model,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "report_type": req.report_type,
        "period_label": req.period_label,
        "content": content,
        "model": model,
    }


@app.get("/api/v1/update")
def update(_: str = Depends(require_token)) -> dict:
    return {"version": APP_VERSION, "apk_url": APK_URL, "notes": APP_NOTES}
