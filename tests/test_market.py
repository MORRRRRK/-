from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import market


class FakeClient:
    def __init__(self):
        self.calls = []

    def fund_nav(self, fund_type: str, thscode: str):
        self.calls.append((fund_type, thscode))
        raise market.MarketError(f"Fund not found: {thscode}")


class MarketPriceTest(unittest.TestCase):
    def test_otc_symbol_appends_of_suffix(self) -> None:
        client = FakeClient()
        with patch(
            "app.services.market.eastmoney_fund_nav",
            return_value=(3.504, "2026-08-21"),
        ):
            price, date_text = market.fetch_live_price(client, "fund_otc", "006555")
        self.assertEqual(price, 3.504)
        self.assertEqual(date_text, "2026-08-21")
        self.assertEqual(client.calls, [("otc", "006555.OF")])

    def test_otc_symbol_with_of_suffix_passthrough(self) -> None:
        client = FakeClient()
        with patch(
            "app.services.market.eastmoney_fund_nav",
            return_value=(3.5, "2026-08-21"),
        ):
            price, _ = market.fetch_live_price(client, "fund_otc", "006555.OF")
        self.assertEqual(price, 3.5)
        self.assertEqual(client.calls, [("otc", "006555.OF")])

    def test_hithink_timestamp_date_formatted(self) -> None:
        client = FakeClient()
        client.fund_nav = lambda *args: {
            "unit_nav": 3.8,
            "nav_date": 1787241600000,
        }
        price, date_text = market.fetch_live_price(client, "fund_otc", "012920")
        self.assertEqual(price, 3.8)
        self.assertEqual(date_text, "2026-08-21")


if __name__ == "__main__":
    unittest.main()
