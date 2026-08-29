"""个人所得税估算：全年模拟与月度累计预扣预缴。"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..core import repository
from . import calculations

STANDARD_DEDUCTION_MONTHLY = 5000.0

# 综合所得年度税率表：上限、税率、速算扣除数。
TAX_BRACKETS = [
    (36000.0, 0.03, 0.0),
    (144000.0, 0.10, 2520.0),
    (300000.0, 0.20, 16920.0),
    (420000.0, 0.25, 31920.0),
    (660000.0, 0.30, 52920.0),
    (960000.0, 0.35, 85920.0),
    (float("inf"), 0.45, 181920.0),
]

# 全年一次性奖金单独计税的月度税率表（奖金/12 查档）。
BONUS_BRACKETS = [
    (3000.0, 0.03, 0.0),
    (12000.0, 0.10, 210.0),
    (25000.0, 0.20, 1410.0),
    (35000.0, 0.25, 2660.0),
    (55000.0, 0.30, 4410.0),
    (80000.0, 0.35, 7160.0),
    (float("inf"), 0.45, 15160.0),
]

# 常见直辖市、省会城市与计划单列市，住房租金专项扣除按 1500 元/月。
RENT_CITY_1500 = {
    "北京", "上海", "广州", "深圳", "天津", "重庆",
    "成都", "杭州", "武汉", "西安", "南京", "沈阳",
    "大连", "青岛", "宁波", "厦门", "哈尔滨", "长春",
    "济南", "郑州", "长沙", "福州", "南昌", "合肥",
    "昆明", "太原", "贵阳", "南宁", "乌鲁木齐", "兰州",
    "银川", "西宁", "海口", "石家庄",
}

# 省/直辖市 -> 城市列表（城市名, 住房租金扣除档位）。
PROVINCE_CITIES: dict[str, list[tuple[str, float]]] = {
    "北京市": [("北京市", 1500.0)],
    "天津市": [("天津市", 1500.0)],
    "上海市": [("上海市", 1500.0)],
    "重庆市": [("重庆市", 1500.0)],
    "河北省": [
        ("石家庄市", 1500.0), ("唐山市", 1100.0), ("秦皇岛市", 1100.0),
        ("邯郸市", 1100.0), ("保定市", 1100.0), ("张家口市", 800.0),
        ("承德市", 800.0), ("廊坊市", 1100.0), ("沧州市", 1100.0),
    ],
    "山西省": [
        ("太原市", 1500.0), ("大同市", 1100.0), ("阳泉市", 800.0),
        ("长治市", 800.0), ("晋中市", 800.0), ("临汾市", 800.0),
    ],
    "内蒙古自治区": [
        ("呼和浩特市", 1500.0), ("包头市", 1100.0), ("赤峰市", 1100.0),
        ("通辽市", 800.0),
    ],
    "辽宁省": [
        ("沈阳市", 1500.0), ("大连市", 1500.0), ("鞍山市", 1100.0),
        ("抚顺市", 800.0), ("本溪市", 800.0), ("锦州市", 800.0),
    ],
    "吉林省": [
        ("长春市", 1500.0), ("吉林市", 1100.0), ("四平市", 800.0),
    ],
    "黑龙江省": [
        ("哈尔滨市", 1500.0), ("齐齐哈尔市", 1100.0), ("大庆市", 1100.0),
        ("牡丹江市", 800.0),
    ],
    "江苏省": [
        ("南京市", 1500.0), ("苏州市", 1100.0), ("无锡市", 1100.0),
        ("常州市", 1100.0), ("南通市", 1100.0), ("徐州市", 1100.0),
        ("扬州市", 800.0), ("盐城市", 800.0),
    ],
    "浙江省": [
        ("杭州市", 1500.0), ("宁波市", 1500.0), ("温州市", 1100.0),
        ("嘉兴市", 1100.0), ("绍兴市", 1100.0), ("金华市", 800.0),
        ("台州市", 1100.0),
    ],
    "安徽省": [
        ("合肥市", 1500.0), ("芜湖市", 1100.0), ("蚌埠市", 800.0),
        ("安庆市", 800.0),
    ],
    "福建省": [
        ("福州市", 1500.0), ("厦门市", 1500.0), ("泉州市", 1100.0),
        ("漳州市", 800.0),
    ],
    "江西省": [
        ("南昌市", 1500.0), ("赣州市", 1100.0), ("九江市", 800.0),
    ],
    "山东省": [
        ("济南市", 1500.0), ("青岛市", 1500.0), ("烟台市", 1100.0),
        ("潍坊市", 1100.0), ("淄博市", 1100.0), ("临沂市", 1100.0),
        ("济宁市", 800.0),
    ],
    "河南省": [
        ("郑州市", 1500.0), ("洛阳市", 1100.0), ("开封市", 800.0),
        ("南阳市", 1100.0), ("新乡市", 800.0),
    ],
    "湖北省": [
        ("武汉市", 1500.0), ("宜昌市", 1100.0), ("襄阳市", 1100.0),
        ("荆州市", 800.0),
    ],
    "湖南省": [
        ("长沙市", 1500.0), ("株洲市", 1100.0), ("湘潭市", 1100.0),
        ("衡阳市", 800.0),
    ],
    "广东省": [
        ("广州市", 1500.0), ("深圳市", 1500.0), ("珠海市", 1500.0),
        ("佛山市", 1100.0), ("东莞市", 1100.0), ("中山市", 1100.0),
        ("惠州市", 1100.0), ("汕头市", 1100.0), ("湛江市", 1100.0),
        ("江门市", 800.0),
    ],
    "广西壮族自治区": [
        ("南宁市", 1500.0), ("柳州市", 1100.0), ("桂林市", 1100.0),
    ],
    "海南省": [
        ("海口市", 1500.0), ("三亚市", 1500.0),
    ],
    "四川省": [
        ("成都市", 1500.0), ("绵阳市", 1100.0), ("德阳市", 800.0),
        ("宜宾市", 800.0), ("南充市", 800.0),
    ],
    "贵州省": [
        ("贵阳市", 1500.0), ("遵义市", 1100.0), ("六盘水市", 800.0),
    ],
    "云南省": [
        ("昆明市", 1500.0), ("曲靖市", 800.0), ("大理市", 800.0),
        ("丽江市", 800.0),
    ],
    "西藏自治区": [
        ("拉萨市", 1500.0), ("日喀则市", 800.0),
    ],
    "陕西省": [
        ("西安市", 1500.0), ("宝鸡市", 1100.0), ("咸阳市", 1100.0),
        ("榆林市", 800.0),
    ],
    "甘肃省": [
        ("兰州市", 1500.0), ("天水市", 800.0), ("酒泉市", 800.0),
    ],
    "青海省": [("西宁市", 1500.0)],
    "宁夏回族自治区": [
        ("银川市", 1500.0), ("石嘴山市", 800.0),
    ],
    "新疆维吾尔自治区": [
        ("乌鲁木齐市", 1500.0), ("克拉玛依市", 800.0),
    ],
}

_CITY_TIER: dict[str, float] = {
    city: tier
    for cities in PROVINCE_CITIES.values()
    for city, tier in cities
}


def income_tax(taxable: float) -> float:
    """按年度累计应纳税所得额计算综合所得个税。"""
    taxable = max(0.0, float(taxable))
    for upper, rate, quick in TAX_BRACKETS:
        if taxable <= upper:
            return max(0.0, taxable * rate - quick)
    return max(0.0, taxable * TAX_BRACKETS[-1][1] - TAX_BRACKETS[-1][2])


def annual_bonus_tax(bonus: float) -> float:
    """年终奖单独计税：总额/12 查找月度税率与速算扣除数。"""
    bonus = max(0.0, float(bonus))
    if bonus <= 0:
        return 0.0
    monthly = bonus / 12.0
    for upper, rate, quick in BONUS_BRACKETS:
        if monthly <= upper:
            return max(0.0, bonus * rate - quick)
    return max(0.0, bonus * BONUS_BRACKETS[-1][1] - BONUS_BRACKETS[-1][2])


def rent_tier_for_city(city: str) -> float:
    """按城市自动识别住房租金扣除档位，无法识别时返回 0。"""
    city = str(city or "").strip()
    if not city:
        return 0.0
    if city in _CITY_TIER:
        return _CITY_TIER[city]
    normalized = city.rstrip("市") + "市"
    if normalized in _CITY_TIER:
        return _CITY_TIER[normalized]
    return 0.0


def special_deductions_monthly(params: dict[str, Any] | None) -> float:
    """专项附加扣除月合计（大病医疗单独按年计算）。"""
    params = params or {}
    rent_tier = float(params.get("rent_tier") or 0.0)
    elderly_option = str(params.get("elderly_option") or "only_child")
    if elderly_option == "shared":
        elderly = 1500.0
    elif elderly_option == "only_child":
        elderly = 3000.0
    else:
        elderly = 0.0
    children = int(params.get("children_education_count") or 0) * 2000.0
    infant = int(params.get("infant_care_count") or 0) * 2000.0
    continuing = 400.0 if int(params.get("continuing_education") or 0) else 0.0
    mortgage = 1000.0 if int(params.get("mortgage_interest") or 0) else 0.0
    custom = float(params.get("custom_deduction") or 0.0)
    personal_pension = min(
        12000.0, float(params.get("personal_pension_annual") or 0.0)
    ) / 12.0
    return (
        rent_tier
        + elderly
        + children
        + infant
        + continuing
        + mortgage
        + custom
        + personal_pension
    )


def default_tax_params() -> dict[str, Any]:
    return {
        "rent_city": "",
        "rent_province": "",
        "rent_district": "",
        "rent_tier": 0.0,
        "elderly_option": "only_child",
        "children_education_count": 0,
        "infant_care_count": 0,
        "continuing_education": 0,
        "mortgage_interest": 0,
        "severe_illness_annual": 0.0,
        "bonus_tax_method": "separate",
        "custom_deduction": 0.0,
        "personal_pension_annual": 0.0,
    }


def simulate_annual(
    social_result: dict[str, Any], tax_params: dict[str, Any] | None
) -> dict[str, Any]:
    """按工资参数模拟全年税后收入与逐月预扣表。"""
    personal_monthly = float(social_result.get("personal_total") or 0.0)
    total_salary = float(social_result.get("total_salary") or 0.0)
    bonus_annual = float(social_result.get("bonus_annual") or 0.0)
    tax_params = tax_params or default_tax_params()
    method = str(tax_params.get("bonus_tax_method") or "separate")
    special_monthly = special_deductions_monthly(tax_params)
    severe_annual = float(tax_params.get("severe_illness_annual") or 0.0)
    special_annual = special_monthly * 12.0 + severe_annual

    combined = method != "separate"
    base_taxable = total_salary - personal_monthly * 12.0 - (
        STANDARD_DEDUCTION_MONTHLY * 12.0
    ) - special_annual
    if combined:
        taxable = base_taxable
        wage_tax = income_tax(taxable)
        bonus_tax = 0.0
    else:
        taxable = base_taxable - bonus_annual
        wage_tax = income_tax(taxable)
        bonus_tax = annual_bonus_tax(bonus_annual)
    total_tax = wage_tax + bonus_tax
    net_income = total_salary - personal_monthly * 12.0 - total_tax

    schedule = []
    cumulative_income = 0.0
    cumulative_deduction = 0.0
    cumulative_insurance = 0.0
    paid_before = 0.0
    for month, gross in enumerate(
        _simulation_monthly_gross(social_result, combined), start=1
    ):
        cumulative_income += gross
        cumulative_deduction += STANDARD_DEDUCTION_MONTHLY + special_monthly
        cumulative_insurance += personal_monthly
        taxable_cumulative = max(
            0.0,
            cumulative_income - cumulative_deduction - cumulative_insurance,
        )
        cumulative_wage_tax = income_tax(taxable_cumulative)
        if month == 12 and not combined:
            current_total = cumulative_wage_tax + bonus_tax
        else:
            current_total = cumulative_wage_tax
        month_tax = max(0.0, current_total - paid_before)
        paid_before = current_total
        schedule.append(
            {
                "month": month,
                "gross": gross,
                "personal_insurance": personal_monthly,
                "taxable_income": taxable_cumulative,
                "cumulative_tax": cumulative_wage_tax,
                "month_tax": month_tax,
                "net_income": gross - personal_monthly - month_tax,
            }
        )

    return {
        "comprehensive_income": total_salary,
        "annual_bonus": bonus_annual,
        "special_monthly": special_monthly,
        "severe_illness_annual": severe_annual,
        "taxable_income": max(0.0, taxable),
        "wage_tax": wage_tax,
        "bonus_tax": bonus_tax,
        "total_tax": total_tax,
        "net_income": net_income,
        "monthly_net": net_income / 12.0,
        "monthly_schedule": schedule,
        "bonus_method": method,
    }


def _simulation_monthly_gross(
    social_result: dict[str, Any], include_bonus: bool
) -> list[float]:
    """把年度工资拆到 12 个月：月发每月、季发 3/6/9/12 月、年发和 13薪/年终奖放 12 月。"""
    params = social_result.get("params") or {}
    base = float(params.get("monthly_salary") or 0.0)
    gross = [base] * 12
    for item in social_result.get("salary_items") or []:
        amount = float(item.get("amount") or 0.0)
        frequency = str(item.get("frequency") or "monthly")
        if frequency == "monthly":
            for index in range(12):
                gross[index] += amount
        elif frequency == "quarterly":
            for index in (2, 5, 8, 11):
                gross[index] += amount
        else:
            gross[11] += amount
    gross[11] += float(social_result.get("thirteen_annual") or 0.0)
    if include_bonus:
        gross[11] += float(social_result.get("bonus_annual") or 0.0)
    return gross


def monthly_schedule_actual(
    conn: sqlite3.Connection,
    year_id: int,
    method_override: str | None = None,
) -> dict[str, Any]:
    """按实际月度流水计算累计预扣预缴，返回逐月明细与年度汇总。"""
    social = calculations.social_insurance(conn, year_id)
    tax_params = repository.get_tax_params(conn, year_id) or default_tax_params()
    return _monthly_schedule(
        conn, year_id, social, tax_params, method_override
    )


def monthly_schedule_profile(
    conn: sqlite3.Connection,
    year: int,
    payload: dict[str, Any],
    method_override: str | None = None,
) -> dict[str, Any]:
    """按工资方案 payload 与实际月度流水计算累计预扣预缴。"""
    from . import salary as salary_service

    social = salary_service.social_result(payload)
    tax_params = salary_service.tax_params(payload)
    year_id = repository.ensure_year(conn, year)
    return _monthly_schedule(
        conn, year_id, social, tax_params, method_override
    )


def _monthly_schedule(
    conn: sqlite3.Connection,
    year_id: int,
    social: dict[str, Any],
    tax_params: dict[str, Any],
    method_override: str | None = None,
) -> dict[str, Any]:
    personal_monthly = (
        float(social.get("personal_total") or 0.0)
        if social.get("has_params")
        else 0.0
    )
    method = (
        method_override
        or str(tax_params.get("bonus_tax_method") or "separate")
    )
    special_monthly = special_deductions_monthly(tax_params)
    records = repository.get_monthly_records(conn, year_id)

    combined = method != "separate"
    total_bonus = sum(
        float(rec.get("year_end_bonus") or 0.0) for rec in records.values()
    )
    bonus_tax = annual_bonus_tax(total_bonus) if not combined else 0.0

    schedule = []
    cumulative_income = 0.0
    cumulative_deduction = 0.0
    cumulative_insurance = 0.0
    paid_before = 0.0
    total_income = 0.0
    for month in range(1, 13):
        rec = records.get(month, {})
        bonus_part = float(rec.get("year_end_bonus") or 0.0)
        income = (
            float(rec.get("salary") or 0.0)
            + (bonus_part if combined else 0.0)
            + float(rec.get("subsidies") or 0.0)
        )
        gross = (
            float(rec.get("salary") or 0.0)
            + bonus_part
            + float(rec.get("subsidies") or 0.0)
        )
        total_income += gross
        cumulative_income += income
        cumulative_deduction += STANDARD_DEDUCTION_MONTHLY + special_monthly
        cumulative_insurance += personal_monthly
        taxable_cumulative = max(
            0.0,
            cumulative_income - cumulative_deduction - cumulative_insurance,
        )
        cumulative_wage_tax = income_tax(taxable_cumulative)
        if month == 12 and not combined:
            current_total = cumulative_wage_tax + bonus_tax
        else:
            current_total = cumulative_wage_tax
        month_tax = max(0.0, current_total - paid_before)
        paid_before = current_total
        schedule.append(
            {
                "month": month,
                "gross": gross,
                "personal_insurance": personal_monthly,
                "special_deduction": special_monthly,
                "taxable_income": taxable_cumulative,
                "cumulative_tax": cumulative_wage_tax,
                "paid_before": paid_before,
                "month_tax": month_tax,
                "net_income": gross - personal_monthly - month_tax,
            }
        )

    wage_tax = cumulative_wage_tax
    total_tax = wage_tax + bonus_tax
    return {
        "has_params": bool(social.get("has_params")),
        "total_income": total_income,
        "personal_total": personal_monthly * 12.0,
        "taxable_income": schedule[-1]["taxable_income"] if schedule else 0.0,
        "special_monthly": special_monthly,
        "total_bonus": total_bonus,
        "wage_tax": wage_tax,
        "bonus_tax": bonus_tax,
        "total_tax": total_tax,
        "net_income": total_income - personal_monthly * 12.0 - total_tax,
        "monthly_net": (
            total_income - personal_monthly * 12.0 - total_tax
        ) / 12.0,
        "monthly_schedule": schedule,
        "bonus_method": method,
    }
