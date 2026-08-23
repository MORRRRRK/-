"""OpenAI 兼容大模型接口与财务报告生成。"""
from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from typing import Any

from ..core import repository


class LlmError(Exception):
    pass


DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


def normalize_chat_url(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise LlmError("请先填写大模型接口地址")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: int = 120,
) -> str:
    if not api_key:
        raise LlmError("请先填写大模型 API Key")
    if not model:
        raise LlmError("请先填写模型名称")
    url = normalize_chat_url(base_url)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 3000,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except OSError:
            pass
        raise LlmError(f"接口请求失败（HTTP {exc.code}）{detail}") from exc
    except urllib.error.URLError as exc:
        raise LlmError(f"网络连接失败：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise LlmError("接口返回内容无法解析") from exc
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError("接口返回格式异常，未找到报告内容") from exc


def test_connection(base_url: str, api_key: str, model: str) -> str:
    reply = chat_completion(
        base_url,
        api_key,
        model,
        [{"role": "user", "content": "请只回复 OK"}],
        timeout=30,
    )
    return reply[:50] if reply else "OK"


def build_financial_context(conn: sqlite3.Connection) -> dict[str, Any]:
    years = repository.list_years(conn)
    monthly = []
    for year in years:
        records = repository.get_monthly_records(conn, year["id"])
        for month in range(1, 13):
            if month in records:
                monthly.append(
                    {
                        "year": year["year"],
                        **records[month],
                    }
                )
    large_items = []
    for year in years:
        for item in repository.get_large_items(conn, year["id"]):
            large_items.append({"year": year["year"], **item})
    insurance = []
    for year in years:
        params = repository.get_insurance_params(conn, year["id"])
        if params:
            insurance.append(
                {
                    "year": year["year"],
                    "params": params,
                    "items": repository.list_insurance_items(conn, year["id"]),
                }
            )
    return {
        "totals": calculations_totals(conn),
        "investment_summary": calculations_investment(conn),
        "years": [{"year": y["year"], "summary": calculations_year(conn, y["id"])} for y in years],
        "monthly_records": monthly,
        "large_items": large_items,
        "holdings": repository.list_holdings(conn),
        "gold_accounts": repository.list_gold_accounts(conn),
        "goals": repository.list_goals(conn),
        "pension_jobs": repository.list_pension_jobs(conn),
        "insurance_params": insurance,
    }


def calculations_totals(conn: sqlite3.Connection) -> dict[str, float]:
    from .calculations import totals

    return totals(conn)


def calculations_investment(conn: sqlite3.Connection) -> dict[str, Any]:
    from .calculations import investment_summary

    return investment_summary(conn)


def calculations_year(conn: sqlite3.Connection, year_id: int) -> dict[str, Any]:
    from .calculations import year_summary

    return year_summary(conn, year_id)


def generate_report_text(
    context: dict[str, Any],
    report_type: str,
    period_label: str,
    base_url: str,
    api_key: str,
    model: str,
) -> str:
    type_names = {
        "year": "年度财务报告",
        "month": "月度财务报告",
        "holding": "持仓分析报告",
        "custom": "自定义财务报告",
    }
    title = f"{period_label} {type_names.get(report_type, '财务报告')}"
    data_json = json.dumps(context, ensure_ascii=False, indent=2)
    system_prompt = (
        "你是一位资深中文个人财务规划师。请根据用户提供的完整财务数据生成专业、"
        "客观、可执行的财务分析报告。报告必须使用 Markdown 格式，包含：总体评价、"
        "收入与支出分析、储蓄与现金流、投资与资产配置、风险提示、改进建议。"
        "请结合实际数字，不要编造数据，不要承诺收益。"
    )
    user_prompt = (
        f"报告标题：{title}\n报告类型：{report_type}\n"
        f"报告期间：{period_label}\n\n完整财务数据如下：\n{data_json}"
    )
    return chat_completion(
        base_url,
        api_key,
        model,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
