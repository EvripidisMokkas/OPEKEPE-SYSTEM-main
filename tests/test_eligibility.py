from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import unittest

from agropekepe.eligibility import ParcelFacts, calculate_subsidy, load_rules


RULES_PATH = Path(__file__).resolve().parents[1] / "configs" / "cap_rules.example.json"


class EligibilityTests(unittest.TestCase):
    def test_calculates_production_specific_rate_with_eco_bonuses(self) -> None:
        rules = load_rules(RULES_PATH)
        decision = calculate_subsidy(
            ParcelFacts(
                parcel_hectares=Decimal("10"),
                production_type="olives",
                organic=True,
                soil_cover=True,
                crop_label_confidence=Decimal("0.91"),
            ),
            rules,
        )

        self.assertEqual(decision.rate_eur_per_ha, Decimal("300.0"))
        self.assertEqual(decision.gross_amount_eur, Decimal("3000.00"))
        self.assertEqual(decision.final_amount_eur, Decimal("3000.00"))
        self.assertEqual(decision.hold_reasons, ())

    def test_holds_payment_for_public_land_conflict(self) -> None:
        rules = load_rules(RULES_PATH)
        decision = calculate_subsidy(
            ParcelFacts(
                parcel_hectares=Decimal("3.5"),
                production_type="pasture",
                public_land_conflict=True,
            ),
            rules,
        )

        self.assertEqual(decision.gross_amount_eur, Decimal("420.00"))
        self.assertEqual(decision.final_amount_eur, Decimal("0.00"))
        self.assertIn("public_land_conflict", decision.hold_reasons)

    def test_holds_payment_for_large_yield_variance(self) -> None:
        rules = load_rules(RULES_PATH)
        decision = calculate_subsidy(
            ParcelFacts(
                parcel_hectares=Decimal("2"),
                production_type="cereals",
                declared_yield_tonnes=Decimal("100"),
                verified_yield_tonnes=Decimal("60"),
            ),
            rules,
        )

        self.assertEqual(decision.final_amount_eur, Decimal("0.00"))
        self.assertIn("yield_variance_exceeds_tolerance", decision.hold_reasons)

    def test_holds_payment_for_low_crop_label_confidence(self) -> None:
        rules = load_rules(RULES_PATH)
        decision = calculate_subsidy(
            ParcelFacts(
                parcel_hectares=Decimal("1"),
                production_type="vineyards",
                crop_label_confidence=Decimal("0.40"),
            ),
            rules,
        )

        self.assertEqual(decision.final_amount_eur, Decimal("0.00"))
        self.assertIn("low_crop_label_confidence", decision.hold_reasons)


if __name__ == "__main__":
    unittest.main()
