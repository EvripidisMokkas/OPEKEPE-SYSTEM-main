from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import unittest

from agropekepe.eligibility import load_rules
from agropekepe.repository import AgroRepository
from agropekepe.services import AgroLedgerService

RULES_PATH = Path(__file__).resolve().parents[1] / "configs" / "cap_rules.example.json"


class AgroLedgerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = AgroRepository(":memory:")
        self.repository.initialize()
        self.service = AgroLedgerService(self.repository, load_rules(RULES_PATH))
        self.farmer = self.service.register_farmer("EL111111111", "Test Farmer")
        self.geometry = {
            "type": "Polygon",
            "coordinates": [
                [
                    [23.7000, 37.9000],
                    [23.7010, 37.9000],
                    [23.7010, 37.9010],
                    [23.7000, 37.9010],
                    [23.7000, 37.9000],
                ]
            ],
        }

    def tearDown(self) -> None:
        self.repository.close()

    def test_registers_land_production_sale_subsidy_and_ledger(self) -> None:
        parcel = self.service.register_parcel(self.farmer.farmer_id, "CAD-1", "owned", self.geometry)
        crop = self.service.enroll_production(
            parcel.parcel_id,
            self.farmer.farmer_id,
            2026,
            "olives",
            parcel.eligible_area_ha,
            organic=True,
            soil_cover=True,
            declared_yield_tonnes=Decimal("10"),
            verified_yield_tonnes=Decimal("9.5"),
            crop_label_confidence=Decimal("0.90"),
        )
        first_sale, tax = self.service.record_first_sale(
            crop.crop_season_id,
            "INV-1",
            "EL222222222",
            "2026-10-10",
            "olive_oil",
            Decimal("5"),
            Decimal("4000"),
            Decimal("0.13"),
            "MYDATA-1",
        )
        self.service.record_debt(self.farmer.farmer_id, "tax", Decimal("200"))

        subsidy = self.service.calculate_annual_subsidy_claim(self.farmer.farmer_id, 2026)
        ledger = self.service.annual_farmer_ledger(self.farmer.farmer_id, 2026)

        self.assertEqual(first_sale.gross_amount_eur, Decimal("20000"))
        self.assertEqual(tax.tax_amount_eur, Decimal("2600.00"))
        self.assertGreater(subsidy.final_amount_eur, Decimal("0"))
        self.assertEqual(subsidy.risk_flags, ())
        self.assertEqual(ledger.first_sale_revenue_eur, Decimal("20000.00"))
        self.assertEqual(ledger.first_sale_tax_eur, Decimal("2600.00"))
        self.assertIn("farmer.registered", [event["action"] for event in self.repository.audit_events()])

    def test_public_land_conflict_blocks_eligible_area_and_payment(self) -> None:
        parcel = self.service.register_parcel(
            self.farmer.farmer_id,
            "CAD-PUBLIC",
            "leased",
            self.geometry,
            declared_area_ha=Decimal("5"),
            public_land_conflict=True,
        )

        self.assertEqual(parcel.eligible_area_ha, Decimal("0"))
        with self.assertRaises(ValueError):
            self.service.enroll_production(
                parcel.parcel_id,
                self.farmer.farmer_id,
                2026,
                "pasture",
                Decimal("1"),
            )

    def test_remote_sensing_low_confidence_holds_subsidy(self) -> None:
        parcel = self.service.register_parcel(self.farmer.farmer_id, "CAD-LOW", "owned", self.geometry)
        self.service.enroll_production(parcel.parcel_id, self.farmer.farmer_id, 2026, "cereals", parcel.eligible_area_ha)
        self.service.record_remote_sensing(
            parcel.parcel_id,
            2026,
            "google-earth-engine",
            "crop_classification",
            Decimal("0.30"),
            {"label": "unknown"},
        )

        subsidy = self.service.calculate_annual_subsidy_claim(self.farmer.farmer_id, 2026)

        self.assertEqual(subsidy.final_amount_eur, Decimal("0.00"))
        self.assertEqual(subsidy.risk_flags, ("low_crop_label_confidence",))

    def test_crisis_compensation_requires_geofence_and_weather_evidence(self) -> None:
        parcel = self.service.register_parcel(self.farmer.farmer_id, "CAD-CRISIS", "owned", self.geometry)
        crop = self.service.enroll_production(parcel.parcel_id, self.farmer.farmer_id, 2026, "olives", parcel.eligible_area_ha)
        crisis = self.service.declare_crisis_event(
            "drought",
            "Attica drought",
            2026,
            "2026-07-01",
            (Decimal("37.80"), Decimal("23.60"), Decimal("38.00"), Decimal("23.80")),
        )

        held = self.service.calculate_crisis_compensation(crisis.crisis_event_id, crop.crop_season_id, Decimal("50"))
        self.assertEqual(held.final_amount_eur, Decimal("0.00"))
        self.assertIn("missing_remote_or_weather_evidence", held.hold_reasons)

        self.service.record_remote_sensing(
            parcel.parcel_id,
            2026,
            "weather-service",
            "drought",
            Decimal("0.90"),
            {"rainfall_deficit_percent": 50},
        )
        approved = self.service.calculate_crisis_compensation(crisis.crisis_event_id, crop.crop_season_id, Decimal("50"))

        self.assertGreater(approved.final_amount_eur, Decimal("0"))
        self.assertEqual(approved.hold_reasons, ())


if __name__ == "__main__":
    unittest.main()
