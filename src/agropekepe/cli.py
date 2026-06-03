"""Command-line interface for running the AgroLedger MVP."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from agropekepe.app import run_server
from agropekepe.eligibility import load_rules
from agropekepe.repository import AgroRepository
from agropekepe.serialization import to_jsonable
from agropekepe.services import AgroLedgerService

DEFAULT_RULES = Path("configs/cap_rules.example.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the application CLI parser."""

    parser = argparse.ArgumentParser(description="AgroLedger agricultural subsidies management application")
    parser.add_argument("--database", default="agroledger.sqlite3", help="SQLite database path")
    parser.add_argument("--rules", default=str(DEFAULT_RULES), help="Rules JSON path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create database tables")

    demo = subparsers.add_parser("demo", help="Create a demo farmer, parcel, crop, sale, subsidy, and crisis decision")
    demo.add_argument("--claim-year", type=int, default=2026)

    serve = subparsers.add_parser("serve", help="Run the JSON HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    return parser


def main() -> None:
    """Run the CLI."""

    args = build_parser().parse_args()
    if args.command == "serve":
        run_server(args.database, args.rules, args.host, args.port)
        return

    repository = AgroRepository(args.database)
    repository.initialize()
    service = AgroLedgerService(repository, load_rules(args.rules))

    if args.command == "init-db":
        print(json.dumps({"database": args.database, "status": "initialized"}, indent=2))
    elif args.command == "demo":
        print(json.dumps(to_jsonable(run_demo(service, args.claim_year)), indent=2, sort_keys=True))


def run_demo(service: AgroLedgerService, claim_year: int) -> dict[str, object]:
    """Create a complete local demo record and return decisions."""

    farmer = service.register_farmer("EL123456789", "Demo Olive Farmer")
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [23.7000, 37.9000],
                [23.7020, 37.9000],
                [23.7020, 37.9020],
                [23.7000, 37.9020],
                [23.7000, 37.9000],
            ]
        ],
    }
    parcel = service.register_parcel(farmer.farmer_id, "DEMO-CAD-1", "owned", geometry)
    crop = service.enroll_production(
        parcel.parcel_id,
        farmer.farmer_id,
        claim_year,
        "olives",
        parcel.eligible_area_ha,
        organic=True,
        soil_cover=True,
        declared_yield_tonnes=Decimal("18"),
        verified_yield_tonnes=Decimal("17.5"),
        crop_label_confidence=Decimal("0.93"),
    )
    service.record_remote_sensing(
        parcel.parcel_id,
        claim_year,
        "google-earth-engine",
        "crop_classification",
        Decimal("0.93"),
        {"label": "olives", "ndvi_trend": "healthy"},
    )
    service.record_first_sale(
        crop.crop_season_id,
        "INV-DEMO-1",
        "EL987654321",
        f"{claim_year}-10-01",
        "olive_oil",
        Decimal("12"),
        Decimal("4300"),
        Decimal("0.13"),
        mydata_mark="DEMO-MARK-1",
    )
    service.record_debt(farmer.farmer_id, "tax", Decimal("1000"))
    crisis = service.declare_crisis_event(
        "drought",
        "Demo drought event",
        claim_year,
        f"{claim_year}-07-01",
        (Decimal("37.80"), Decimal("23.60"), Decimal("38.00"), Decimal("23.80")),
    )
    service.record_remote_sensing(
        parcel.parcel_id,
        claim_year,
        "weather-service",
        "drought",
        Decimal("0.88"),
        {"spi": "severe", "rainfall_deficit_percent": 45},
    )
    return {
        "farmer": farmer,
        "parcel": parcel,
        "crop_season": crop,
        "subsidy_claim": service.calculate_annual_subsidy_claim(farmer.farmer_id, claim_year),
        "compensation": service.calculate_crisis_compensation(crisis.crisis_event_id, crop.crop_season_id, Decimal("40")),
        "annual_ledger": service.annual_farmer_ledger(farmer.farmer_id, claim_year),
    }


if __name__ == "__main__":
    main()
