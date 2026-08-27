from __future__ import annotations

import json

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core import repository
from ...services import account_service, llm
from ..widgets import make_button

SYSTEM_PROMPT = (
    "你是个人财务与投资分析助手。你只能回答与个人财务、工资、存款、"
    "资产配置、投资理财、持仓分析、买卖建议、风险管理相关的问题；"
    "与这些无关的问题请礼貌拒绝并引导回财务话题。回答使用中文，"
    "必须结合用户提供的持仓数据，不要编造数字，不给确定收益承诺，"
    "涉及买卖时给出风险提示。"
)

REPORT_PERIODS = [
    ("日报", "日"),
    ("周报", "周"),
    ("月报", "月"),
    ("季报", "季"),
    ("年报", "年"),
]


class ChatWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.messages = messages

    def run(self) -> None:
        try:
            reply = llm.chat_completion(
                self.base_url, self.api_key, self.model, self.messages
            )
        except llm.LlmError as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(reply)


class HoldingsChatPanel(QWidget):
    """持仓智能分析问答：保留历史与上下文压缩，使用智能报告的大模型配置。"""

    def __init__(self, conn, on_change=None):
        super().__init__()
        self.conn = conn
        self.on_change = on_change
        self._worker: ChatWorker | None = None
        self._compress_worker: ChatWorker | None = None
        self._compress_after_reply = False
        self._build()
        self._render_history()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("智能分析持仓")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        report_row = QHBoxLayout()
        report_row.setSpacing(4)
        for label, _period in REPORT_PERIODS:
            button = make_button(label)
            button.setFixedWidth(52)
            button.clicked.connect(
                lambda _=False, period=_period: self._generate_report(period)
            )
            report_row.addWidget(button)
        report_row.addStretch(1)
        layout.addLayout(report_row)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        layout.addWidget(self.browser, 1)

        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("输入持仓/投资问题，回车发送")
        self.input_edit.returnPressed.connect(self._send_input)
        self.send_button = make_button("发送", primary=True)
        self.send_button.clicked.connect(self._send_input)
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("fieldLabel")
        layout.addWidget(self.status_label)

    def _llm_config(self) -> tuple[str, str, str] | None:
        base_url = repository.get_setting(
            self.conn, "llm_base_url", llm.DEFAULT_BASE_URL
        ).strip()
        api_key = repository.get_setting(self.conn, "llm_api_key", "").strip()
        model = repository.get_setting(
            self.conn, "llm_model", llm.DEFAULT_MODEL
        ).strip()
        if not api_key:
            QMessageBox.information(
                self,
                "需要配置",
                "请先在“设置 > 智能报告”中填写大模型 API Key。",
            )
            return None
        return base_url, api_key, model

    def _send_input(self) -> None:
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        self._ask(text)

    def _generate_report(self, period: str) -> None:
        self._compress_after_reply = True
        data = self._holdings_context()
        self._ask(
            f"请生成一份{period}度持仓分析报告。要求包含：持仓类型与账户分布、"
            "各类资产比例、净值与收益变化、投资组合健康度评价、"
            "该不该买卖的建议以及风险提示。当前持仓数据：\n"
            + json.dumps(data, ensure_ascii=False, indent=2)
        )

    def _ask(self, question: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        config = self._llm_config()
        if config is None:
            return
        repository.add_chat_message(self.conn, "user", question)
        self.conn.commit()
        self._render_history()
        self._set_busy(True)
        self._worker = ChatWorker(
            config[0], config[1], config[2], self._build_messages(question), self
        )
        self._worker.finished.connect(self._on_reply)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _build_messages(self, question: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        summary = repository.get_chat_summary(self.conn)
        if summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"历史对话压缩摘要：\n{summary}",
                }
            )
        recent = repository.list_chat_messages(self.conn, limit=20)
        for message in recent:
            role = "assistant" if message["role"] == "assistant" else "user"
            messages.append({"role": role, "content": message["content"]})
        if not any(message["content"] == question for message in recent):
            messages.append({"role": "user", "content": question})
        return messages

    def _on_reply(self, reply: str) -> None:
        self._worker = None
        self._save_reply(reply)
        self._render_history()
        self._set_busy(False)
        if self._compress_after_reply:
            self._compress_after_reply = False
            self._compress_history()

    def _on_failed(self, message: str) -> None:
        self._worker = None
        self._set_busy(False)
        self.status_label.setText(message)

    def _save_reply(self, reply: str) -> None:
        repository.add_chat_message(self.conn, "assistant", reply)
        self.conn.commit()

    def _compress_history(self) -> None:
        """把已有问答压缩成滚动摘要，后续对话只携带摘要与最近消息。"""
        config = self._llm_config()
        if config is None:
            return
        messages = repository.list_chat_messages(self.conn)
        if not messages:
            return
        content = "\n\n".join(
            f"{m['role']}：{m['content']}" for m in messages
        )
        prompt = (
            "请把下面的个人财务问答历史压缩成 500 字以内的中文要点摘要，"
            "保留关键结论、数字、建议和用户偏好；不要添加新信息。\n\n" + content
        )
        self._compress_worker = ChatWorker(
            config[0], config[1], config[2],
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            self,
        )
        self._compress_worker.finished.connect(self._on_compressed)
        self._compress_worker.failed.connect(
            lambda message: self.status_label.setText(message)
        )
        self._compress_worker.start()

    def _on_compressed(self, summary: str) -> None:
        self._compress_worker = None
        repository.save_chat_summary(self.conn, summary)
        self.conn.commit()
        self.status_label.setText("历史对话已压缩，上下文已更新")

    def _set_busy(self, busy: bool) -> None:
        self.send_button.setEnabled(not busy)
        self.input_edit.setEnabled(not busy)
        self.status_label.setText("正在生成…" if busy else "")

    def _holdings_context(self) -> dict:
        accounts = {
            a["id"]: a["name"]
            for a in account_service.get_accounts(self.conn)
        }
        holdings = []
        for holding in repository.list_holdings(self.conn):
            item = dict(holding)
            item["account"] = accounts.get(holding.get("account_id"), "")
            holdings.append(item)
        gold = []
        for account in repository.list_gold_accounts(self.conn):
            item = dict(account)
            item["account"] = accounts.get(account.get("account_id"), "")
            gold.append(item)
        return {
            "holdings": holdings,
            "gold_accounts": gold,
        }

    def _render_history(self) -> None:
        messages = repository.list_chat_messages(self.conn)
        if not messages:
            self.browser.setMarkdown(
                "这里是持仓智能分析问答，可以问：\n\n"
                "- 我的持仓健康度如何？\n"
                "- 基金/股票该不该继续买入？\n"
                "- 帮我生成一份周报/月报/季报/年报。"
            )
            return
        lines = []
        for message in messages:
            role = "你" if message["role"] == "user" else "助手"
            lines.append(f"**{role}**：\n\n{message['content']}\n\n---\n")
        self.browser.setMarkdown("\n".join(lines))
        self.browser.verticalScrollBar().setValue(
            self.browser.verticalScrollBar().maximum()
        )

    def refresh(self) -> None:
        self._render_history()
