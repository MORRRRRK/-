"""OpenAI 兼容大模型接口与财务报告生成。"""
from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from typing import Any

from ..core import repository
from . import salary as salary_service


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


def build_financial_context(
    conn: sqlite3.Connection,
    report_type: str = "custom",
    start: str = "",
    end: str = "",
) -> dict[str, Any]:
    """按报告类型收集对应数据源的最新结果。"""
    if report_type == "bill":
        return _bill_context(conn, start, end)
    if report_type == "salary":
        return _salary_context(conn, start, end)
    if report_type == "planning":
        return _planning_context(conn, start, end)
    return _custom_context(conn, start, end)


def _bill_context(
    conn: sqlite3.Connection, start: str = "", end: str = ""
) -> dict[str, Any]:
    from . import transaction_service

    transactions = (
        transaction_service.get_transactions(conn, start, end)
        if start and end
        else []
    )
    income = sum(
        float(t["amount"] or 0)
        for t in transactions
        if t["type"] == "income"
    )
    expense = sum(
        float(t["amount"] or 0)
        for t in transactions
        if t["type"] == "expense"
    )
    categories = (
        transaction_service.get_category_summary(conn, start, end, "expense")
        if start and end
        else []
    )
    accounts = {}
    for transaction in transactions:
        name = str(transaction.get("account_id") or "")
        accounts[name] = accounts.get(name, 0.0) + float(transaction["amount"] or 0)
    years = repository.list_years(conn)
    deposits = []
    for year in years:
        records = repository.get_monthly_records(conn, year["id"])
        total = sum(
            float(rec.get("forced_deposit", 0.0) or 0.0)
            for rec in records.values()
        )
        if total:
            deposits.append({"year": year["year"], "forced_deposit": total})
    return {
        "period": {"start": start, "end": end},
        "income_total": income,
        "expense_total": expense,
        "balance": income - expense,
        "transaction_count": len(transactions),
        "expense_categories": categories,
        "income_transactions": [
            t for t in transactions if t["type"] == "income"
        ],
        "expense_transactions": [
            t for t in transactions if t["type"] == "expense"
        ],
        "forced_deposits": deposits,
    }


def _salary_context(
    conn: sqlite3.Connection, start: str = "", end: str = ""
) -> dict[str, Any]:
    from . import tax

    year = int(start[:4]) if len(start or "") >= 4 else 0
    profiles = repository.list_salary_profiles(conn)
    result = []
    for profile in profiles:
        payload = salary_service.decode_payload(profile.get("payload"))
        profile_year = int(payload.get("year") or profile.get("year") or 0)
        if year and profile_year != year:
            continue
        social = salary_service.social_result(payload)
        schedule = tax.monthly_schedule_profile(
            conn, profile_year or year or 2026, payload
        )
        result.append(
            {
                "name": profile.get("name", ""),
                "year": profile_year,
                "salary": social,
                "tax_summary": schedule,
                "tax_params": salary_service.tax_params(payload),
            }
        )
    return {
        "period": {"start": start, "end": end},
        "salary_profiles": result,
    }


def _planning_context(
    conn: sqlite3.Connection, start: str = "", end: str = ""
) -> dict[str, Any]:
    from . import account_service, planning

    totals = calculations_totals(conn)
    invest = calculations_investment(conn)
    accounts = account_service.get_account_summary(conn)
    goals = []
    for goal in repository.list_goals(conn):
        months = 36.0
        try:
            from datetime import date

            target = date.fromisoformat(str(goal.get("target_date") or ""))
            months = max(0.0, (target - date.today()).days / 30.4375)
        except (TypeError, ValueError):
            pass
        monthly = planning.required_monthly_saving(
            float(goal.get("target_amount") or 0),
            float(goal.get("current_amount") or 0),
            months,
            0.03,
        )
        goals.append(
            {
                **goal,
                "months_left": round(months, 1),
                "required_monthly_saving": round(monthly, 2),
            }
        )
    net_worth = totals["deposits"] + invest["total_holding"]
    projection = planning.project_net_worth(
        net_worth, 3000.0, 0.03, 5.0
    )
    return {
        "period": {"start": start, "end": end},
        "totals": totals,
        "investment_summary": invest,
        "account_summary": accounts,
        "net_worth": net_worth,
        "goals": goals,
        "pension_jobs": repository.list_pension_jobs(conn),
        "projection_5y_3pct_monthly3000": projection,
    }


def _custom_context(
    conn: sqlite3.Connection, start: str = "", end: str = ""
) -> dict[str, Any]:
    years = repository.list_years(conn)
    monthly = []
    for year in years:
        records = repository.get_monthly_records(conn, year["id"])
        for month in range(1, 13):
            if month in records:
                monthly.append(
                    {"year": year["year"], **records[month]}
                )
    insurance = []
    for profile in repository.list_salary_profiles(conn):
        payload = salary_service.decode_payload(profile.get("payload"))
        insurance.append(
            {
                "profile_id": profile["id"],
                "name": profile["name"],
                "year": profile["year"],
                "params": salary_service.params(payload),
                "items": salary_service.items(payload),
                "salary_items": salary_service.salary_items(payload),
                "tax_params": salary_service.tax_params(payload),
            }
        )
    return {
        "period": {"start": start, "end": end},
        "totals": calculations_totals(conn),
        "investment_summary": calculations_investment(conn),
        "years": [
            {
                "year": y["year"],
                "summary": calculations_year(conn, y["id"]),
            }
            for y in years
        ],
        "monthly_records": monthly,
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
        "bill": "账单报告",
        "salary": "工资报告",
        "planning": "资产规划建议",
        "custom": "综合财务报告",
    }
    title = f"{period_label} {type_names.get(report_type, '财务报告')}"
    data_json = json.dumps(context, ensure_ascii=False, indent=2)
    prompts = {
        "bill": (
            "你是一位资深中文个人账单分析师。请根据用户提供的记账流水数据生成"
            "专业、客观、可执行的账单分析报告。报告必须使用 Markdown 格式，包含："
            "收支总体评价、收入来源、支出分类占比、异常大额支出、储蓄与现金流、"
            "下阶段预算建议。请结合实际数字，不要编造数据。"
        ),
        "salary": (
            "你是一位资深中文薪酬与个税顾问。请根据工资管理中的工资详情、"
            "N险N金、专项附加扣除与个税计算结果生成报告。报告必须使用 Markdown 格式，"
            "包含：工资结构、五险一金负担、税前税后收入、个税合理性、"
            "年终奖计税方式建议、可优化方向。请结合实际数字，不要编造数据。"
        ),
        "planning": (
            "你是一位资深中文个人资产规划师。请根据资产总览、储蓄目标与资产规划"
            "最新结果生成建议。报告必须使用 Markdown 格式，包含：净资产现状、"
            "存款与投资结构、储蓄目标可行性、每月需存金额建议、资产配置与风险提示、"
            "下一步行动清单。不要承诺收益。"
        ),
        "custom": (
            "你是一位资深中文个人财务规划师。请根据用户提供的完整财务数据生成专业、"
            "客观、可执行的财务分析报告。报告必须使用 Markdown 格式，包含：总体评价、"
            "收入与支出分析、储蓄与现金流、投资与资产配置、风险提示、改进建议。"
            "请结合实际数字，不要编造数据，不要承诺收益。"
        ),
    }
    system_prompt = prompts.get(
        report_type, prompts["custom"]
    )
    user_prompt = (
        f"报告标题：{title}\n报告类型：{report_type}\n"
        f"报告期间：{period_label}\n\n财务数据如下：\n{data_json}"
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
