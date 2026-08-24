from __future__ import annotations

import unittest

from app.services import tax
from app.services import calculations


class TaxFormulaTest(unittest.TestCase):
    def test_income_tax_brackets(self) -> None:
        self.assertAlmostEqual(tax.income_tax(0), 0.0)
        self.assertAlmostEqual(tax.income_tax(36000), 1080.0)
        self.assertAlmostEqual(tax.income_tax(36001), 1080.1)
        self.assertAlmostEqual(tax.income_tax(144000), 11880.0)
        self.assertAlmostEqual(tax.income_tax(300000), 43080.0)

    def test_annual_bonus_tax(self) -> None:
        self.assertAlmostEqual(tax.annual_bonus_tax(0), 0.0)
        self.assertAlmostEqual(tax.annual_bonus_tax(36000), 1080.0)
        self.assertAlmostEqual(tax.annual_bonus_tax(36001), 3390.1)
        self.assertAlmostEqual(tax.annual_bonus_tax(120000), 11790.0)

    def test_rent_tier_for_city(self) -> None:
        self.assertEqual(tax.rent_tier_for_city("北京"), 1500.0)
        self.assertEqual(tax.rent_tier_for_city("上海"), 1500.0)
        self.assertEqual(tax.rent_tier_for_city(""), 0.0)

    def test_special_deductions_monthly(self) -> None:
        params = {
            "rent_tier": 1500.0,
            "elderly_option": "only_child",
            "children_education_count": 1,
            "infant_care_count": 1,
            "continuing_education": 1,
            "mortgage_interest": 1,
            "custom_deduction": 100.0,
        }
        self.assertAlmostEqual(tax.special_deductions_monthly(params), 10000.0)

    def test_simulate_annual_separate_and_combined(self) -> None:
        social = {
            "params": {"monthly_salary": 10000.0},
            "personal_total": 0.0,
            "total_salary": 156000.0,
            "thirteen_annual": 0.0,
            "bonus_annual": 36000.0,
            "salary_items": [],
        }
        separate = tax.simulate_annual(
            social,
            {"bonus_tax_method": "separate", "elderly_option": "none"},
        )
        self.assertAlmostEqual(separate["wage_tax"], 3480.0)
        self.assertAlmostEqual(separate["bonus_tax"], 1080.0)
        self.assertAlmostEqual(separate["total_tax"], 4560.0)
        self.assertAlmostEqual(separate["net_income"], 151440.0)
        self.assertAlmostEqual(
            sum(row["month_tax"] for row in separate["monthly_schedule"]),
            separate["total_tax"],
        )

        combined = tax.simulate_annual(
            social,
            {"bonus_tax_method": "combined", "elderly_option": "none"},
        )
        self.assertAlmostEqual(combined["wage_tax"], 7080.0)
        self.assertAlmostEqual(combined["bonus_tax"], 0.0)
        self.assertAlmostEqual(combined["net_income"], 148920.0)

    def test_social_insurance_from_data_frequencies(self) -> None:
        params = {
            "monthly_salary": 10000.0,
            "thirteenth_coefficient": 1.0,
            "thirteenth_frequency": "annual",
            "year_end_bonus_coefficient": 0.5,
            "year_end_bonus_frequency": "annual",
        }
        salary_items = [
            {
                "item_type": "performance",
                "name": "绩效",
                "amount": 1000.0,
                "frequency": "monthly",
            },
            {
                "item_type": "subsidy",
                "name": "补贴",
                "amount": 2000.0,
                "frequency": "quarterly",
            },
        ]
        result = calculations.social_insurance_from_data(
            params, [], salary_items
        )
        self.assertAlmostEqual(result["base_annual"], 120000.0)
        self.assertAlmostEqual(result["thirteen_annual"], 10000.0)
        self.assertAlmostEqual(result["bonus_annual"], 5000.0)
        self.assertAlmostEqual(result["performance_annual"], 12000.0)
        self.assertAlmostEqual(result["subsidy_annual"], 8000.0)
        self.assertAlmostEqual(result["total_salary"], 155000.0)


if __name__ == "__main__":
    unittest.main()
