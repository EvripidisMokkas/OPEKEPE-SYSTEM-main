from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import unittest

from agropekepe.app import AgroLedgerAPI
from agropekepe.eligibility import load_rules
from agropekepe.repository import AgroRepository
from agropekepe.services import AgroLedgerService

RULES_PATH = Path(__file__).resolve().parents[1] / "configs" / "cap_rules.example.json"


class AgroLedgerAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = AgroRepository(":memory:")
        self.repository.initialize()
        self.api = AgroLedgerAPI(AgroLedgerService(self.repository, load_rules(RULES_PATH)))

    def tearDown(self) -> None:
        self.repository.close()

    def test_api_route_sequence_creates_and_calculates_claim(self) -> None:
        status, farmer_response = self.api.handle(
            "POST",
            "/farmers",
            {},
            {"tax_identifier": "EL333333333", "legal_name": "API Farmer"},
        )
        self.assertEqual(status, 201)
        farmer_id = farmer_response["farmer"]["farmer_id"]

        geometry = {
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
        status, parcel_response = self.api.handle(
            "POST",
            "/parcels",
            {},
            {
                "farmer_id": farmer_id,
                "cadastral_reference": "API-CAD-1",
                "right_type": "owned",
                "geometry_geojson": geometry,
            },
        )
        self.assertEqual(status, 201)
        parcel = parcel_response["parcel"]

        status, crop_response = self.api.handle(
            "POST",
            "/crop-seasons",
            {},
            {
                "parcel_id": parcel["parcel_id"],
                "farmer_id": farmer_id,
                "claim_year": 2026,
                "production_type": "olives",
                "labelled_area_ha": parcel["eligible_area_ha"],
                "crop_label_confidence": "0.91",
            },
        )
        self.assertEqual(status, 201)
        self.assertIn("crop_season_id", crop_response["crop_season"])

        status, claim_response = self.api.handle(
            "POST",
            "/subsidy-claims/calculate",
            {},
            {"farmer_id": farmer_id, "claim_year": 2026},
        )

        self.assertEqual(status, 200)
        self.assertEqual(claim_response["subsidy_claim"]["risk_flags"], [])
        self.assertGreater(Decimal(claim_response["subsidy_claim"]["final_amount_eur"]), Decimal("0"))

    def test_dashboard_data_initializes_core_services(self) -> None:
        status, response = self.api.handle("GET", "/dashboard/data", {}, {})

        self.assertEqual(status, 200)
        self.assertEqual(response["summary"]["farmers"], 1)
        self.assertEqual(response["summary"]["parcels"], 1)
        self.assertEqual(response["summary"]["crop_seasons"], 1)
        self.assertGreaterEqual(response["summary"]["observations"], 2)
        self.assertEqual(response["summary"]["first_sales"], 1)
        self.assertEqual(response["summary"]["debts"], 1)
        self.assertEqual(response["summary"]["crisis_events"], 1)
        self.assertEqual(response["subsidy_claim"]["risk_flags"], [])
        self.assertEqual(response["services"][0]["status"], "αρχικοποιημένη")
        self.assertIn("financial_analysis", response)
        self.assertIn("crisis_management", response)
        self.assertIn("weather_conditions", response)
        self.assertIn("seed_analysis", response)
        self.assertIn("first_sale_deductions", response["financial_analysis"])
        self.assertIn("collective_revenue_loss_eur", response["crisis_management"])
        self.assertGreater(Decimal(response["financial_analysis"]["first_sale_deductions"]["net_product_after_deductions_eur"]), Decimal("0"))
        self.assertEqual(response["seed_analysis"]["records"][0]["status"], "aligned")
        self.assertGreaterEqual(len(response["seed_analysis"]["collective_database"]), 4)
        self.assertGreater(Decimal(response["seed_analysis"]["summary"]["total_net_margin_eur"]), Decimal("0"))
        self.assertIn("techno_economic_notes", response["seed_analysis"]["records"][0])
        self.assertGreaterEqual(len(response["seed_analysis"]["recommendations"]), 4)

    def test_document_submission_updates_dashboard_records(self) -> None:
        status, dashboard = self.api.handle("GET", "/dashboard/data", {}, {})
        self.assertEqual(status, 200)
        farmer_id = dashboard["farmer"]["farmer_id"]

        status, response = self.api.handle(
            "POST",
            "/documents",
            {},
            {
                "farmer_id": farmer_id,
                "document_type": "finance",
                "file_name": "invoice-summary.pdf",
                "file_size": 2048,
            },
        )

        self.assertEqual(status, 201)
        self.assertEqual(response["document"]["status"], "submitted")
        self.assertEqual(response["document"]["analysis"]["risk"], "medium")

        status, refreshed = self.api.handle("GET", "/dashboard/data", {}, {})
        self.assertEqual(status, 200)
        self.assertEqual(refreshed["summary"]["documents"], 1)
        self.assertEqual(refreshed["financial_analysis"]["document_coverage"], "πλήρης")

    def test_applicant_screening_flags_declared_public_integrity_exposure(self) -> None:
        status, response = self.api.handle(
            "POST",
            "/applicant-screening",
            {},
            {
                "first_name": "Nikos",
                "surname": "Farmer",
                "occupation": "Farmer",
                "public_integrity_exposure": "yes",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(response["screening"]["status"], "enhanced_audit")
        self.assertTrue(response["screening"]["enhanced_audit"])
        self.assertIn("applicant_declared_public_integrity_exposure", response["screening"]["reasons"])

    def test_applicant_screening_clears_unmatched_applicant(self) -> None:
        status, response = self.api.handle(
            "POST",
            "/applicant-screening",
            {},
            {
                "first_name": "Clear",
                "surname": "Applicant",
                "occupation": "Farmer",
                "public_integrity_exposure": "no",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(response["screening"]["status"], "off_the_hook")
        self.assertFalse(response["screening"]["enhanced_audit"])

    def test_enhanced_audit_document_upload_marks_close_audit(self) -> None:
        status, dashboard = self.api.handle("GET", "/dashboard/data", {}, {})
        self.assertEqual(status, 200)
        farmer_id = dashboard["farmer"]["farmer_id"]

        status, response = self.api.handle(
            "POST",
            "/documents",
            {},
            {
                "farmer_id": farmer_id,
                "document_type": "land",
                "file_name": "lease.pdf",
                "file_size": 1024,
                "enhanced_audit": True,
            },
        )

        self.assertEqual(status, 201)
        self.assertEqual(response["document"]["analysis"]["risk"], "high")
        self.assertEqual(response["document"]["analysis"]["audit_mode"], "close_audit")
        self.assertIn("enhanced_audit_queue", response["document"]["analysis"]["checks"])


if __name__ == "__main__":
    unittest.main()
