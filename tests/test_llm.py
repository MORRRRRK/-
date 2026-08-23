from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.services import llm


class MockLlmHandler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = json.dumps(
            {"choices": [{"message": {"content": "# 测试报告\n内容"}}]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LlmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), MockLlmHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_chat_completion_and_url(self) -> None:
        self.assertEqual(
            llm.normalize_chat_url("https://api.example.com/v1"),
            "https://api.example.com/v1/chat/completions",
        )
        content = llm.chat_completion(
            f"http://127.0.0.1:{self.port}/v1",
            "key",
            "model",
            [{"role": "user", "content": "hi"}],
        )
        self.assertIn("测试报告", content)


if __name__ == "__main__":
    unittest.main()
