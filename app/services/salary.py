"""工资方案序列化与计算辅助。"""
from __future__ import annotations

import json
from typing import Any

from . import calculations, tax


def default_params() -> dict[str, Any]:
    return {
        "base": 0.0,
        "monthly_salary": 0.0,
        "thirteenth_month_months": 1.0,
        "year_end_bonus_months": 1.0,
        "thirteenth_coefficient": 1.0,
        "thirteenth_frequency": "annual",
        "year_end_bonus_coefficient": 1.0,
        "year_end_bonus_frequency": "annual",
        "thirteenth_amount": 0.0,
        "year_end_bonus_amount": 0.0,
        "housing_subsidy": 0.0,
        "housing_fund_personal_rate": 0.0,
        "housing_fund_company_rate": 0.0,
        "pension_personal_rate": 0.0,
        "pension_company_rate": 0.0,
        "medical_personal_rate": 0.0,
        "medical_company_rate": 0.0,
        "big_medical_personal": 0.0,
        "big_medical_company": 0.0,
        "maternity_personal_rate": 0.0,
        "maternity_company_rate": 0.0,
        "injury_personal_rate": 0.0,
        "injury_company_rate": 0.0,
        "unemployment_personal_rate": 0.0,
        "unemployment_company_rate": 0.0,
    }


def default_payload(year: int = 2026) -> dict[str, Any]:
    return {
        "year": int(year),
        "params": default_params(),
        "items": [],
        "salary_items": [],
        "tax_params": tax.default_tax_params(),
    }


def decode_payload(payload: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(payload, dict):
        data = payload
    elif payload:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            data = {}
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data


def params(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload or {}
    result = default_params()
    result.update(data.get("params") or {})
    return result


def items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = payload or {}
    return [dict(item) for item in (data.get("items") or [])]


def salary_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = payload or {}
    return [dict(item) for item in (data.get("salary_items") or [])]


def tax_params(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload or {}
    result = tax.default_tax_params()
    result.update(data.get("tax_params") or {})
    return result


def social_result(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload or {}
    return {
        "has_params": bool(data.get("params")),
        **calculations.social_insurance_from_data(
            params(payload),
            items(payload),
            salary_items(payload),
        ),
    }
