"""桌面端与 V4 手机服务端互联：推送本机数据并拉取服务端快照。"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime

from ..core import repository


class ServerSyncError(Exception):
    pass


class ServerClient:
    def __init__(self, base_url: str, token: str = ""):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        if not self.base_url:
            raise ServerSyncError("请先填写同步服务地址")
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body or {}).encode("utf-8") if body is not None else None,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except OSError:
                pass
            raise ServerSyncError(f"服务器请求失败（HTTP {exc.code}）{detail}") from exc
        except urllib.error.URLError as exc:
            raise ServerSyncError(f"无法连接服务器：{exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise ServerSyncError("服务器返回内容无法解析") from exc

    def login(self, password: str) -> str:
        data = self._request("POST", "/api/v1/auth/token", {"password": password})
        token = str(data.get("token") or "")
        if not token:
            raise ServerSyncError("服务器未返回 Token")
        self.token = token
        return token

    def snapshot(self) -> dict:
        return self._request("GET", "/api/v1/sync/snapshot")

    def push(self, changes: list[dict]) -> int:
        data = self._request("POST", "/api/v1/sync/push", {"changes": changes})
        return int(data.get("accepted") or 0)


def _desktop_entities(conn: sqlite3.Connection) -> list[dict]:
    changes: list[dict] = []
    now = time.time()
    years = {year["id"]: year["year"] for year in repository.list_years(conn)}
    for year_id, year in years.items():
        records = repository.get_monthly_records(conn, year_id)
        for month, record in records.items():
            record = dict(record)
            record["year"] = year
            changes.append(
                {
                    "table": "monthly_records",
                    "row_id": year * 100 + month,
                    "data": record,
                    "deleted": False,
                    "updated_at": now,
                }
            )
    for item in _all_large_items(conn):
        changes.append(
            {
                "table": "large_items",
                "row_id": item["id"],
                "data": {
                    "item_type": item["item_type"],
                    "item_date": item["item_date"],
                    "name": item["name"],
                    "amount": item["amount"],
                    "note": item["note"],
                    "year": _year_from_date(item["item_date"]),
                },
                "deleted": False,
                "updated_at": now,
            }
        )
    for holding in repository.list_holdings(conn):
        changes.append(
            {
                "table": "holdings",
                "row_id": holding["id"],
                "data": dict(holding),
                "deleted": False,
                "updated_at": now,
            }
        )
    for account in repository.list_gold_accounts(conn):
        changes.append(
            {
                "table": "gold_accounts",
                "row_id": account["id"],
                "data": dict(account),
                "deleted": False,
                "updated_at": now,
            }
        )
    for goal in repository.list_goals(conn):
        changes.append(
            {
                "table": "goals",
                "row_id": goal["id"],
                "data": dict(goal),
                "deleted": False,
                "updated_at": now,
            }
        )
    return changes


def _all_large_items(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM large_items ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def _year_from_date(text: str) -> int:
    digits = "".join(ch for ch in str(text or "") if ch.isdigit())
    return int(digits[:4]) if len(digits) >= 4 else datetime.now().year


def _apply_snapshot(conn: sqlite3.Connection, tables: dict) -> tuple[int, int]:
    updated = 0
    deleted = 0
    for table, rows in tables.items():
        for row in rows:
            row_id = int(row["row_id"])
            data = row.get("data") or {}
            if row.get("deleted"):
                deleted += 1
                continue
            if table == "monthly_records":
                year = row_id // 100
                month = row_id % 100
                year_id = repository.ensure_year(conn, year)
                repository.upsert_monthly_records(
                    conn, year_id, [{**data, "month": month}]
                )
            elif table == "large_items":
                year = int(data.get("year") or _year_from_date(data.get("item_date")))
                year_id = repository.ensure_year(conn, year)
                _upsert_large_item(conn, year_id, row_id, data)
            elif table == "holdings":
                _upsert_holding(conn, row_id, data)
            elif table == "gold_accounts":
                _upsert_gold_account(conn, row_id, data)
            elif table == "goals":
                _upsert_goal(conn, row_id, data)
            updated += 1
    conn.commit()
    return updated, deleted


def _upsert_large_item(
    conn: sqlite3.Connection, year_id: int, row_id: int, data: dict
) -> None:
    exists = conn.execute(
        "SELECT 1 FROM large_items WHERE id = ?", (row_id,)
    ).fetchone()
    item = {
        "item_type": data.get("item_type", "expense"),
        "item_date": data.get("item_date", ""),
        "name": data.get("name", ""),
        "amount": float(data.get("amount") or 0),
        "note": data.get("note", ""),
    }
    if exists:
        conn.execute(
            """
            UPDATE large_items SET item_type = :item_type, item_date = :item_date,
              name = :name, amount = :amount, note = :note WHERE id = :id
            """,
            {**item, "id": row_id},
        )
    else:
        conn.execute(
            """
            INSERT INTO large_items(id, year_id, item_type, item_date, name, amount, note)
            VALUES (:id, :year_id, :item_type, :item_date, :name, :amount, :note)
            """,
            {**item, "id": row_id, "year_id": year_id},
        )


def _upsert_holding(conn: sqlite3.Connection, row_id: int, data: dict) -> None:
    exists = conn.execute(
        "SELECT 1 FROM holdings WHERE id = ?", (row_id,)
    ).fetchone()
    if exists:
        repository.update_holding(conn, row_id, data)
    else:
        conn.execute(
            """
            INSERT INTO holdings(
              id, category, channel, name, holding_value, holding_profit,
              cumulative_profit, return_rate, cost_basis, invest_plan, invest_time,
              note, symbol, asset_type, shares, last_price, price_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                data.get("category", ""),
                data.get("channel", ""),
                data.get("name", ""),
                float(data.get("holding_value") or 0),
                float(data.get("holding_profit") or 0),
                float(data.get("cumulative_profit") or 0),
                data.get("return_rate"),
                data.get("cost_basis"),
                data.get("invest_plan", ""),
                data.get("invest_time", ""),
                data.get("note", ""),
                data.get("symbol", ""),
                data.get("asset_type", ""),
                float(data.get("shares") or 0),
                data.get("last_price"),
                data.get("price_time", ""),
            ),
        )


def _upsert_gold_account(
    conn: sqlite3.Connection, row_id: int, data: dict
) -> None:
    exists = conn.execute(
        "SELECT 1 FROM gold_accounts WHERE id = ?", (row_id,)
    ).fetchone()
    if exists:
        repository.update_gold_account(conn, row_id, data)
    else:
        conn.execute(
            """
            INSERT INTO gold_accounts(
              id, name, channel, grams, cost_basis, last_price, price_time, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                data.get("name", ""),
                data.get("channel", ""),
                float(data.get("grams") or 0),
                float(data.get("cost_basis") or 0),
                data.get("last_price"),
                data.get("price_time", ""),
                data.get("note", ""),
            ),
        )


def _upsert_goal(conn: sqlite3.Connection, row_id: int, data: dict) -> None:
    exists = conn.execute(
        "SELECT 1 FROM goals WHERE id = ?", (row_id,)
    ).fetchone()
    values = {
        "name": data.get("name", ""),
        "target_amount": float(data.get("target_amount") or 0),
        "target_date": data.get("target_date", ""),
        "current_amount": float(data.get("current_amount") or 0),
        "monthly_saving": float(data.get("monthly_saving") or 0),
        "note": data.get("note", ""),
    }
    if exists:
        conn.execute(
            """
            UPDATE goals SET name = :name, target_amount = :target_amount,
              target_date = :target_date, current_amount = :current_amount,
              monthly_saving = :monthly_saving, note = :note WHERE id = :id
            """,
            {**values, "id": row_id},
        )
    else:
        conn.execute(
            """
            INSERT INTO goals(
              id, name, target_amount, target_date, current_amount,
              monthly_saving, note
            ) VALUES (:id, :name, :target_amount, :target_date, :current_amount,
              :monthly_saving, :note)
            """,
            {**values, "id": row_id},
        )


def sync_all(conn: sqlite3.Connection, client: ServerClient) -> dict:
    pushed = client.push(_desktop_entities(conn))
    snapshot = client.snapshot()
    tables = snapshot.get("tables") or {}
    updated, deleted = _apply_snapshot(conn, tables)
    conn.commit()
    return {
        "pushed": pushed,
        "updated": updated,
        "deleted": deleted,
        "pulled": updated + deleted,
    }
