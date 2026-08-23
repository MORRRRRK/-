"""东财场外基金兜底：部分老基金代码同花顺未收录时使用。"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

SEARCH_URL = "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
NAV_URL = "https://api.fund.eastmoney.com/f10/lsjz"


class EastMoneyError(Exception):
    pass


def _fetch(url: str, params: dict, referer: str) -> dict:
    url = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "Referer": referer,
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            text = response.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        raise EastMoneyError(f"东财接口请求失败（HTTP {exc.code}）") from exc
    except urllib.error.URLError as exc:
        raise EastMoneyError(f"东财接口网络失败：{exc.reason}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise EastMoneyError("东财接口返回内容无法解析") from exc


def search_fund(keyword: str) -> list[dict]:
    data = _fetch(
        SEARCH_URL,
        {"m": 1, "key": keyword},
        "https://fund.eastmoney.com/",
    )
    results = []
    for item in data.get("Datas") or []:
        code = item.get("CODE") or item.get("_id") or ""
        name = item.get("NAME") or ""
        if code and name:
            results.append({"code": code, "name": name})
    return results


def fund_nav(code: str) -> tuple[float, str]:
    code = code.strip().upper().replace(".OF", "")
    data = _fetch(
        NAV_URL,
        {"fundCode": code, "pageIndex": 1, "pageSize": 1},
        "https://fundf10.eastmoney.com/",
    )
    rows = (data.get("Data") or {}).get("LSJZList") or []
    if not rows:
        raise EastMoneyError(f"东财未找到基金净值：{code}")
    try:
        price = float(rows[0].get("DWJZ") or 0)
    except ValueError as exc:
        raise EastMoneyError("基金净值无法解析") from exc
    return price, str(rows[0].get("FSRQ") or "")
