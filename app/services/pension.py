"""退休金测算（估算），参考国家基本养老金计发办法。"""
from __future__ import annotations

from typing import Any

# 2024 年度各省（含部分计划单列市）基本养老金计发基数，单位：元/月。
PROVINCE_BASES_2024 = {
    "上海": 12307.0,
    "北京": 11883.0,
    "西藏": 11546.0,
    "广东": 9307.0,
    "天津": 9232.0,
    "青海": 8878.0,
    "江苏": 8785.0,
    "大连": 8823.0,
    "新疆": 8332.0,
    "四川": 8321.0,
    "浙江": 8310.17,
    "沈阳": 8266.0,
    "云南": 8183.0,
    "宁夏": 8202.0,
    "重庆": 8160.0,
    "海南": 8131.0,
    "内蒙古": 8105.0,
    "安徽": 7842.0,
    "长春": 7852.58,
    "福建": 7776.0,
    "陕西": 7727.0,
    "山东": 7678.0,
    "湖南": 7618.0,
    "甘肃": 7594.0,
    "菏泽": 7359.0,
    "贵州": 7272.25,
    "河北": 7265.0,
    "辽宁": 7201.0,
    "吉林": 7178.5,
    "山西": 7111.0,
    "黑龙江": 7010.0,
    "湖北": 6957.0,
    "江西": 6916.0,
    "广西": 6847.0,
    "河南": 6606.0,
}

# 个人账户养老金计发月数（官方表）。
MONTHS_TABLE = {
    50: 195, 51: 190, 52: 185, 53: 180, 54: 175,
    55: 170, 56: 164, 57: 158, 58: 152, 59: 145,
    60: 139, 61: 132, 62: 125, 63: 117, 64: 109,
    65: 101, 66: 93, 67: 84, 68: 75, 69: 65, 70: 56,
}


def contribution_years(job: dict[str, Any]) -> int:
    start = int(job.get("start_year") or 0)
    end = int(job.get("end_year") or 0)
    return max(0, end - start + 1)


def months_for_age(age: float) -> int:
    age_int = max(50, min(70, int(round(age))))
    return MONTHS_TABLE.get(age_int, 139)


def calculate_pension(
    job: dict[str, Any],
    retire_age: float = 60.0,
    personal_rate: float = 0.08,
) -> dict[str, Any]:
    """按一段工作记录估算退休后每月基本养老金。"""
    personal_rate = float(
        job.get("personal_rate", personal_rate) or personal_rate
    )
    company_rate = float(job.get("company_rate") or 0.16)
    province = (job.get("province") or "").strip()
    province_base = PROVINCE_BASES_2024.get(province, 0.0)
    monthly_base = float(job.get("monthly_base") or 0.0)
    years = contribution_years(job)
    warning = ""

    if not province:
        warning = "未填写省份，无法计算计发基数"
    elif province_base <= 0:
        warning = f"暂未收录“{province}”的 2024 计发基数，请手动核对"
    if years <= 0:
        warning = (warning + "；" if warning else "") + "缴费年限须大于 0"
    if monthly_base <= 0:
        warning = (warning + "；" if warning else "") + "月缴费基数须大于 0"

    if not warning:
        average_index = min(3.0, monthly_base / province_base)
        indexed_wage = province_base * average_index
        basic_pension = (province_base + indexed_wage) / 2.0 * years * 0.01
        months = months_for_age(retire_age)
        personal_savings = monthly_base * personal_rate * 12.0 * years
        personal_pension = personal_savings / months
        total = basic_pension + personal_pension
        if years < 15:
            warning = "累计缴费不足 15 年，通常不能按月领取职工养老金"
    else:
        basic_pension = personal_savings = personal_pension = total = 0.0
        average_index = indexed_wage = 0.0
        months = months_for_age(retire_age)

    return {
        "job": dict(job),
        "province_base": province_base,
        "contribution_years": years,
        "average_index": average_index,
        "indexed_wage": indexed_wage,
        "personal_rate": personal_rate,
        "company_rate": company_rate,
        "basic_pension": basic_pension,
        "personal_savings": personal_savings,
        "personal_pension": personal_pension,
        "total": total,
        "months": months,
        "warning": warning,
    }


def calculate_personal_pension(
    enabled: bool,
    annual: float,
    return_rate: float,
    start_year: int,
    end_year: int,
    retire_age: float = 60.0,
) -> dict[str, Any]:
    """估算个人养老金：按年缴存并模拟复利，退休后按计发月数逐月领取。"""
    annual = max(0.0, float(annual or 0.0))
    rate = max(0.0, min(1.0, float(return_rate or 0.0)))
    years = max(0, int(end_year or 0) - int(start_year or 0) + 1)
    if not enabled or annual <= 0 or years <= 0:
        return {
            "enabled": bool(enabled),
            "years": years,
            "contributed": 0.0,
            "balance": 0.0,
            "months": 0,
            "monthly": 0.0,
            "monthly_after_tax": 0.0,
            "warning": "",
        }
    if rate > 0:
        balance = annual * (((1.0 + rate) ** years - 1.0) / rate)
    else:
        balance = annual * years
    months = months_for_age(retire_age)
    monthly = balance / months if months else 0.0
    return {
        "enabled": True,
        "years": years,
        "contributed": annual * years,
        "balance": balance,
        "months": months,
        "monthly": monthly,
        "monthly_after_tax": monthly * 0.97,
        "warning": "个人养老金领取环节按 3% 税率计征个税（估算）",
    }
