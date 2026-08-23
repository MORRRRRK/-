"""实时金价参考接口（新浪财经，无需 API Key）。"""
from __future__ import annotations

import re
import urllib.error
import urllib.request

GOLD_URL = "https://hq.sinajs.cn/list=gds_AUTD"
REFERER = "https://finance.sina.com.cn"


class GoldPriceError(Exception):
    pass


def fetch_gold_price(timeout: float = 12.0) -> tuple[float, str]:
    request = urllib.request.Request(
        GOLD_URL,
        headers={
            "Referer": REFERER,
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise GoldPriceError(f"金价接口请求失败（HTTP {exc.code}）") from exc
    except urllib.error.URLError as exc:
        raise GoldPriceError(f"金价接口网络失败：{exc.reason}") from exc
    try:
        text = raw.decode("gbk", errors="ignore")
    except Exception:
        text = raw.decode("utf-8", errors="ignore")
    match = re.search(r'"(.*?)"', text)
    if not match:
        raise GoldPriceError("金价接口返回格式异常")
    fields = match.group(1).split(",")
    if len(fields) < 2:
        raise GoldPriceError("金价接口字段不足")
    try:
        price = float(fields[0])
    except ValueError as exc:
        raise GoldPriceError("金价接口数值无法解析") from exc
    date = fields[12] if len(fields) > 12 else ""
    return price, date
