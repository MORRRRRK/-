"""资产规划模拟：净资产生长与目标倒推每月存款。"""
from __future__ import annotations


def project_net_worth(
    current: float, monthly_invest: float, annual_rate: float, years: float
) -> float:
    months = max(0, int(years * 12))
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    if months == 0:
        return current
    if abs(monthly_rate) < 1e-12:
        return current + monthly_invest * months
    return current * (1 + monthly_rate) ** months + monthly_invest * (
        (1 + monthly_rate) ** months - 1
    ) / monthly_rate


def required_monthly_saving(
    target: float, current: float, months: float, annual_rate: float
) -> float:
    if target <= current or months <= 0:
        return 0.0
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    if abs(monthly_rate) < 1e-12:
        return (target - current) / months
    return (
        (target - current * (1 + monthly_rate) ** months)
        * monthly_rate
        / ((1 + monthly_rate) ** months - 1)
    )
