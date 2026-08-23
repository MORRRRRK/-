"""同花顺金融数据服务 REST 客户端（V2.0 实时行情）。"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .eastmoney import EastMoneyError, fund_nav as eastmoney_fund_nav

BASE_URL = "https://fuyao.aicubes.cn"


class MarketError(Exception):
    pass


class MarketClient:
    def __init__(self, api_key: str, timeout: float = 12.0):
        self.api_key = api_key
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        if not self.api_key:
            raise MarketError("尚未配置同花顺 API Key，请先在“设置”中填写")
        url = BASE_URL + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"X-api-key": self.api_key})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (4001, 429) or exc.code >= 500:
                    if attempt < 2:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                raise MarketError(f"接口请求失败（HTTP {exc.code}）") from exc
            except urllib.error.URLError as exc:
                raise MarketError(f"网络连接失败：{exc.reason}") from exc
            except json.JSONDecodeError as exc:
                raise MarketError("接口返回内容无法解析") from exc
        if payload.get("code") != 0:
            raise MarketError(
                f"接口错误（{payload.get('code')}）：{payload.get('message', '')}"
            )
        return payload.get("data") or {}

    def search_ticker(self, query: str, asset_type: str = "") -> list[dict]:
        params = {"q": query, "limit": 10}
        if asset_type:
            params["asset_type"] = asset_type
        data = self._get("/api/meta/tickers/search", params)
        return data.get("item") or []

    def stock_snapshot(self, thscodes: list[str]) -> dict[str, dict]:
        if not thscodes:
            return {}
        data = self._get(
            "/api/a-share/prices/snapshot",
            {"thscodes": ",".join(thscodes)},
        )
        result = {}
        for item in data.get("item") or []:
            result[item.get("thscode")] = item
        return result

    def fund_market_snapshot(self, thscode: str) -> dict:
        data = self._get("/api/fund/market/snapshot", {"thscode": thscode})
        items = data.get("item") or []
        return items[0] if items else {}

    def fund_nav(self, fund_type: str, thscode: str) -> dict:
        data = self._get(
            "/api/fund/performance/nav",
            {"fund_type": fund_type, "thscode": thscode, "nav_type": "unit"},
        )
        items = data.get("item") or []
        return items[-1] if items else {}

    def trading_days(self) -> list[str]:
        data = self._get("/api/a-share/calendar/trading-days")
        return [str(item.get("date", "")) for item in data.get("item") or []]


def fetch_live_price(
    client: MarketClient, asset_type: str, symbol: str
) -> tuple[float, str]:
    """返回 (最新价, 更新时间)。"""
    symbol = symbol.strip()
    if not symbol:
        raise MarketError("未填写代码")
    if asset_type == "stock":
        data = client.stock_snapshot([symbol])
        item = data.get(symbol)
        if not item:
            raise MarketError(f"未找到股票行情：{symbol}")
        price = float(item.get("last_price") or 0)
        return price, ""
    if asset_type in ("fund_exchange", "gold_etf"):
        try:
            item = client.fund_market_snapshot(symbol)
            price = float(item.get("last_price") or 0)
            return price, ""
        except MarketError:
            pure = symbol.upper().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
            if pure.isdigit() and len(pure) == 6:
                try:
                    return eastmoney_fund_nav(pure)
                except EastMoneyError as exc:
                    raise MarketError(str(exc)) from exc
            raise
    if asset_type == "fund_otc":
        try:
            item = client.fund_nav("otc", symbol)
            price = float(item.get("unit_nav") or 0)
            return price, str(item.get("nav_date") or "")
        except MarketError:
            try:
                return eastmoney_fund_nav(symbol)
            except EastMoneyError as exc:
                raise MarketError(str(exc)) from exc
    raise MarketError(f"不支持的资产类型：{asset_type}")
