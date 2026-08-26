"""局域网只读 Web 服务：提供资产总览、月度流水、持仓与智能报告查看。"""
from __future__ import annotations

import json
import secrets
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ..core import paths, repository
from ..services import (
    account_service,
    calculations,
    category_service,
    transaction_service,
)

SESSION_TTL_SECONDS = 12 * 3600


class FinanceHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, conn, access_code):
        self.conn = conn
        self.access_code = str(access_code or "")
        self.sessions: dict[str, float] = {}
        self.lock = threading.Lock()
        super().__init__(addr, handler)


class FinanceHandler(BaseHTTPRequestHandler):
    server: FinanceHTTPServer

    def log_message(self, format, *args) -> None:
        pass

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _session_token(self) -> str | None:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("finance_session="):
                return part.split("=", 1)[1]
        return None

    def _require_session(self) -> bool:
        header_code = self.headers.get("X-Access-Code", "")
        if header_code and secrets.compare_digest(
            header_code, self.server.access_code
        ):
            return True
        token = self._session_token()
        if not token:
            self._send_json({"error": "未登录"}, 401)
            return False
        with self.server.lock:
            expires = self.server.sessions.get(token)
            if expires is None or expires < time.time():
                self.server.sessions.pop(token, None)
                self._send_json({"error": "会话已过期"}, 401)
                return False
        return True

    def _require_access(self) -> bool:
        return self._require_session()

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._serve_index()
            return
        if path.startswith("/mobile/") or path in (
            "/service-worker.js",
            "/manifest.json",
        ):
            self._serve_static(path)
            return
        if path == "/api/health":
            self._send_json({"ok": True})
            return
        if not self._require_session():
            return
        query = parse_qs(parsed.query)
        if path == "/api/accounts":
            self._send_json(account_service.get_accounts(self.server.conn))
        elif path.startswith("/api/accounts/"):
            self._api_account_detail(path)
        elif path == "/api/categories":
            self._send_json(
                category_service.get_categories(
                    self.server.conn, (query.get("type") or [None])[0]
                )
            )
        elif path == "/api/transactions":
            self._api_transactions(query)
        elif path.startswith("/api/transactions/"):
            self._api_transaction_detail(path)
        elif path == "/api/summary/monthly":
            self._api_summary_monthly(query)
        elif path == "/api/summary/overview":
            self._api_overview()
        elif path == "/api/summary/category":
            self._api_summary_category(query)
        elif path == "/api/overview":
            self._api_overview()
        elif path == "/api/monthly":
            self._api_monthly(parse_qs(parsed.query))
        elif path == "/api/holdings":
            self._api_holdings()
        elif path == "/api/reports":
            self._api_reports()
        else:
            self._send_json({"error": "接口不存在"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/login":
            self._api_login()
            return
        if not self._require_access():
            return
        if path == "/api/accounts":
            self._api_create_account()
        elif path == "/api/transactions":
            self._api_create_transaction()
        else:
            self._send_json({"error": "接口不存在"}, 404)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if not self._require_access():
            return
        if parsed.path.startswith("/api/accounts/"):
            self._api_update_account(parsed.path)
        elif parsed.path.startswith("/api/transactions/"):
            self._api_update_transaction(parsed.path)
        else:
            self._send_json({"error": "接口不存在"}, 404)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not self._require_access():
            return
        if parsed.path.startswith("/api/accounts/"):
            self._api_delete_account(parsed.path)
        elif parsed.path.startswith("/api/transactions/"):
            self._api_delete_transaction(parsed.path)
        else:
            self._send_json({"error": "接口不存在"}, 404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

    def _serve_static(self, path: str) -> None:
        web_root = paths.web_dir()
        if path == "/service-worker.js":
            target = web_root / "mobile" / "service-worker.js"
            content_type = "application/javascript"
        elif path == "/manifest.json":
            target = web_root / "mobile" / "manifest.json"
            content_type = "application/manifest+json"
        else:
            relative = path.removeprefix("/mobile/") or "index.html"
            target = web_root / "mobile" / relative
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".js": "application/javascript",
                ".css": "text/css; charset=utf-8",
                ".json": "application/json",
                ".svg": "image/svg+xml",
            }.get(target.suffix, "application/octet-stream")
        if not target.exists() or not str(target.resolve()).startswith(
            str((web_root / "mobile").resolve())
        ):
            self._send_json({"error": "文件不存在"}, 404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_index(self) -> None:
        index_path = paths.web_dir() / "index.html"
        if not index_path.exists():
            self._send_json({"error": "Web 资源缺失"}, 404)
            return
        body = index_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_login(self) -> None:
        body = self._read_json_body()
        code = str(body.get("code", ""))
        if not self.server.access_code or not secrets.compare_digest(
            code, self.server.access_code
        ):
            self._send_json({"error": "访问码错误"}, 401)
            return
        token = secrets.token_hex(24)
        with self.server.lock:
            self.server.sessions[token] = time.time() + SESSION_TTL_SECONDS
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header(
            "Set-Cookie",
            f"finance_session={token}; Path=/; HttpOnly; SameSite=Lax; "
            f"Max-Age={SESSION_TTL_SECONDS}",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def _api_overview(self) -> None:
        totals = calculations.totals(self.server.conn)
        invest = calculations.investment_summary(self.server.conn)
        years = repository.list_years(self.server.conn)
        year_data = [
            {
                "year": y["year"],
                "summary": calculations.year_summary(self.server.conn, y["id"]),
            }
            for y in years
        ]
        allocation = {
            "存款": totals["deposits"],
            "基金": invest["categories"].get("基金", {}).get("holding", 0),
            "黄金": invest["categories"].get("黄金", {}).get("holding", 0),
            "黄金账户": invest["categories"].get("黄金账户", {}).get("holding", 0),
            "股票": invest["categories"].get("股票", {}).get("holding", 0),
        }
        self._send_json(
            {
                "totals": totals,
                "investment": invest,
                "net_worth": totals["deposits"] + invest["total_holding"],
                "years": year_data,
                "allocation": allocation,
            }
        )

    def _api_monthly(self, query: dict[str, list[str]]) -> None:
        year = int((query.get("year") or ["0"])[0] or 0)
        year_id = None
        for row in repository.list_years(self.server.conn):
            if row["year"] == year:
                year_id = row["id"]
                break
        if year_id is None:
            self._send_json({"year": year, "records": [], "large_items": []})
            return
        records = [
            {"month": month, **rec}
            for month, rec in sorted(
                repository.get_monthly_records(self.server.conn, year_id).items()
            )
        ]
        self._send_json(
            {
                "year": year,
                "records": records,
                "large_items": repository.get_large_items(
                    self.server.conn, year_id
                ),
            }
        )

    def _api_holdings(self) -> None:
        self._send_json(
            {
                "holdings": repository.list_holdings(self.server.conn),
                "gold_accounts": repository.list_gold_accounts(self.server.conn),
                "summary": calculations.investment_summary(self.server.conn),
            }
        )

    def _api_reports(self) -> None:
        self._send_json({"reports": repository.list_ai_reports(self.server.conn)})

    def _api_account_detail(self, path: str) -> None:
        try:
            account_id = int(path.rsplit("/", 1)[1])
        except (ValueError, IndexError):
            self._send_json({"error": "参数错误"}, 400)
            return
        account = account_service.get_account(self.server.conn, account_id)
        if not account:
            self._send_json({"error": "账户不存在"}, 404)
            return
        self._send_json(account)

    def _api_transactions(self, query: dict[str, list[str]]) -> None:
        def first(key: str):
            values = query.get(key) or []
            return values[0] if values else None

        category_id = first("category_id")
        account_id = first("account_id")
        rows = transaction_service.get_transactions(
            self.server.conn,
            start_date=first("start_date"),
            end_date=first("end_date"),
            category_id=int(category_id) if category_id else None,
            account_id=int(account_id) if account_id else None,
            trans_type=first("type"),
            keyword=first("keyword"),
        )
        self._send_json({"transactions": rows})

    def _api_transaction_detail(self, path: str) -> None:
        try:
            trans_id = int(path.rsplit("/", 1)[1])
        except (ValueError, IndexError):
            self._send_json({"error": "参数错误"}, 400)
            return
        trans = transaction_service.get_transaction(self.server.conn, trans_id)
        if not trans:
            self._send_json({"error": "交易不存在"}, 404)
            return
        self._send_json(trans)

    def _api_summary_monthly(self, query: dict[str, list[str]]) -> None:
        try:
            year = int((query.get("year") or ["0"])[0])
            month = int((query.get("month") or ["1"])[0])
        except ValueError:
            self._send_json({"error": "参数错误"}, 400)
            return
        self._send_json(
            transaction_service.get_monthly_summary(self.server.conn, year, month)
        )

    def _api_summary_category(self, query: dict[str, list[str]]) -> None:
        start = (query.get("start_date") or [""])[0]
        end = (query.get("end_date") or [""])[0]
        trans_type = (query.get("type") or ["expense"])[0]
        self._send_json(
            transaction_service.get_category_summary(
                self.server.conn, start, end, trans_type
            )
        )

    def _api_create_account(self) -> None:
        body = self._read_json_body()
        try:
            account_id = account_service.add_account(
                self.server.conn,
                body.get("name", ""),
                body.get("type", "other"),
                body.get("institution", ""),
                float(body.get("initial_balance") or 0),
                bool(body.get("is_liability")),
                body.get("note", ""),
            )
            self.server.conn.commit()
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self._send_json({"id": account_id})

    def _api_update_account(self, path: str) -> None:
        try:
            account_id = int(path.rsplit("/", 1)[1])
        except (ValueError, IndexError):
            self._send_json({"error": "参数错误"}, 400)
            return
        body = self._read_json_body()
        account_service.update_account(self.server.conn, account_id, **body)
        self.server.conn.commit()
        self._send_json({"ok": True})

    def _api_delete_account(self, path: str) -> None:
        try:
            account_id = int(path.rsplit("/", 1)[1])
        except (ValueError, IndexError):
            self._send_json({"error": "参数错误"}, 400)
            return
        try:
            account_service.delete_account(self.server.conn, account_id)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self.server.conn.commit()
        self._send_json({"ok": True})

    def _api_create_transaction(self) -> None:
        body = self._read_json_body()
        try:
            trans_id = transaction_service.add_transaction(
                self.server.conn,
                trans_date=body.get("trans_date", ""),
                trans_type=body.get("type", "expense"),
                amount=float(body.get("amount") or 0),
                category_id=body.get("category_id"),
                account_id=int(body.get("account_id") or 0),
                to_account_id=(
                    int(body["to_account_id"])
                    if body.get("to_account_id")
                    else None
                ),
                merchant=body.get("merchant", ""),
                note=body.get("note", ""),
            )
            self.server.conn.commit()
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self._send_json({"id": trans_id})

    def _api_update_transaction(self, path: str) -> None:
        try:
            trans_id = int(path.rsplit("/", 1)[1])
        except (ValueError, IndexError):
            self._send_json({"error": "参数错误"}, 400)
            return
        body = self._read_json_body()
        transaction_service.update_transaction(self.server.conn, trans_id, **body)
        self.server.conn.commit()
        self._send_json({"ok": True})

    def _api_delete_transaction(self, path: str) -> None:
        try:
            trans_id = int(path.rsplit("/", 1)[1])
        except (ValueError, IndexError):
            self._send_json({"error": "参数错误"}, 400)
            return
        transaction_service.delete_transaction(self.server.conn, trans_id)
        self.server.conn.commit()
        self._send_json({"ok": True})


class WebService:
    """管理局域网只读 Web 服务的生命周期。"""

    def __init__(self, port: int, access_code: str, host: str = "0.0.0.0"):
        self.port = int(port)
        self.host = host
        self.access_code = access_code
        self.server: FinanceHTTPServer | None = None
        self.conn: sqlite3.Connection | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.server is not None:
            return
        self.conn = sqlite3.connect(str(paths.db_path()), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        try:
            self.server = FinanceHTTPServer(
                (self.host, self.port),
                FinanceHandler,
                self.conn,
                self.access_code,
            )
        except OSError:
            if self.conn:
                self.conn.close()
                self.conn = None
            raise
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        self.thread = None

    @property
    def running(self) -> bool:
        return self.server is not None

    def urls(self) -> dict[str, str]:
        return {
            "local": f"http://127.0.0.1:{self.port}",
            "lan": f"http://{_lan_ip()}:{self.port}",
        }


def _lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return socket.gethostbyname(socket.gethostname())
