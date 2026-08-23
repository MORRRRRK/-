from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.services import cloud_sync


class MockWebDAVHandler(BaseHTTPRequestHandler):
    store: dict[str, bytes] = {}

    def log_message(self, *args) -> None:
        pass

    def _send(self, code: int, body: bytes = b"") -> None:
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        if self.path in self.store:
            self._send(200)
        else:
            self._send(404)

    def do_GET(self) -> None:
        if self.path in self.store:
            self._send(200, self.store[self.path])
        else:
            self._send(404)

    def do_PUT(self) -> None:
        data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.store[self.path] = data
        self._send(201)

    def do_MKCOL(self) -> None:
        self._send(201)

    def do_PROPFIND(self) -> None:
        if self.path in self.store or self.path.endswith("/"):
            self.send_response(207)
        else:
            self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


class CloudSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        MockWebDAVHandler.store = {}
        cls.server = HTTPServer(("127.0.0.1", 0), MockWebDAVHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "finance.db"
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE t(x)")
        conn.execute("INSERT INTO t VALUES('工资')")
        conn.commit()
        conn.close()
        self.base = f"http://127.0.0.1:{self.port}/dav"

    def test_roundtrip_and_wrong_password(self) -> None:
        self.assertIn("连接成功", cloud_sync.test_connection(self.base, "u", "p"))
        result = cloud_sync.push_sync(
            self.db, self.base, "u", "p", "password123", self.tmp / "backups"
        )
        self.assertEqual(result["message"], "同步成功")
        restored = cloud_sync.pull_sync(
            self.db, self.base, "u", "p", "password123"
        )
        conn = sqlite3.connect(restored)
        self.assertEqual(conn.execute("SELECT x FROM t").fetchone()[0], "工资")
        conn.close()
        with self.assertRaises(cloud_sync.CloudSyncError):
            cloud_sync.pull_sync(self.db, self.base, "u", "p", "wrongpass")

    def test_first_sync_keeps_conflict_copy(self) -> None:
        cloud_sync.push_sync(
            self.db, self.base, "u", "p", "password123", self.tmp / "backups"
        )
        fresh_db = self.tmp / "fresh.db"
        conn = sqlite3.connect(fresh_db)
        conn.execute("CREATE TABLE t(x)")
        conn.execute("INSERT INTO t VALUES('新电脑')")
        conn.commit()
        conn.close()
        result = cloud_sync.push_sync(
            fresh_db, self.base, "u", "p", "password123", self.tmp / "backups"
        )
        self.assertTrue(result["conflict_saved"])
        self.assertTrue(Path(result["conflict_path"]).exists())


if __name__ == "__main__":
    unittest.main()
