"""Dependency-free JSON HTTP API for the AgroLedger MVP."""

from __future__ import annotations

import json
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from agropekepe.eligibility import load_rules
from agropekepe.repository import AgroRepository
from agropekepe.serialization import to_jsonable
from agropekepe.services import AgroLedgerService

HandlerResult = tuple[int, dict[str, Any]]
DASHBOARD_CLAIM_YEAR = 2026


class AgroLedgerAPI:
    """Route table for the local AgroLedger JSON API."""

    def __init__(self, service: AgroLedgerService) -> None:
        self.service = service

    def handle(self, method: str, path: str, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        """Dispatch a JSON request to an application service method."""

        routes: dict[tuple[str, str], Callable[[dict[str, list[str]], dict[str, Any]], HandlerResult]] = {
            ("GET", "/health"): self.health,
            ("GET", "/dashboard/data"): self.dashboard_data,
            ("POST", "/documents"): self.submit_document,
            ("POST", "/farmers"): self.create_farmer,
            ("POST", "/parcels"): self.create_parcel,
            ("POST", "/crop-seasons"): self.create_crop_season,
            ("POST", "/remote-sensing"): self.create_remote_sensing,
            ("POST", "/first-sales"): self.create_first_sale,
            ("POST", "/debts"): self.create_debt,
            ("POST", "/subsidy-claims/calculate"): self.calculate_subsidy_claim,
            ("POST", "/crisis-events"): self.create_crisis_event,
            ("POST", "/compensation-claims/calculate"): self.calculate_compensation,
            ("GET", "/annual-ledger"): self.annual_ledger,
            ("GET", "/audit/events"): self.audit_events,
        }
        handler = routes.get((method, path))
        if handler is None:
            return 404, {"error": "route_not_found", "method": method, "path": path}
        return handler(query, payload)

    def health(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        return 200, {"status": "ok", "service": "agroledger"}

    def dashboard_data(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        return 200, _dashboard_payload(self.service)

    def submit_document(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        document_type = str(payload["document_type"])
        file_name = str(payload["file_name"])
        file_size = int(payload.get("file_size", 0))
        analysis = _document_analysis(document_type, file_name, file_size)
        document = self.service.repository.add_document_record(
            farmer_id=str(payload["farmer_id"]),
            document_type=document_type,
            file_name=file_name,
            file_size=file_size,
            analysis=analysis,
        )
        return 201, {"document": document}

    def create_farmer(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        farmer = self.service.register_farmer(
            tax_identifier=str(payload["tax_identifier"]),
            legal_name=str(payload["legal_name"]),
            farmer_type=str(payload.get("farmer_type", "individual")),
            active_farmer=bool(payload.get("active_farmer", True)),
        )
        return 201, {"farmer": to_jsonable(farmer)}

    def create_parcel(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        parcel = self.service.register_parcel(
            farmer_id=str(payload["farmer_id"]),
            cadastral_reference=str(payload["cadastral_reference"]),
            right_type=str(payload["right_type"]),
            geometry_geojson=payload["geometry_geojson"],
            declared_area_ha=_optional_decimal(payload.get("declared_area_ha")),
            public_land_conflict=bool(payload.get("public_land_conflict", False)),
            protected_area_conflict=bool(payload.get("protected_area_conflict", False)),
        )
        return 201, {"parcel": to_jsonable(parcel)}

    def create_crop_season(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        crop_season = self.service.enroll_production(
            parcel_id=str(payload["parcel_id"]),
            farmer_id=str(payload["farmer_id"]),
            claim_year=int(payload["claim_year"]),
            production_type=str(payload["production_type"]),
            labelled_area_ha=Decimal(str(payload["labelled_area_ha"])),
            organic=bool(payload.get("organic", False)),
            soil_cover=bool(payload.get("soil_cover", False)),
            irrigation_status=str(payload.get("irrigation_status", "unknown")),
            declared_yield_tonnes=_optional_decimal(payload.get("declared_yield_tonnes")),
            verified_yield_tonnes=_optional_decimal(payload.get("verified_yield_tonnes")),
            crop_label_confidence=_optional_decimal(payload.get("crop_label_confidence")),
        )
        return 201, {"crop_season": to_jsonable(crop_season)}

    def create_remote_sensing(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        observation = self.service.record_remote_sensing(
            parcel_id=str(payload["parcel_id"]),
            claim_year=int(payload["claim_year"]),
            provider=str(payload["provider"]),
            observation_type=str(payload["observation_type"]),
            confidence=Decimal(str(payload["confidence"])),
            result=dict(payload.get("result", {})),
            evidence_uri=payload.get("evidence_uri"),
        )
        return 201, {"observation": to_jsonable(observation)}

    def create_first_sale(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        first_sale, tax = self.service.record_first_sale(
            crop_season_id=str(payload["crop_season_id"]),
            invoice_number=str(payload["invoice_number"]),
            buyer_tax_identifier=str(payload["buyer_tax_identifier"]),
            sale_date=str(payload["sale_date"]),
            product_type=str(payload["product_type"]),
            quantity_tonnes=Decimal(str(payload["quantity_tonnes"])),
            unit_price_eur=Decimal(str(payload["unit_price_eur"])),
            tax_rate=Decimal(str(payload["tax_rate"])),
            mydata_mark=payload.get("mydata_mark"),
        )
        return 201, {"first_sale": to_jsonable(first_sale), "tax": to_jsonable(tax)}

    def create_debt(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        debt = self.service.record_debt(
            farmer_id=str(payload["farmer_id"]),
            debt_type=str(payload["debt_type"]),
            outstanding_eur=Decimal(str(payload["outstanding_eur"])),
            status=str(payload.get("status", "open")),
        )
        return 201, {"debt": to_jsonable(debt)}

    def calculate_subsidy_claim(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        decision = self.service.calculate_annual_subsidy_claim(str(payload["farmer_id"]), int(payload["claim_year"]))
        return 200, {"subsidy_claim": to_jsonable(decision)}

    def create_crisis_event(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        bbox = payload["affected_bbox"]
        crisis_event = self.service.declare_crisis_event(
            event_type=str(payload["event_type"]),
            name=str(payload["name"]),
            claim_year=int(payload["claim_year"]),
            event_start=str(payload["event_start"]),
            affected_bbox=(Decimal(str(bbox[0])), Decimal(str(bbox[1])), Decimal(str(bbox[2])), Decimal(str(bbox[3]))),
            event_end=payload.get("event_end"),
        )
        return 201, {"crisis_event": to_jsonable(crisis_event)}

    def calculate_compensation(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        decision = self.service.calculate_crisis_compensation(
            crisis_event_id=str(payload["crisis_event_id"]),
            crop_season_id=str(payload["crop_season_id"]),
            damage_percent=Decimal(str(payload["damage_percent"])),
        )
        return 200, {"compensation": to_jsonable(decision)}

    def annual_ledger(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        farmer_id = _single_query(query, "farmer_id")
        claim_year = int(_single_query(query, "claim_year"))
        return 200, {"annual_ledger": to_jsonable(self.service.annual_farmer_ledger(farmer_id, claim_year))}

    def audit_events(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        return 200, {
            "audit_events": self.service.repository.audit_events(
                entity_type=_optional_single_query(query, "entity_type"),
                entity_id=_optional_single_query(query, "entity_id"),
            )
        }


def create_handler(api: AgroLedgerAPI) -> type[BaseHTTPRequestHandler]:
    """Create an HTTP request handler bound to an API instance."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle_request("GET")

        def do_POST(self) -> None:
            self._handle_request("POST")

        def _handle_request(self, method: str) -> None:
            parsed = urlparse(self.path)
            if method == "GET" and parsed.path == "/":
                self._send_bytes(200, DASHBOARD_HTML.encode("utf-8"), "text/html; charset=utf-8")
                return

            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
                status, response = api.handle(method, parsed.path, parse_qs(parsed.query), payload)
            except KeyError as error:
                status, response = 404, {"error": "record_not_found", "detail": str(error)}
            except (json.JSONDecodeError, ValueError, TypeError) as error:
                status, response = 400, {"error": "bad_request", "detail": str(error)}
            body = json.dumps(response, sort_keys=True).encode("utf-8")
            self._send_bytes(status, body, "application/json")

        def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def run_server(database_path: str | Path, rules_path: str | Path, host: str = "127.0.0.1", port: int = 8080) -> None:
    """Initialize and run the local JSON HTTP API."""

    repository = AgroRepository(database_path)
    repository.initialize()
    service = AgroLedgerService(repository, load_rules(rules_path))
    server = ThreadingHTTPServer((host, port), create_handler(AgroLedgerAPI(service)))
    print(f"AgroLedger API listening on http://{host}:{port}")
    server.serve_forever()


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _single_query(query: dict[str, list[str]], key: str) -> str:
    value = _optional_single_query(query, key)
    if value is None:
        raise ValueError(f"missing query parameter: {key}")
    return value


def _optional_single_query(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _dashboard_payload(service: AgroLedgerService) -> dict[str, Any]:
    """Return an initialized dashboard snapshot for the browser UI."""

    if not service.repository.list_farmers():
        _initialize_demo_services(service)

    farmers = service.repository.list_farmers()
    parcels = service.repository.list_parcels()
    crop_seasons = service.repository.list_crop_seasons()
    observations = [
        observation
        for parcel in parcels
        for observation in service.repository.list_observations(parcel.parcel_id)
    ]
    first_sales = [
        first_sale
        for crop_season in crop_seasons
        for first_sale in service.repository.list_first_sales_for_crop(crop_season.crop_season_id)
    ]
    debts = [debt for farmer in farmers for debt in service.repository.list_debts(farmer.farmer_id)]
    crisis_events = service.repository.list_crisis_events()
    primary_farmer = farmers[0]
    documents = service.repository.list_document_records(primary_farmer.farmer_id)
    primary_crop = crop_seasons[0] if crop_seasons else None
    subsidy_claim = service.calculate_annual_subsidy_claim(primary_farmer.farmer_id, DASHBOARD_CLAIM_YEAR)
    annual_ledger = service.annual_farmer_ledger(primary_farmer.farmer_id, DASHBOARD_CLAIM_YEAR)
    compensation = None
    if crisis_events and primary_crop is not None:
        compensation = service.calculate_crisis_compensation(
            crisis_events[0].crisis_event_id,
            primary_crop.crop_season_id,
            Decimal("40"),
        )

    return {
        "summary": {
            "farmers": len(farmers),
            "parcels": len(parcels),
            "crop_seasons": len(crop_seasons),
            "observations": len(observations),
            "first_sales": len(first_sales),
            "debts": len(debts),
            "documents": len(documents),
            "crisis_events": len(crisis_events),
            "audit_events": len(service.repository.audit_events()),
        },
        "services": [
            {"name": "Farmer identity", "status": "initialized", "records": len(farmers)},
            {"name": "Land parcel registry", "status": "initialized", "records": len(parcels)},
            {"name": "Production declarations", "status": "initialized", "records": len(crop_seasons)},
            {"name": "Remote sensing evidence", "status": "initialized", "records": len(observations)},
            {"name": "First-sale tax reconciliation", "status": "initialized", "records": len(first_sales)},
            {"name": "Debt offset management", "status": "initialized", "records": len(debts)},
            {"name": "Document intake and review", "status": "initialized", "records": len(documents)},
            {"name": "CAP subsidy calculation", "status": "initialized", "records": len(subsidy_claim.line_items)},
            {"name": "Crop weather forecast", "status": "initialized", "records": 20},
            {"name": "Crisis compensation", "status": "initialized", "records": len(crisis_events)},
            {"name": "AI assistant guidance", "status": "initialized", "records": 4},
            {"name": "Audit trail", "status": "initialized", "records": len(service.repository.audit_events())},
        ],
        "farmer": to_jsonable(primary_farmer),
        "parcels": to_jsonable(parcels),
        "crop_seasons": to_jsonable(crop_seasons),
        "documents": documents,
        "document_requirements": _document_requirements(documents),
        "subsidy_claim": to_jsonable(subsidy_claim),
        "compensation": to_jsonable(compensation) if compensation is not None else None,
        "annual_ledger": to_jsonable(annual_ledger),
        "land_declaration": _land_declaration_state(parcels),
        "weather_conditions": _weather_conditions(),
        "crop_forecast": _crop_forecast_service(crop_seasons, parcels),
        "seed_analysis": _seed_analysis(crop_seasons, parcels),
        "financial_analysis": _financial_analysis(annual_ledger, subsidy_claim, compensation, documents, first_sales),
        "audit_analysis": _audit_analysis(service.repository.audit_events(), subsidy_claim, documents),
        "crisis_management": _crisis_management(compensation, annual_ledger),
        "assistant": _assistant_prompts(documents, subsidy_claim),
        "audit_events": service.repository.audit_events()[-8:],
    }


def _initialize_demo_services(service: AgroLedgerService) -> None:
    """Create a complete local operating sample for every dashboard service."""

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
        DASHBOARD_CLAIM_YEAR,
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
        DASHBOARD_CLAIM_YEAR,
        "google-earth-engine",
        "crop_classification",
        Decimal("0.93"),
        {"label": "olives", "ndvi_trend": "healthy"},
    )
    service.record_first_sale(
        crop.crop_season_id,
        "INV-DEMO-1",
        "EL987654321",
        f"{DASHBOARD_CLAIM_YEAR}-10-01",
        "olive_oil",
        Decimal("12"),
        Decimal("4300"),
        Decimal("0.13"),
        mydata_mark="DEMO-MARK-1",
    )
    service.record_debt(farmer.farmer_id, "tax", Decimal("1000"))
    service.declare_crisis_event(
        "drought",
        "Demo drought event",
        DASHBOARD_CLAIM_YEAR,
        f"{DASHBOARD_CLAIM_YEAR}-07-01",
        (Decimal("37.80"), Decimal("23.60"), Decimal("38.00"), Decimal("23.80")),
    )
    service.record_remote_sensing(
        parcel.parcel_id,
        DASHBOARD_CLAIM_YEAR,
        "weather-service",
        "drought",
        Decimal("0.88"),
        {"spi": "severe", "rainfall_deficit_percent": 45},
    )


def _document_analysis(document_type: str, file_name: str, file_size: int) -> dict[str, Any]:
    checks = {
        "identity": ["tax_identifier_detected", "name_match_pending"],
        "land": ["parcel_reference_detected", "geometry_review_required"],
        "finance": ["invoice_totals_read", "tax_reconciliation_pending"],
        "bank": ["iban_format_check", "beneficiary_match_pending"],
        "crisis": ["incident_date_detected", "evidence_review_required"],
    }
    normalized_type = document_type if document_type in checks else "general"
    return {
        "summary": f"{file_name} queued for {document_type} review",
        "file_size": file_size,
        "confidence": "0.82" if file_size else "0.58",
        "checks": checks.get(normalized_type, ["manual_review_required"]),
        "risk": "medium" if normalized_type in {"finance", "crisis"} else "low",
    }


def _document_requirements(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    submitted = {document["document_type"] for document in documents}
    required = [
        ("identity", "Identity and tax certificate"),
        ("land", "Land title, lease, or cadastral extract"),
        ("finance", "Invoices, myDATA records, and bank statement"),
        ("bank", "IBAN proof for payment"),
        ("crisis", "Incident photos or authority declaration"),
    ]
    return [
        {
            "document_type": document_type,
            "label": label,
            "status": "submitted" if document_type in submitted else "needed",
        }
        for document_type, label in required
    ]


def _land_declaration_state(parcels: list[Any]) -> dict[str, Any]:
    parcel = parcels[0] if parcels else None
    lat = str(parcel.centroid_lat) if parcel is not None else "37.9008"
    lon = str(parcel.centroid_lon) if parcel is not None else "23.7008"
    return {
        "sources": [
            {"name": "Google Maps parcel draw", "status": "ready"},
            {"name": "Google Earth KML import", "status": "ready"},
            {"name": "Manual GeoJSON upload", "status": "ready"},
        ],
        "active_source": "Google Earth Engine evidence",
        "map_center": {"lat": lat, "lon": lon},
        "google_maps_url": f"https://maps.google.com/maps?q={lat},{lon}&z=16",
        "declared_area_ha": str(parcel.declared_area_ha) if parcel is not None else "0.00",
        "eligible_area_ha": str(parcel.eligible_area_ha) if parcel is not None else "0.00",
    }


def _financial_analysis(
    annual_ledger: Any,
    subsidy_claim: Any,
    compensation: Any | None,
    documents: list[dict[str, Any]],
    first_sales: list[Any],
) -> dict[str, Any]:
    compensation_amount = compensation.final_amount_eur if compensation is not None else Decimal("0")
    gross_public_support = subsidy_claim.final_amount_eur + compensation_amount
    tax_and_debt = annual_ledger.first_sale_tax_eur + annual_ledger.open_debt_eur
    net_after_obligations = gross_public_support - subsidy_claim.debt_offset.offset_eur
    finance_docs = [document for document in documents if document["document_type"] == "finance"]
    sold_quantity = sum((sale.quantity_tonnes for sale in first_sales), Decimal("0"))
    gross_product_value = sum((sale.gross_amount_eur for sale in first_sales), Decimal("0"))
    first_sale_tax = sum((sale.tax_amount_eur for sale in first_sales), Decimal("0"))
    market_fee = gross_product_value * Decimal("0.02")
    net_product_after_deductions = gross_product_value - first_sale_tax - market_fee
    return {
        "gross_public_support_eur": str(gross_public_support),
        "tax_and_debt_exposure_eur": str(tax_and_debt),
        "net_after_offsets_eur": str(net_after_obligations),
        "document_coverage": "complete" if finance_docs else "missing financial uploads",
        "first_sale_deductions": {
            "sold_quantity_tonnes": str(sold_quantity),
            "gross_product_value_eur": str(gross_product_value),
            "first_sale_tax_eur": str(first_sale_tax),
            "market_fee_eur": str(market_fee),
            "net_product_after_deductions_eur": str(net_product_after_deductions),
        },
        "series": [
            {"label": "Sales revenue", "value": str(annual_ledger.first_sale_revenue_eur)},
            {"label": "Tax due", "value": str(annual_ledger.first_sale_tax_eur)},
            {"label": "Subsidy", "value": str(subsidy_claim.final_amount_eur)},
            {"label": "Compensation", "value": str(compensation_amount)},
            {"label": "Debt", "value": str(annual_ledger.open_debt_eur)},
        ],
        "payment_scenarios": [
            {"label": "Normal clearance", "gross": str(subsidy_claim.final_amount_eur), "net": str(subsidy_claim.debt_offset.disbursable_eur)},
            {"label": "Crisis approved", "gross": str(gross_public_support), "net": str(net_after_obligations + compensation_amount)},
            {"label": "Document hold", "gross": str(gross_public_support), "net": "0.00"},
        ],
    }


def _weather_conditions() -> dict[str, Any]:
    return {
        "station": "Attica demo weather grid",
        "current": {
            "temperature_c": "31",
            "humidity_percent": "42",
            "wind_kph": "18",
            "rainfall_7d_mm": "4",
            "soil_moisture": "low",
            "risk": "drought watch",
        },
        "forecast": [
            {"day": "Today", "condition": "hot", "rain_mm": "0", "risk": "medium"},
            {"day": "Tomorrow", "condition": "wind", "rain_mm": "0", "risk": "medium"},
            {"day": "Day 3", "condition": "dry", "rain_mm": "1", "risk": "high"},
            {"day": "Day 4", "condition": "cloud", "rain_mm": "3", "risk": "low"},
        ],
    }


def _crop_forecast_service(crop_seasons: list[Any], parcels: list[Any]) -> dict[str, Any]:
    declared_area = sum((parcel.eligible_area_ha for parcel in parcels), Decimal("0"))
    if declared_area <= 0:
        declared_area = Decimal("1")
    declared_crop = crop_seasons[0].production_type if crop_seasons else "olives"
    weather_forecast = _weather_conditions()
    soil_profile = {
        "texture": "clay loam",
        "organic_matter_percent": "2.4",
        "ph": "7.3",
        "drainage": "moderate",
        "water_holding": "medium-low",
    }
    options = []
    for crop in _crop_forecast_catalog():
        expected_yield_ha = Decimal(str(crop["base_yield_tonnes_per_ha"]))
        soil_factor = Decimal(str(crop["soil_factor"]))
        forecast_yield_ha = expected_yield_ha
        max_yield_ha = expected_yield_ha * Decimal(str(crop["max_factor"]))
        forecast_tonnes = forecast_yield_ha * declared_area
        max_tonnes = max_yield_ha * declared_area
        price = Decimal(str(crop["market_price_eur_per_tonne"]))
        byproduct_rates = _industry_byproduct_rates(crop["id"])
        byproduct_value = sum(
            (
                forecast_tonnes
                * Decimal(str(rate["yield_ratio"]))
                * Decimal(str(rate["market_price_eur_per_tonne"]))
                for rate in byproduct_rates
            ),
            Decimal("0"),
        )
        input_cost = Decimal(str(crop["input_cost_eur_per_ha"])) * declared_area
        field_cost = Decimal(str(crop["field_operations_eur_per_ha"])) * declared_area
        irrigation_cost = Decimal(str(crop["irrigation_eur_per_ha"])) * declared_area
        protection_cost = Decimal(str(crop["crop_protection_eur_per_ha"])) * declared_area
        total_cost = input_cost + field_cost + irrigation_cost + protection_cost
        gross_income = forecast_tonnes * price
        market_cap = max_tonnes * price
        subsidy = Decimal(str(crop["subsidy_eur_per_ha"])) * declared_area
        gross_with_subsidy = gross_income + byproduct_value + subsidy
        net_margin = gross_with_subsidy - total_cost
        options.append(
            {
                "id": crop["id"],
                "label": crop["label"],
                "category": crop["category"],
                "declared_area_ha": str(declared_area),
                "declared_crop_match": crop["id"] == declared_crop,
                "forecast_yield_tonnes_per_ha": str(forecast_yield_ha.quantize(Decimal("0.01"))),
                "forecast_yield_tonnes": str(forecast_tonnes.quantize(Decimal("0.01"))),
                "max_yield_tonnes_per_ha": str(max_yield_ha.quantize(Decimal("0.01"))),
                "max_yield_tonnes": str(max_tonnes.quantize(Decimal("0.01"))),
                "market_price_eur_per_tonne": str(price),
                "gross_income_eur": str(gross_income.quantize(Decimal("0.01"))),
                "market_cap_eur": str(market_cap.quantize(Decimal("0.01"))),
                "byproduct_income_eur": str(byproduct_value.quantize(Decimal("0.01"))),
                "subsidy_eur": str(subsidy.quantize(Decimal("0.01"))),
                "gross_with_subsidy_eur": str(gross_with_subsidy.quantize(Decimal("0.01"))),
                "total_cost_eur": str(total_cost.quantize(Decimal("0.01"))),
                "net_margin_eur": str(net_margin.quantize(Decimal("0.01"))),
                "soil_score": str((soil_factor * Decimal("100")).quantize(Decimal("1"))),
                "yield_source": "stored database benchmark",
                "industry_rates": {
                    "primary_product": crop["label"],
                    "primary_product_rate_eur_per_tonne": str(price),
                    "market_cap_eur": str(market_cap.quantize(Decimal("0.01"))),
                    "byproducts": byproduct_rates,
                },
                "soil_note": crop["soil_note"],
                "weather_note": crop["weather_note"],
                "solution": crop["solution"],
            }
        )
    best = max(options, key=lambda row: Decimal(row["net_margin_eur"]))
    return {
        "service_name": "Stored Yield Forecast and Techno-Economic Analysis",
        "declared_area_ha": str(declared_area),
        "declared_crop": declared_crop,
        "forecast_source": "stored yield database",
        "weather_forecast": weather_forecast,
        "soil_profile": soil_profile,
        "options": options,
        "best_option": best,
        "solutions": [
            "Use drought-tolerant varieties or delay planting where the weather score falls below 75 percent.",
            "Prioritize crops with high net margin after subsidy, not only high gross income.",
            "Add soil organic matter and moisture retention measures for summer crops on clay-loam fields.",
            "Keep first-sale invoices tied to the selected crop so gross product income can be reconciled against subsidies.",
        ],
    }


def _crop_forecast_catalog() -> list[dict[str, Any]]:
    return [
        {"id": "olives", "label": "Olives", "category": "perennial", "base_yield_tonnes_per_ha": "4.5", "max_factor": "1.18", "market_price_eur_per_tonne": "4300", "input_cost_eur_per_ha": "360", "field_operations_eur_per_ha": "540", "irrigation_eur_per_ha": "210", "crop_protection_eur_per_ha": "185", "subsidy_eur_per_ha": "560", "water_need_mm": "420", "soil_factor": "0.94", "soil_note": "Clay-loam supports olives if drainage is maintained.", "weather_note": "Drought watch reduces oil fruit set without irrigation.", "solution": "Use deficit irrigation, pruning, and fruit-fly monitoring before heat peaks."},
        {"id": "durum_wheat", "label": "Durum wheat", "category": "cereal", "base_yield_tonnes_per_ha": "5.8", "max_factor": "1.12", "market_price_eur_per_tonne": "315", "input_cost_eur_per_ha": "155", "field_operations_eur_per_ha": "410", "irrigation_eur_per_ha": "165", "crop_protection_eur_per_ha": "120", "subsidy_eur_per_ha": "390", "water_need_mm": "360", "soil_factor": "0.91", "soil_note": "Good fit for neutral pH and moderate water holding.", "weather_note": "Low rainfall affects grain fill.", "solution": "Shift sowing date and keep nitrogen split to rainfall events."},
        {"id": "barley", "label": "Barley", "category": "cereal", "base_yield_tonnes_per_ha": "5.2", "max_factor": "1.10", "market_price_eur_per_tonne": "260", "input_cost_eur_per_ha": "130", "field_operations_eur_per_ha": "360", "irrigation_eur_per_ha": "120", "crop_protection_eur_per_ha": "95", "subsidy_eur_per_ha": "350", "water_need_mm": "310", "soil_factor": "0.90", "soil_note": "Tolerates lighter moisture stress than wheat.", "weather_note": "Forecast favors barley over higher-water cereals.", "solution": "Use certified seed and early weed control to protect tillering."},
        {"id": "corn", "label": "Corn", "category": "irrigated", "base_yield_tonnes_per_ha": "11.5", "max_factor": "1.20", "market_price_eur_per_tonne": "245", "input_cost_eur_per_ha": "410", "field_operations_eur_per_ha": "620", "irrigation_eur_per_ha": "520", "crop_protection_eur_per_ha": "210", "subsidy_eur_per_ha": "420", "water_need_mm": "620", "soil_factor": "0.86", "soil_note": "Needs strong moisture management on medium-low water holding soil.", "weather_note": "Current drought watch strongly limits rain-fed yield.", "solution": "Plant only with secured irrigation schedule and evapotranspiration monitoring."},
        {"id": "cotton", "label": "Cotton", "category": "industrial", "base_yield_tonnes_per_ha": "3.6", "max_factor": "1.16", "market_price_eur_per_tonne": "760", "input_cost_eur_per_ha": "390", "field_operations_eur_per_ha": "610", "irrigation_eur_per_ha": "430", "crop_protection_eur_per_ha": "260", "subsidy_eur_per_ha": "740", "water_need_mm": "560", "soil_factor": "0.88", "soil_note": "Moderate fit; compaction must be avoided.", "weather_note": "Heat helps cotton but water stress lowers boll retention.", "solution": "Use drip scheduling and pest scouting before flowering."},
        {"id": "tomatoes", "label": "Processing tomatoes", "category": "vegetable", "base_yield_tonnes_per_ha": "78", "max_factor": "1.14", "market_price_eur_per_tonne": "115", "input_cost_eur_per_ha": "1250", "field_operations_eur_per_ha": "1450", "irrigation_eur_per_ha": "780", "crop_protection_eur_per_ha": "560", "subsidy_eur_per_ha": "520", "water_need_mm": "590", "soil_factor": "0.89", "soil_note": "Good pH, but drainage and calcium management matter.", "weather_note": "Hot dry days increase blossom-end stress.", "solution": "Use drip fertigation, mulch, and calcium monitoring."},
        {"id": "potatoes", "label": "Potatoes", "category": "vegetable", "base_yield_tonnes_per_ha": "34", "max_factor": "1.13", "market_price_eur_per_tonne": "410", "input_cost_eur_per_ha": "980", "field_operations_eur_per_ha": "1380", "irrigation_eur_per_ha": "650", "crop_protection_eur_per_ha": "480", "subsidy_eur_per_ha": "450", "water_need_mm": "520", "soil_factor": "0.82", "soil_note": "Clay-loam can reduce tuber shape unless beds are prepared well.", "weather_note": "Heat and low moisture reduce tuber bulking.", "solution": "Improve ridging, schedule irrigation, and monitor late blight risk."},
        {"id": "grapes", "label": "Wine grapes", "category": "perennial", "base_yield_tonnes_per_ha": "9.0", "max_factor": "1.11", "market_price_eur_per_tonne": "820", "input_cost_eur_per_ha": "520", "field_operations_eur_per_ha": "860", "irrigation_eur_per_ha": "260", "crop_protection_eur_per_ha": "340", "subsidy_eur_per_ha": "480", "water_need_mm": "390", "soil_factor": "0.92", "soil_note": "Neutral pH and moderate drainage support quality grapes.", "weather_note": "Dry weather lowers disease pressure but can reduce berry size.", "solution": "Use canopy management and targeted irrigation at veraison."},
        {"id": "almonds", "label": "Almonds", "category": "perennial", "base_yield_tonnes_per_ha": "2.4", "max_factor": "1.18", "market_price_eur_per_tonne": "3900", "input_cost_eur_per_ha": "620", "field_operations_eur_per_ha": "760", "irrigation_eur_per_ha": "420", "crop_protection_eur_per_ha": "310", "subsidy_eur_per_ha": "530", "water_need_mm": "520", "soil_factor": "0.87", "soil_note": "Needs drainage and salinity monitoring.", "weather_note": "Water stress reduces kernel fill.", "solution": "Use regulated deficit irrigation and bee-pollination planning."},
        {"id": "pistachios", "label": "Pistachios", "category": "perennial", "base_yield_tonnes_per_ha": "1.9", "max_factor": "1.20", "market_price_eur_per_tonne": "6200", "input_cost_eur_per_ha": "690", "field_operations_eur_per_ha": "820", "irrigation_eur_per_ha": "390", "crop_protection_eur_per_ha": "360", "subsidy_eur_per_ha": "540", "water_need_mm": "470", "soil_factor": "0.86", "soil_note": "Moderate fit with careful drainage.", "weather_note": "Dry heat is acceptable if irrigation is reliable.", "solution": "Protect alternate bearing with balanced pruning and irrigation."},
        {"id": "chickpeas", "label": "Chickpeas", "category": "legume", "base_yield_tonnes_per_ha": "2.2", "max_factor": "1.10", "market_price_eur_per_tonne": "780", "input_cost_eur_per_ha": "150", "field_operations_eur_per_ha": "330", "irrigation_eur_per_ha": "80", "crop_protection_eur_per_ha": "100", "subsidy_eur_per_ha": "410", "water_need_mm": "260", "soil_factor": "0.90", "soil_note": "Good low-input option for neutral soil.", "weather_note": "Drought watch is less damaging than for irrigated crops.", "solution": "Use inoculated seed and avoid excess irrigation during flowering."},
        {"id": "lentils", "label": "Lentils", "category": "legume", "base_yield_tonnes_per_ha": "1.8", "max_factor": "1.09", "market_price_eur_per_tonne": "950", "input_cost_eur_per_ha": "135", "field_operations_eur_per_ha": "310", "irrigation_eur_per_ha": "70", "crop_protection_eur_per_ha": "90", "subsidy_eur_per_ha": "405", "water_need_mm": "240", "soil_factor": "0.88", "soil_note": "Works where drainage avoids waterlogging.", "weather_note": "Dry conditions are manageable if emergence is protected.", "solution": "Use clean seed and harvest early to limit shattering."},
        {"id": "beans", "label": "Dry beans", "category": "legume", "base_yield_tonnes_per_ha": "3.0", "max_factor": "1.12", "market_price_eur_per_tonne": "1050", "input_cost_eur_per_ha": "220", "field_operations_eur_per_ha": "420", "irrigation_eur_per_ha": "310", "crop_protection_eur_per_ha": "150", "subsidy_eur_per_ha": "430", "water_need_mm": "430", "soil_factor": "0.84", "soil_note": "Needs better water holding than the declared field currently shows.", "weather_note": "Low moisture raises flower abortion risk.", "solution": "Select only with irrigation and avoid heat during flowering."},
        {"id": "sunflower", "label": "Sunflower", "category": "oilseed", "base_yield_tonnes_per_ha": "3.1", "max_factor": "1.13", "market_price_eur_per_tonne": "470", "input_cost_eur_per_ha": "210", "field_operations_eur_per_ha": "390", "irrigation_eur_per_ha": "150", "crop_protection_eur_per_ha": "130", "subsidy_eur_per_ha": "360", "water_need_mm": "340", "soil_factor": "0.89", "soil_note": "Deep rooting suits medium-low moisture better than corn.", "weather_note": "Forecast supports sunflower if establishment succeeds.", "solution": "Use conservation tillage and monitor broomrape pressure."},
        {"id": "rapeseed", "label": "Rapeseed", "category": "oilseed", "base_yield_tonnes_per_ha": "3.3", "max_factor": "1.10", "market_price_eur_per_tonne": "510", "input_cost_eur_per_ha": "250", "field_operations_eur_per_ha": "420", "irrigation_eur_per_ha": "130", "crop_protection_eur_per_ha": "170", "subsidy_eur_per_ha": "365", "water_need_mm": "380", "soil_factor": "0.86", "soil_note": "Moderate suitability; avoid compaction.", "weather_note": "Needs rain during autumn establishment.", "solution": "Plan sowing after rainfall and use soil cover to conserve moisture."},
        {"id": "alfalfa", "label": "Alfalfa", "category": "forage", "base_yield_tonnes_per_ha": "14.0", "max_factor": "1.15", "market_price_eur_per_tonne": "215", "input_cost_eur_per_ha": "240", "field_operations_eur_per_ha": "520", "irrigation_eur_per_ha": "430", "crop_protection_eur_per_ha": "110", "subsidy_eur_per_ha": "380", "water_need_mm": "650", "soil_factor": "0.85", "soil_note": "Needs reliable water for multiple cuts.", "weather_note": "Drought watch reduces later cuts.", "solution": "Use irrigation budgeting and cut timing based on evapotranspiration."},
        {"id": "oranges", "label": "Oranges", "category": "perennial", "base_yield_tonnes_per_ha": "32", "max_factor": "1.12", "market_price_eur_per_tonne": "430", "input_cost_eur_per_ha": "760", "field_operations_eur_per_ha": "920", "irrigation_eur_per_ha": "520", "crop_protection_eur_per_ha": "390", "subsidy_eur_per_ha": "500", "water_need_mm": "700", "soil_factor": "0.83", "soil_note": "Needs higher water holding and salinity control.", "weather_note": "Current dry pattern increases fruit drop risk.", "solution": "Use mulching, salinity checks, and steady irrigation."},
        {"id": "apples", "label": "Apples", "category": "perennial", "base_yield_tonnes_per_ha": "38", "max_factor": "1.12", "market_price_eur_per_tonne": "620", "input_cost_eur_per_ha": "900", "field_operations_eur_per_ha": "1180", "irrigation_eur_per_ha": "560", "crop_protection_eur_per_ha": "620", "subsidy_eur_per_ha": "510", "water_need_mm": "610", "soil_factor": "0.80", "soil_note": "Declared field is not ideal for high-quality apples.", "weather_note": "Heat stress can reduce color and size.", "solution": "Use shade nets and precision irrigation if planted."},
        {"id": "kiwi", "label": "Kiwi", "category": "perennial", "base_yield_tonnes_per_ha": "30", "max_factor": "1.13", "market_price_eur_per_tonne": "850", "input_cost_eur_per_ha": "1050", "field_operations_eur_per_ha": "1280", "irrigation_eur_per_ha": "720", "crop_protection_eur_per_ha": "520", "subsidy_eur_per_ha": "520", "water_need_mm": "760", "soil_factor": "0.78", "soil_note": "Requires better moisture and wind protection than the demo field shows.", "weather_note": "Dry wind creates high stress.", "solution": "Install windbreaks, fertigation, and moisture sensors before investment."},
        {"id": "watermelon", "label": "Watermelon", "category": "vegetable", "base_yield_tonnes_per_ha": "48", "max_factor": "1.16", "market_price_eur_per_tonne": "280", "input_cost_eur_per_ha": "620", "field_operations_eur_per_ha": "880", "irrigation_eur_per_ha": "520", "crop_protection_eur_per_ha": "330", "subsidy_eur_per_ha": "390", "water_need_mm": "500", "soil_factor": "0.84", "soil_note": "Raised beds and drainage are important on clay-loam.", "weather_note": "Heat is useful, but water stress reduces fruit size.", "solution": "Use mulch, drip irrigation, and staged harvest forecasts."},
    ]


def _industry_byproduct_rates(crop_id: str) -> list[dict[str, str]]:
    rates = {
        "olives": [
            {"name": "olive pomace", "yield_ratio": "0.35", "market_price_eur_per_tonne": "85"},
            {"name": "olive leaves biomass", "yield_ratio": "0.08", "market_price_eur_per_tonne": "55"},
        ],
        "durum_wheat": [
            {"name": "straw", "yield_ratio": "0.80", "market_price_eur_per_tonne": "95"},
            {"name": "bran for milling", "yield_ratio": "0.12", "market_price_eur_per_tonne": "185"},
        ],
        "barley": [
            {"name": "straw", "yield_ratio": "0.75", "market_price_eur_per_tonne": "90"},
            {"name": "feed screenings", "yield_ratio": "0.05", "market_price_eur_per_tonne": "150"},
        ],
        "corn": [
            {"name": "stover", "yield_ratio": "0.90", "market_price_eur_per_tonne": "65"},
            {"name": "cobs", "yield_ratio": "0.18", "market_price_eur_per_tonne": "70"},
        ],
        "cotton": [
            {"name": "cottonseed", "yield_ratio": "0.55", "market_price_eur_per_tonne": "310"},
            {"name": "stalk biomass", "yield_ratio": "0.70", "market_price_eur_per_tonne": "45"},
        ],
        "tomatoes": [
            {"name": "tomato pomace", "yield_ratio": "0.06", "market_price_eur_per_tonne": "42"},
            {"name": "seed extract material", "yield_ratio": "0.01", "market_price_eur_per_tonne": "260"},
        ],
        "potatoes": [
            {"name": "processing peel", "yield_ratio": "0.08", "market_price_eur_per_tonne": "38"},
            {"name": "cull potatoes feed", "yield_ratio": "0.07", "market_price_eur_per_tonne": "70"},
        ],
        "grapes": [
            {"name": "grape pomace", "yield_ratio": "0.20", "market_price_eur_per_tonne": "70"},
            {"name": "grape seed", "yield_ratio": "0.04", "market_price_eur_per_tonne": "220"},
        ],
        "almonds": [
            {"name": "almond hulls", "yield_ratio": "1.20", "market_price_eur_per_tonne": "135"},
            {"name": "almond shells", "yield_ratio": "0.45", "market_price_eur_per_tonne": "75"},
        ],
        "pistachios": [
            {"name": "pistachio hulls", "yield_ratio": "0.90", "market_price_eur_per_tonne": "80"},
            {"name": "pistachio shells", "yield_ratio": "0.35", "market_price_eur_per_tonne": "95"},
        ],
        "chickpeas": [
            {"name": "haulm feed", "yield_ratio": "0.70", "market_price_eur_per_tonne": "85"},
            {"name": "split/broken pulses", "yield_ratio": "0.04", "market_price_eur_per_tonne": "420"},
        ],
        "lentils": [
            {"name": "straw feed", "yield_ratio": "0.65", "market_price_eur_per_tonne": "80"},
            {"name": "split/broken pulses", "yield_ratio": "0.04", "market_price_eur_per_tonne": "500"},
        ],
        "beans": [
            {"name": "haulm feed", "yield_ratio": "0.60", "market_price_eur_per_tonne": "75"},
            {"name": "split/broken beans", "yield_ratio": "0.05", "market_price_eur_per_tonne": "520"},
        ],
        "sunflower": [
            {"name": "sunflower meal", "yield_ratio": "0.58", "market_price_eur_per_tonne": "255"},
            {"name": "hulls", "yield_ratio": "0.18", "market_price_eur_per_tonne": "70"},
        ],
        "rapeseed": [
            {"name": "rapeseed meal", "yield_ratio": "0.60", "market_price_eur_per_tonne": "285"},
            {"name": "straw biomass", "yield_ratio": "0.70", "market_price_eur_per_tonne": "55"},
        ],
        "alfalfa": [
            {"name": "leaf meal", "yield_ratio": "0.18", "market_price_eur_per_tonne": "240"},
            {"name": "stem bedding", "yield_ratio": "0.20", "market_price_eur_per_tonne": "65"},
        ],
        "oranges": [
            {"name": "citrus peel", "yield_ratio": "0.45", "market_price_eur_per_tonne": "55"},
            {"name": "essential oil fraction", "yield_ratio": "0.004", "market_price_eur_per_tonne": "1800"},
        ],
        "apples": [
            {"name": "apple pomace", "yield_ratio": "0.25", "market_price_eur_per_tonne": "52"},
            {"name": "juice grade culls", "yield_ratio": "0.08", "market_price_eur_per_tonne": "110"},
        ],
        "kiwi": [
            {"name": "juice grade culls", "yield_ratio": "0.08", "market_price_eur_per_tonne": "130"},
            {"name": "kiwi pomace", "yield_ratio": "0.12", "market_price_eur_per_tonne": "50"},
        ],
        "watermelon": [
            {"name": "juice grade fruit", "yield_ratio": "0.10", "market_price_eur_per_tonne": "75"},
            {"name": "rind biomass", "yield_ratio": "0.18", "market_price_eur_per_tonne": "28"},
        ],
    }
    return rates.get(crop_id, [{"name": "field residue", "yield_ratio": "0.20", "market_price_eur_per_tonne": "40"}])


def _seed_analysis(crop_seasons: list[Any], parcels: list[Any]) -> dict[str, Any]:
    parcel_by_id = {parcel.parcel_id: parcel for parcel in parcels}
    collective_database = _seed_collective_database()
    records = []
    for crop in crop_seasons:
        parcel = parcel_by_id.get(crop.parcel_id)
        benchmark = collective_database.get(crop.production_type, collective_database["olives"])
        area = crop.labelled_area_ha
        declared = crop.declared_yield_tonnes or Decimal("0")
        verified = crop.verified_yield_tonnes or Decimal("0")
        seed_requirement = area * Decimal(str(benchmark["seed_rate_tonnes_per_ha"]))
        expected_yield = area * Decimal(str(benchmark["expected_yield_tonnes_per_ha"]))
        seed_cost = area * Decimal(str(benchmark["seed_cost_eur_per_ha"]))
        field_operations = area * Decimal(str(benchmark["field_operations_eur_per_ha"]))
        irrigation = area * Decimal(str(benchmark["irrigation_eur_per_ha"]))
        crop_protection = area * Decimal(str(benchmark["crop_protection_eur_per_ha"]))
        total_cost = seed_cost + field_operations + irrigation + crop_protection
        gross_revenue = verified * Decimal(str(benchmark["market_price_eur_per_tonne"]))
        net_margin = gross_revenue - total_cost
        break_even_yield = total_cost / Decimal(str(benchmark["market_price_eur_per_tonne"])) if total_cost else Decimal("0")
        roi = (net_margin / total_cost * Decimal("100")) if total_cost else Decimal("0")
        variance = declared - verified
        records.append(
            {
                "parcel_id": crop.parcel_id,
                "cadastral_reference": parcel.cadastral_reference if parcel is not None else "unknown",
                "production_type": crop.production_type,
                "seed_variety": benchmark["variety"],
                "seed_lot": benchmark["seed_lot"],
                "owned_area_ha": str(area),
                "declared_seed_tonnes": str(seed_requirement),
                "expected_production_tonnes": str(expected_yield),
                "declared_production_tonnes": str(declared),
                "verified_production_tonnes": str(verified),
                "variance_tonnes": str(variance),
                "seed_cost_eur": str(seed_cost),
                "operating_cost_eur": str(total_cost),
                "gross_revenue_eur": str(gross_revenue),
                "net_margin_eur": str(net_margin),
                "break_even_yield_tonnes": str(break_even_yield),
                "roi_percent": str(roi),
                "techno_economic_notes": benchmark["techno_economic_notes"],
                "status": "aligned" if abs(variance) <= Decimal("2.5") else "review",
            }
        )
    total_cost = sum((Decimal(record["operating_cost_eur"]) for record in records), Decimal("0"))
    total_revenue = sum((Decimal(record["gross_revenue_eur"]) for record in records), Decimal("0"))
    total_margin = total_revenue - total_cost
    return {
        "records": records,
        "collective_database": list(collective_database.values()),
        "summary": {
            "sample_regions": 4,
            "sample_farms": 128,
            "total_operating_cost_eur": str(total_cost),
            "total_gross_revenue_eur": str(total_revenue),
            "total_net_margin_eur": str(total_margin),
            "average_roi_percent": str((total_margin / total_cost * Decimal("100")) if total_cost else Decimal("0")),
        },
        "recommendations": [
            "Prioritize certified seed lots with traceable invoices and parcel-level sowing logs.",
            "Flag any declared yield more than 15 percent above the collective benchmark for agronomist review.",
            "Use weather and irrigation evidence before approving drought-related seed loss compensation.",
            "Compare first-sale units against verified production before calculating gross product deductions.",
        ],
    }


def _seed_collective_database() -> dict[str, dict[str, Any]]:
    return {
        "olives": {
            "production_type": "olives",
            "variety": "Koroneiki certified nursery stock",
            "seed_lot": "EL-OLV-2026-001",
            "sample_region": "Attica and Peloponnese",
            "sample_farms": 42,
            "seed_rate_tonnes_per_ha": "0.18",
            "expected_yield_tonnes_per_ha": "4.50",
            "market_price_eur_per_tonne": "4300",
            "seed_cost_eur_per_ha": "360",
            "field_operations_eur_per_ha": "540",
            "irrigation_eur_per_ha": "210",
            "crop_protection_eur_per_ha": "185",
            "water_need_mm": "420",
            "techno_economic_notes": "High-value perennial crop; margin depends on oil quality, irrigation stress, and verified first-sale invoices.",
        },
        "cereals": {
            "production_type": "cereals",
            "variety": "Durum wheat EL-DW26",
            "seed_lot": "EL-CER-2026-014",
            "sample_region": "Thessaly",
            "sample_farms": 36,
            "seed_rate_tonnes_per_ha": "0.22",
            "expected_yield_tonnes_per_ha": "5.80",
            "market_price_eur_per_tonne": "315",
            "seed_cost_eur_per_ha": "155",
            "field_operations_eur_per_ha": "410",
            "irrigation_eur_per_ha": "165",
            "crop_protection_eur_per_ha": "120",
            "water_need_mm": "360",
            "techno_economic_notes": "Lower unit price but stable benchmark; nitrogen, fuel, and rainfall timing drive the margin.",
        },
        "cotton": {
            "production_type": "cotton",
            "variety": "FiberMax GR-26",
            "seed_lot": "EL-COT-2026-009",
            "sample_region": "Macedonia and Thessaly",
            "sample_farms": 31,
            "seed_rate_tonnes_per_ha": "0.035",
            "expected_yield_tonnes_per_ha": "3.40",
            "market_price_eur_per_tonne": "760",
            "seed_cost_eur_per_ha": "210",
            "field_operations_eur_per_ha": "620",
            "irrigation_eur_per_ha": "310",
            "crop_protection_eur_per_ha": "240",
            "water_need_mm": "650",
            "techno_economic_notes": "Irrigation intensive; quality premiums and ginning deductions should be reconciled with first-sale records.",
        },
        "legumes": {
            "production_type": "legumes",
            "variety": "Chickpea local protein line",
            "seed_lot": "EL-LEG-2026-006",
            "sample_region": "Central Greece",
            "sample_farms": 19,
            "seed_rate_tonnes_per_ha": "0.16",
            "expected_yield_tonnes_per_ha": "2.10",
            "market_price_eur_per_tonne": "980",
            "seed_cost_eur_per_ha": "180",
            "field_operations_eur_per_ha": "350",
            "irrigation_eur_per_ha": "95",
            "crop_protection_eur_per_ha": "85",
            "water_need_mm": "260",
            "techno_economic_notes": "Lower water pressure and useful rotation value; gross margin improves when storage losses are controlled.",
        },
    }


def _audit_analysis(audit_events: list[dict[str, Any]], subsidy_claim: Any, documents: list[dict[str, Any]]) -> dict[str, Any]:
    missing_documents = [requirement for requirement in _document_requirements(documents) if requirement["status"] == "needed"]
    return {
        "score": 94 if not subsidy_claim.risk_flags else 68,
        "findings": [
            {"level": "ok", "text": "Parcel and crop-season records are linked"},
            {"level": "ok", "text": "Remote sensing confidence is above review threshold"},
            {"level": "warn", "text": f"{len(missing_documents)} required document groups still need upload"},
        ],
        "event_count": len(audit_events),
        "risk_flags": list(subsidy_claim.risk_flags),
    }


def _crisis_management(compensation: Any | None, annual_ledger: Any) -> dict[str, Any]:
    final_amount = compensation.final_amount_eur if compensation is not None else Decimal("0")
    property_value = annual_ledger.first_sale_revenue_eur + Decimal("18500")
    destruction_loss = property_value * Decimal("0.40")
    collective_loss = destruction_loss + annual_ledger.first_sale_revenue_eur * Decimal("0.30")
    return {
        "active_incident": "Demo drought event",
        "severity": "moderate",
        "response_status": "eligible for assessment",
        "gross_payment_eur": str(final_amount),
        "property_value_eur": str(property_value),
        "property_destruction_loss_eur": str(destruction_loss),
        "collective_revenue_loss_eur": str(collective_loss),
        "weather_trigger": "rainfall deficit and low soil moisture",
        "scenarios": [
            {"label": "Drought 20%", "value": "234.60"},
            {"label": "Drought 40%", "value": str(final_amount)},
            {"label": "Flood 60%", "value": "703.80"},
            {"label": "Fire 80%", "value": "938.40"},
        ],
    }


def _assistant_prompts(documents: list[dict[str, Any]], subsidy_claim: Any) -> list[dict[str, str]]:
    missing = [requirement["label"] for requirement in _document_requirements(documents) if requirement["status"] == "needed"]
    next_step = "Upload remaining documents" if missing else "Review payment calculation"
    risk_note = "No subsidy risk flags are active" if not subsidy_claim.risk_flags else ", ".join(subsidy_claim.risk_flags)
    return [
        {"role": "assistant", "message": "Welcome. I can guide your land declaration, document upload, audit review, and payment forecast."},
        {"role": "assistant", "message": f"Next recommended step: {next_step}."},
        {"role": "assistant", "message": f"Audit status: {risk_note}."},
        {"role": "assistant", "message": "For land declaration, start with Google Maps draw or import a Google Earth KML boundary."},
    ]


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgroLedger Farmer Portal</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #18221d;
      --muted: #657169;
      --line: #d7dfdb;
      --panel: #ffffff;
      --field: #f4f7f5;
      --green: #2d7650;
      --blue: #286f9e;
      --gold: #ad7a25;
      --red: #a6473b;
      --violet: #6656a6;
      --shadow: 0 10px 26px rgba(29, 47, 37, .10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-width: 320px;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: #eef2ef;
    }
    button, input, select { font: inherit; }
    button {
      min-height: 38px;
      border: 1px solid #245f3f;
      background: var(--green);
      color: white;
      border-radius: 8px;
      padding: 8px 12px;
      font-weight: 700;
      cursor: pointer;
    }
    button.secondary { background: white; color: var(--ink); border-color: var(--line); }
    button.blue { background: var(--blue); border-color: #215b82; }
    button.gold { background: var(--gold); border-color: #805a1d; }
    .login {
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background:
        linear-gradient(120deg, rgba(45,118,80,.18), rgba(40,111,158,.14)),
        #edf3ef;
    }
    .login-panel {
      width: min(980px, 100%);
      display: grid;
      grid-template-columns: 1fr 360px;
      gap: 18px;
      align-items: stretch;
    }
    .login-copy, .login-form, .card, .modal-panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .login-copy { padding: 30px; }
    .login-copy h1 { margin: 0 0 10px; font-size: 32px; letter-spacing: 0; }
    .login-copy p { margin: 0; color: var(--muted); line-height: 1.5; }
    .login-form { padding: 22px; }
    label { display: block; color: var(--muted); font-size: 13px; font-weight: 700; margin-bottom: 6px; }
    input, select {
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: white;
      color: var(--ink);
    }
    .field { margin-bottom: 12px; }
    .app { display: none; min-height: 100vh; }
    .shell { display: grid; grid-template-columns: 248px minmax(0, 1fr); min-height: 100vh; }
    aside {
      background: #17221c;
      color: #edf7f0;
      padding: 18px;
      position: sticky;
      top: 0;
      height: 100vh;
    }
    .brand { font-size: 19px; font-weight: 800; margin-bottom: 16px; }
    nav { display: grid; gap: 8px; }
    nav button {
      width: 100%;
      text-align: left;
      background: transparent;
      border-color: rgba(255,255,255,.16);
      color: #edf7f0;
    }
    nav button.active { background: #2d7650; border-color: #2d7650; }
    main { min-width: 0; }
    header {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: center;
      padding: 16px 22px;
      background: rgba(249,251,250,.94);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(10px);
    }
    h1, h2, h3 { letter-spacing: 0; }
    header h1 { margin: 0; font-size: 22px; }
    header p { margin: 3px 0 0; color: var(--muted); font-size: 13px; }
    .content { padding: 18px 22px 96px; }
    .grid { display: grid; gap: 14px; }
    .metrics { grid-template-columns: repeat(5, minmax(140px, 1fr)); }
    .two { grid-template-columns: minmax(0, 1fr) minmax(320px, .72fr); align-items: start; }
    .three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .card { padding: 16px; box-shadow: 0 1px 2px rgba(28, 42, 34, .04); }
    .metric strong { display: block; font-size: 26px; margin-bottom: 5px; }
    .metric span, .muted { color: var(--muted); font-size: 13px; line-height: 1.4; }
    .card h2 { margin: 0 0 12px; font-size: 17px; }
    .card h3 { margin: 0 0 8px; font-size: 15px; }
    .status, .tag {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 999px;
      background: #e6f2eb;
      color: #215b39;
      font-size: 12px;
      font-weight: 700;
    }
    .tag.warn { background: #fbf0d9; color: #7d5517; }
    .tag.blue { background: #e4f0f8; color: #20577e; }
    .fact { display: flex; justify-content: space-between; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--line); }
    .fact:last-child { border-bottom: 0; }
    .fact strong { text-align: right; }
    .money { color: var(--green); font-weight: 800; }
    .warn-text { color: var(--gold); font-weight: 800; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); font-size: 14px; vertical-align: top; }
    th { color: var(--muted); background: var(--field); }
    canvas { width: 100%; height: 210px; display: block; background: #fbfdfc; border: 1px solid var(--line); border-radius: 8px; }
    .map-shell {
      min-height: 280px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(90deg, rgba(45,118,80,.18) 1px, transparent 1px),
        linear-gradient(0deg, rgba(40,111,158,.16) 1px, transparent 1px),
        #f8fbf9;
      background-size: 36px 36px;
      position: relative;
      overflow: hidden;
    }
    .google-map {
      width: 100%;
      height: 320px;
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 10px;
      background: var(--field);
    }
    .parcel {
      position: absolute;
      left: 24%;
      top: 22%;
      width: 46%;
      height: 42%;
      border: 3px solid var(--green);
      background: rgba(45,118,80,.16);
      transform: rotate(-4deg);
    }
    .map-actions, .quick-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .forecast-window {
      border: 2px solid #c8d8d0;
      border-radius: 8px;
      background: #fbfdfc;
      padding: 14px;
    }
    .forecast-controls {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(130px, .45fr));
      gap: 12px;
      align-items: end;
      margin-bottom: 14px;
    }
    .forecast-strip {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .mini-metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: white;
      padding: 12px;
      min-height: 82px;
    }
    .mini-metric strong { display: block; font-size: 19px; margin-bottom: 4px; }
    .mini-metric span { color: var(--muted); font-size: 12px; line-height: 1.35; }
    .overlay-actions {
      position: fixed;
      right: 18px;
      bottom: 18px;
      z-index: 20;
      display: grid;
      gap: 10px;
    }
    .overlay-actions button {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      padding: 0;
      box-shadow: var(--shadow);
    }
    .section { display: none; }
    .section.active { display: block; }
    .modal {
      position: fixed;
      inset: 0;
      z-index: 30;
      display: none;
      place-items: center;
      padding: 18px;
      background: rgba(18, 30, 23, .48);
    }
    .modal.open { display: grid; }
    .modal-panel { width: min(720px, 100%); padding: 18px; max-height: 86vh; overflow: auto; }
    .modal-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
    .messages {
      height: 340px;
      overflow: auto;
      display: grid;
      gap: 8px;
      align-content: start;
      border: 1px solid var(--line);
      background: var(--field);
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 10px;
    }
    .message { max-width: 84%; padding: 9px 10px; border-radius: 8px; background: white; border: 1px solid var(--line); }
    .message.user { justify-self: end; background: #e4f0f8; }
    .chat-row { display: grid; grid-template-columns: 1fr auto; gap: 8px; }
    .mobile-menu { display: none; }
    @media (max-width: 980px) {
      .shell { grid-template-columns: 1fr; }
      aside { position: static; height: auto; }
      nav { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .metrics, .two, .three { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .forecast-controls, .forecast-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      header { align-items: flex-start; flex-direction: column; }
    }
    @media (max-width: 680px) {
      .login-panel { grid-template-columns: 1fr; }
      .login-copy h1 { font-size: 26px; }
      .content, header { padding-left: 14px; padding-right: 14px; }
      nav { grid-template-columns: 1fr; }
      .metrics, .two, .three { grid-template-columns: 1fr; }
      .forecast-controls, .forecast-strip { grid-template-columns: 1fr; }
      .quick-actions { width: 100%; }
      .quick-actions button { flex: 1 1 130px; }
      .overlay-actions { right: 12px; bottom: 12px; }
    }
  </style>
</head>
<body>
  <section class="login" id="login">
    <div class="login-panel">
      <div class="login-copy">
        <h1>AgroLedger Farmer Portal</h1>
        <p>Secure local portal for land declarations, document submission, audit analysis, financial review, subsidy payment forecasts, crisis management, and guided assistance.</p>
        <div class="quick-actions">
          <span class="tag">Container services ready</span>
          <span class="tag blue">Demo identity enabled</span>
          <span class="tag warn">Local MVP mode</span>
        </div>
      </div>
      <form class="login-form" id="login-form">
        <div class="field">
          <label for="tax-id">Tax identifier</label>
          <input id="tax-id" value="EL123456789" autocomplete="username">
        </div>
        <div class="field">
          <label for="password">Password</label>
          <input id="password" type="password" value="demo" autocomplete="current-password">
        </div>
        <button type="submit">Enter Dashboard</button>
        <p class="muted">Use the demo credentials already filled in to inspect the initialized container.</p>
      </form>
    </div>
  </section>

  <section class="app" id="app">
    <div class="shell">
      <aside>
        <div class="brand">AgroLedger</div>
        <nav id="nav">
          <button class="active" data-section="overview">Overview</button>
          <button data-section="documents">Documents</button>
          <button data-section="land">Land Declaration</button>
          <button data-section="forecast">Crop Forecast</button>
          <button data-section="audit">Audit Analysis</button>
          <button data-section="finance">Financials</button>
          <button data-section="crisis">Crisis Management</button>
        </nav>
      </aside>
      <main>
        <header>
          <div>
            <h1 id="page-title">Overview</h1>
            <p id="page-subtitle">Loading initialized services</p>
          </div>
          <div class="quick-actions">
            <button class="secondary" id="refresh" type="button">Refresh</button>
            <button class="blue" data-open="upload">Upload</button>
            <button class="gold" data-open="assistant">Assistant</button>
            <button class="secondary" id="logout" type="button">Logout</button>
          </div>
        </header>
        <div class="content">
          <section class="section active" id="overview"></section>
          <section class="section" id="documents"></section>
          <section class="section" id="land"></section>
          <section class="section" id="forecast"></section>
          <section class="section" id="audit"></section>
          <section class="section" id="finance"></section>
          <section class="section" id="crisis"></section>
        </div>
      </main>
    </div>
    <div class="overlay-actions">
      <button title="Upload documents" data-open="upload">UP</button>
      <button title="Declare land" data-section-jump="land">LD</button>
      <button title="Open assistant" data-open="assistant">AI</button>
    </div>
  </section>

  <div class="modal" id="upload-modal">
    <div class="modal-panel">
      <div class="modal-head">
        <h2>Upload Required Document</h2>
        <button class="secondary" data-close="upload">Close</button>
      </div>
      <form id="upload-form">
        <div class="field">
          <label for="document-type">Document type</label>
          <select id="document-type">
            <option value="identity">Identity and tax certificate</option>
            <option value="land">Land title, lease, or cadastral extract</option>
            <option value="finance">Financial records and invoices</option>
            <option value="bank">IBAN proof</option>
            <option value="crisis">Crisis incident evidence</option>
          </select>
        </div>
        <div class="field">
          <label for="file-input">File</label>
          <input id="file-input" type="file">
        </div>
        <button type="submit">Submit Document</button>
      </form>
    </div>
  </div>

  <div class="modal" id="assistant-modal">
    <div class="modal-panel">
      <div class="modal-head">
        <h2>Application Assistant</h2>
        <button class="secondary" data-close="assistant">Close</button>
      </div>
      <div class="messages" id="messages"></div>
      <form class="chat-row" id="chat-form">
        <input id="chat-input" placeholder="Ask about documents, land, audit, finance, crisis, or payment">
        <button type="submit">Send</button>
      </form>
    </div>
  </div>

  <script>
    let state = null;
    let selectedCropId = null;
    let cropAnalysisReady = false;
    const titles = {
      overview: ["Overview", "Initialized services, payment outlook, and farmer profile"],
      documents: ["Documents", "Upload and review all required farmer records"],
      land: ["Land Declaration", "Declare parcels from Google Maps, Google Earth, or GeoJSON"],
      forecast: ["Crop Forecast", "Stored yield database and techno-economic analysis"],
      audit: ["Audit Analysis", "Risk scoring, evidence checks, and audit trail"],
      finance: ["Financials", "Submitted finance records and subsidy payment scenarios"],
      crisis: ["Crisis Management", "Incident response and gross payment forecasts"],
    };
    const money = (value) => `EUR ${Number(value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    const fact = (label, value, cls = "") => `<div class="fact"><span class="muted">${label}</span><strong class="${cls}">${value}</strong></div>`;
    const card = (title, body) => `<div class="card"><h2>${title}</h2>${body}</div>`;

    document.getElementById("login-form").addEventListener("submit", (event) => {
      event.preventDefault();
      document.getElementById("login").style.display = "none";
      document.getElementById("app").style.display = "block";
      loadDashboard();
    });

    document.getElementById("nav").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-section]");
      if (!button) return;
      showSection(button.dataset.section);
    });

    document.querySelectorAll("[data-section-jump]").forEach((button) => {
      button.addEventListener("click", () => showSection(button.dataset.sectionJump));
    });
    document.querySelectorAll("[data-open]").forEach((button) => {
      button.addEventListener("click", () => document.getElementById(`${button.dataset.open}-modal`).classList.add("open"));
    });
    document.querySelectorAll("[data-close]").forEach((button) => {
      button.addEventListener("click", () => document.getElementById(`${button.dataset.close}-modal`).classList.remove("open"));
    });
    document.getElementById("refresh").addEventListener("click", loadDashboard);
    document.getElementById("logout").addEventListener("click", () => {
      document.getElementById("app").style.display = "none";
      document.getElementById("login").style.display = "grid";
      document.getElementById("password").value = "";
    });

    document.getElementById("upload-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = document.getElementById("file-input");
      const file = input.files[0];
      if (!file || !state) return;
      await fetch("/documents", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          farmer_id: state.farmer.farmer_id,
          document_type: document.getElementById("document-type").value,
          file_name: file.name,
          file_size: file.size,
        }),
      });
      input.value = "";
      document.getElementById("upload-modal").classList.remove("open");
      await loadDashboard();
      showSection("documents");
    });

    document.getElementById("chat-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const input = document.getElementById("chat-input");
      const text = input.value.trim();
      if (!text) return;
      addMessage("user", text);
      input.value = "";
      addMessage("assistant", assistantReply(text));
    });

    async function loadDashboard() {
      const response = await fetch("/dashboard/data");
      if (!response.ok) throw new Error(`Dashboard data failed: ${response.status}`);
      state = await response.json();
      renderAll();
    }

    function showSection(id) {
      document.querySelectorAll(".section").forEach((section) => section.classList.toggle("active", section.id === id));
      document.querySelectorAll("nav button").forEach((button) => button.classList.toggle("active", button.dataset.section === id));
      document.getElementById("page-title").textContent = titles[id][0];
      document.getElementById("page-subtitle").textContent = titles[id][1];
      if (state) requestAnimationFrame(drawCharts);
    }

    function renderAll() {
      renderOverview();
      renderDocuments();
      renderLand();
      renderCropForecast();
      renderAudit();
      renderFinance();
      renderCrisis();
      renderAssistant();
      document.getElementById("page-subtitle").textContent = `${state.farmer.legal_name} - all container services initialized`;
      requestAnimationFrame(drawCharts);
    }

    function renderOverview() {
      const s = state.summary;
      document.getElementById("overview").innerHTML = `
        <div class="grid metrics">
          ${metric("Gross support", money(state.financial_analysis.gross_public_support_eur))}
          ${metric("Net after offsets", money(state.financial_analysis.net_after_offsets_eur))}
          ${metric("Product net", money(state.financial_analysis.first_sale_deductions.net_product_after_deductions_eur))}
          ${metric("Documents", `${s.documents}/5`)}
          ${metric("Forecast risk", state.crop_forecast.weather_forecast.current.risk)}
          ${metric("Best crop", state.crop_forecast.best_option.label)}
        </div>
        <div class="grid two">
          ${card("Farmer Profile", [
            fact("Name", state.farmer.legal_name),
            fact("Tax identifier", state.farmer.tax_identifier),
            fact("Farmer type", state.farmer.farmer_type),
            fact("Active farmer", state.farmer.active_farmer ? "Yes" : "No"),
          ].join(""))}
          ${card("Payment Due", [
            fact("Subsidy final", money(state.subsidy_claim.final_amount_eur), "money"),
            fact("Debt offset", money(state.subsidy_claim.debt_offset.offset_eur), "warn-text"),
            fact("Disbursable subsidy", money(state.subsidy_claim.debt_offset.disbursable_eur), "money"),
            fact("Crisis gross", money(state.crisis_management.gross_payment_eur), "money"),
            fact("Revenue loss", money(state.crisis_management.collective_revenue_loss_eur), "warn-text"),
          ].join(""))}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Initialized Services", servicesTable())}
          ${card("Payment Graph", '<canvas id="payment-chart"></canvas>')}
        </div>`;
    }

    function renderDocuments() {
      document.getElementById("documents").innerHTML = `
        <div class="grid two">
          ${card("Required Records", requirementsTable())}
          ${card("Submitted Documents", documentsTable())}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Upload Actions", '<div class="quick-actions"><button data-open="upload">Upload document</button><button class="secondary" data-section-jump="audit">Review audit</button></div><p class="muted">The portal records document metadata, assigns a review status, and feeds audit and financial analysis.</p>')}
          ${card("Document Analysis", documentAnalysis())}
        </div>`;
      rebindDynamicButtons();
    }

    function renderLand() {
      const land = state.land_declaration;
      document.getElementById("land").innerHTML = `
        <div class="grid two">
          <div class="card">
            <h2>Google Maps Declaration Workspace</h2>
            <iframe class="google-map" title="Google Maps parcel center" loading="lazy" src="${land.google_maps_url}&output=embed"></iframe>
            <div class="map-shell"><div class="parcel"></div></div>
            <div class="map-actions">
              <button onclick="window.open('${land.google_maps_url}', '_blank')">Open Google Maps</button>
              <button class="blue">Import Google Earth KML</button>
              <button class="secondary">Upload GeoJSON</button>
            </div>
          </div>
          ${card("Parcel State", [
            fact("Active source", land.active_source),
            fact("Map center", `${land.map_center.lat}, ${land.map_center.lon}`),
            fact("Declared area", `${land.declared_area_ha} ha`),
            fact("Eligible area", `${land.eligible_area_ha} ha`),
          ].join("") + sourcesList(land.sources))}
        </div>`;
    }

    function renderCropForecast() {
      const forecast = state.crop_forecast;
      const selected = selectedForecast();
      const result = cropAnalysisReady ? forecastResult(selected) : `<div class="card"><h2>Techno-Economic Analysis</h2><p class="muted">Select a crop type from the stored yield database and press Run Analysis to calculate yearly yield, cost, gross income, subsidy, and margin.</p></div>`;
      document.getElementById("forecast").innerHTML = `
        <div class="forecast-window">
          <div class="forecast-controls">
            <div>
              <label for="crop-select">Crop yield type</label>
              <select id="crop-select">${forecast.options.map((row) => `<option value="${row.id}" ${row.id === selected.id ? "selected" : ""}>${row.label} - ${row.forecast_yield_tonnes_per_ha} t/ha</option>`).join("")}</select>
            </div>
            <div>${fact("Declared area", `${forecast.declared_area_ha} ha`)}</div>
            <div>${fact("Forecast source", forecast.forecast_source)}</div>
            <div><button id="run-crop-analysis" type="button">Run Analysis</button></div>
          </div>
          <div class="grid two">
            ${card("Stored DB Yields", cropForecastTable())}
            ${card("Forecast Service Weather", forecastWeather())}
          </div>
          <div class="grid two" style="margin-top:14px">
            ${card("Weather Rain Graph", '<canvas id="forecast-weather-chart"></canvas>')}
            ${card("Market Cap Graph", '<canvas id="market-cap-chart"></canvas>')}
          </div>
          <div id="forecast-result" style="margin-top:14px">${result}</div>
        </div>`;
      document.getElementById("crop-select").addEventListener("change", (event) => {
        selectedCropId = event.target.value;
        cropAnalysisReady = false;
        renderCropForecast();
      });
      document.getElementById("run-crop-analysis").addEventListener("click", () => {
        selectedCropId = document.getElementById("crop-select").value;
        cropAnalysisReady = true;
        renderCropForecast();
      });
      requestAnimationFrame(drawCharts);
    }

    function renderAudit() {
      document.getElementById("audit").innerHTML = `
        <div class="grid two">
          ${card("Audit Score", `<canvas id="audit-chart"></canvas>`)}
          ${card("Findings", state.audit_analysis.findings.map((f) => `<div class="fact"><span>${f.text}</span><strong class="${f.level === "warn" ? "warn-text" : "money"}">${f.level}</strong></div>`).join(""))}
        </div>
        <div class="card" style="margin-top:14px">
          <h2>Recent Audit Trail</h2>
          <table><thead><tr><th>Action</th><th>Entity</th><th>Created</th></tr></thead><tbody>${state.audit_events.map((event) => `<tr><td>${event.action}</td><td>${event.entity_type}</td><td>${event.created_at}</td></tr>`).join("")}</tbody></table>
        </div>`;
    }

    function renderFinance() {
      const selected = selectedForecast();
      document.getElementById("finance").innerHTML = `
        <div class="forecast-window" style="margin-bottom:14px">
          <div class="forecast-controls">
            <div>
              <label for="finance-crop-select">Stated yield choice</label>
              <select id="finance-crop-select">${state.crop_forecast.options.map((row) => `<option value="${row.id}" ${row.id === selected.id ? "selected" : ""}>${row.label} - ${row.forecast_yield_tonnes_per_ha} t/ha</option>`).join("")}</select>
            </div>
            <div>${fact("Forecast yield", `${selected.forecast_yield_tonnes} t`)}</div>
            <div>${fact("Market cap", money(selected.market_cap_eur), "money")}</div>
            <div>${fact("By-product value", money(selected.byproduct_income_eur), "money")}</div>
          </div>
        </div>
        <div class="grid two">
          ${card("Financial Analysis", [
            fact("Gross public support", money(state.financial_analysis.gross_public_support_eur), "money"),
            fact("Tax and debt exposure", money(state.financial_analysis.tax_and_debt_exposure_eur), "warn-text"),
            fact("Net after offsets", money(state.financial_analysis.net_after_offsets_eur), "money"),
            fact("Document coverage", state.financial_analysis.document_coverage),
          ].join(""))}
          ${card("Revenue and Support Graph", '<canvas id="finance-chart"></canvas>')}
        </div>
        <div class="card" style="margin-top:14px">
          <h2>Payment Scenarios</h2>
          <table><thead><tr><th>Condition</th><th>Gross output</th><th>Net output</th></tr></thead><tbody>${state.financial_analysis.payment_scenarios.map((row) => `<tr><td>${row.label}</td><td>${money(row.gross)}</td><td>${money(row.net)}</td></tr>`).join("")}</tbody></table>
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("First Sold Units Deduction", [
            fact("Sold quantity", `${state.financial_analysis.first_sale_deductions.sold_quantity_tonnes} tonnes`),
            fact("Gross product value", money(state.financial_analysis.first_sale_deductions.gross_product_value_eur), "money"),
            fact("First-sale tax", money(state.financial_analysis.first_sale_deductions.first_sale_tax_eur), "warn-text"),
            fact("Market fee", money(state.financial_analysis.first_sale_deductions.market_fee_eur), "warn-text"),
            fact("Net product value", money(state.financial_analysis.first_sale_deductions.net_product_after_deductions_eur), "money"),
          ].join(""))}
          ${card("Stated Yield Industry Analysis", industryAnalysis(selected))}
        </div>
        <div class="grid three" style="margin-top:14px">
          ${card("Yield Value Graph", '<canvas id="finance-yield-chart"></canvas>')}
          ${card("Product and By-product Rates", '<canvas id="industry-rates-chart"></canvas>')}
          ${card("Market Cap vs Margin", '<canvas id="finance-market-chart"></canvas>')}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("By-product Revenue Table", byproductTable(selected))}
          ${card("Seed Production Analysis", seedTable())}
        </div>`;
      document.getElementById("finance-crop-select").addEventListener("change", (event) => {
        selectedCropId = event.target.value;
        cropAnalysisReady = true;
        renderFinance();
        requestAnimationFrame(drawCharts);
      });
    }

    function renderCrisis() {
      const crisis = state.crisis_management;
      document.getElementById("crisis").innerHTML = `
        <div class="grid two">
          ${card("Incident Response", [
            fact("Active incident", crisis.active_incident),
            fact("Severity", crisis.severity),
            fact("Response status", crisis.response_status),
            fact("Gross payment", money(crisis.gross_payment_eur), "money"),
            fact("Weather trigger", crisis.weather_trigger),
            fact("Property value", money(crisis.property_value_eur), "money"),
            fact("Property destruction loss", money(crisis.property_destruction_loss_eur), "warn-text"),
            fact("Collective revenue loss", money(crisis.collective_revenue_loss_eur), "warn-text"),
          ].join(""))}
          ${card("Crisis Payment Graph", '<canvas id="crisis-chart"></canvas>')}
        </div>
        <div class="card" style="margin-top:14px">
          <h2>Incident Actions</h2>
          <div class="quick-actions"><button data-open="upload">Upload incident evidence</button><button class="blue">Request field inspection</button><button class="secondary">Export crisis file</button></div>
        </div>`;
      rebindDynamicButtons();
    }

    function renderAssistant() {
      const messages = document.getElementById("messages");
      messages.innerHTML = "";
      state.assistant.forEach((message) => addMessage(message.role, message.message));
    }

    function metric(label, value) {
      return `<div class="card metric"><strong>${value}</strong><span>${label}</span></div>`;
    }

    function miniMetric(label, value, note) {
      return `<div class="mini-metric"><strong>${value}</strong><span>${label}<br>${note}</span></div>`;
    }

    function selectedForecast() {
      const forecast = state.crop_forecast;
      const current = selectedCropId || document.getElementById("crop-select")?.value;
      return forecast.options.find((row) => row.id === current) || forecast.options.find((row) => row.id === forecast.declared_crop) || forecast.best_option;
    }

    function forecastResult(selected) {
      return `
        <div class="forecast-strip">
          ${miniMetric("Year yield", `${selected.forecast_yield_tonnes} t`, `${selected.forecast_yield_tonnes_per_ha} t/ha stored yield`)}
          ${miniMetric("Max yield", `${selected.max_yield_tonnes} t`, `${selected.max_yield_tonnes_per_ha} t/ha benchmark max`)}
          ${miniMetric("Gross income", money(selected.gross_income_eur), "product value")}
          ${miniMetric("Market cap", money(selected.market_cap_eur), "max yield at product rate")}
        </div>
        <div class="grid two">
          ${card("Techno-Economic Analysis", [
            fact("Selected crop", selected.label),
            fact("Category", selected.category),
            fact("Yield source", selected.yield_source),
            fact("Declared crop match", selected.declared_crop_match ? "yes" : "alternative scenario"),
            fact("Soil score", `${selected.soil_score}%`, "money"),
            fact("Market price", `${money(selected.market_price_eur_per_tonne)}/t`),
            fact("By-product value", money(selected.byproduct_income_eur), "money"),
          ].join(""))}
          ${card("Cost and Gross Product", [
            fact("Total costs", money(selected.total_cost_eur), "warn-text"),
            fact("Gross product income", money(selected.gross_income_eur), "money"),
            fact("Market cap", money(selected.market_cap_eur), "money"),
            fact("Subsidy amount", money(selected.subsidy_eur), "money"),
            fact("Gross with subsidy", money(selected.gross_with_subsidy_eur), "money"),
            fact("Net margin", money(selected.net_margin_eur), Number(selected.net_margin_eur) >= 0 ? "money" : "warn-text"),
          ].join(""))}
        </div>
        <div class="grid three" style="margin-top:14px">
          ${card("Yield Graph", '<canvas id="crop-yield-chart"></canvas>')}
          ${card("Income Graph", '<canvas id="crop-finance-chart"></canvas>')}
          ${card("Subsidy Comparison", '<canvas id="crop-subsidy-chart"></canvas>')}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Soil and Field Solution", [
            fact("Soil analysis", selected.soil_note),
            fact("Weather analysis", selected.weather_note, "warn-text"),
            fact("Recommended action", selected.solution, "money"),
          ].join(""))}
          ${card("Planning Solutions", state.crop_forecast.solutions.map((text) => `<div class="fact"><span>${text}</span><strong class="money">solution</strong></div>`).join(""))}
        </div>`;
    }

    function forecastWeather() {
      const weather = state.crop_forecast.weather_forecast;
      return `
        ${[
          fact("Station", weather.station),
          fact("Temperature", `${weather.current.temperature_c} C`),
          fact("Humidity", `${weather.current.humidity_percent}%`),
          fact("Wind", `${weather.current.wind_kph} kph`),
          fact("7-day rainfall", `${weather.current.rainfall_7d_mm} mm`),
          fact("Soil moisture", weather.current.soil_moisture, "warn-text"),
          fact("Risk", weather.current.risk, "warn-text"),
        ].join("")}
        <table style="margin-top:12px"><thead><tr><th>Day</th><th>Condition</th><th>Rain</th><th>Risk</th></tr></thead><tbody>${weather.forecast.map((row) => `<tr><td>${row.day}</td><td>${row.condition}</td><td>${row.rain_mm} mm</td><td><span class="tag ${row.risk === "high" ? "warn" : "blue"}">${row.risk}</span></td></tr>`).join("")}</tbody></table>`;
    }

    function industryAnalysis(selected) {
      return [
        fact("Stated yield choice", selected.label),
        fact("Forecast yield", `${selected.forecast_yield_tonnes} t (${selected.forecast_yield_tonnes_per_ha} t/ha)`, "money"),
        fact("Maximum yield benchmark", `${selected.max_yield_tonnes} t (${selected.max_yield_tonnes_per_ha} t/ha)`),
        fact("Primary product rate", `${money(selected.industry_rates.primary_product_rate_eur_per_tonne)}/t`),
        fact("Gross market cap", money(selected.market_cap_eur), "money"),
        fact("By-product value", money(selected.byproduct_income_eur), "money"),
        fact("Net margin", money(selected.net_margin_eur), Number(selected.net_margin_eur) >= 0 ? "money" : "warn-text"),
      ].join("");
    }

    function byproductTable(selected) {
      return `<table><thead><tr><th>By-product</th><th>Yield ratio</th><th>Rate</th><th>Estimated value</th></tr></thead><tbody>${selected.industry_rates.byproducts.map((row) => {
        const value = Number(selected.forecast_yield_tonnes) * Number(row.yield_ratio) * Number(row.market_price_eur_per_tonne);
        return `<tr><td>${row.name}</td><td>${Number(row.yield_ratio).toFixed(2)} t/t</td><td>${money(row.market_price_eur_per_tonne)}/t</td><td><span class="money">${money(value)}</span></td></tr>`;
      }).join("")}</tbody></table>`;
    }

    function cropForecastTable() {
      return `<table><thead><tr><th>Crop</th><th>Yield</th><th>Gross</th><th>Subsidy</th><th>Margin</th></tr></thead><tbody>${state.crop_forecast.options.map((row) => `<tr><td>${row.label}<br><span class="muted">${row.category}</span></td><td>${row.forecast_yield_tonnes} t</td><td>${money(row.gross_income_eur)}</td><td>${money(row.subsidy_eur)}</td><td><span class="${Number(row.net_margin_eur) >= 0 ? "money" : "warn-text"}">${money(row.net_margin_eur)}</span></td></tr>`).join("")}</tbody></table>`;
    }

    function servicesTable() {
      return `<table><thead><tr><th>Service</th><th>Status</th><th>Records</th></tr></thead><tbody>${state.services.map((service) => `<tr><td>${service.name}</td><td><span class="status">${service.status}</span></td><td>${service.records}</td></tr>`).join("")}</tbody></table>`;
    }

    function requirementsTable() {
      return `<table><thead><tr><th>Required record</th><th>Status</th></tr></thead><tbody>${state.document_requirements.map((row) => `<tr><td>${row.label}</td><td><span class="tag ${row.status === "needed" ? "warn" : ""}">${row.status}</span></td></tr>`).join("")}</tbody></table>`;
    }

    function documentsTable() {
      if (!state.documents.length) return '<p class="muted">No farmer uploads yet. Use Upload to submit identity, land, finance, bank, or crisis evidence.</p>';
      return `<table><thead><tr><th>File</th><th>Type</th><th>Status</th></tr></thead><tbody>${state.documents.map((doc) => `<tr><td>${doc.file_name}</td><td>${doc.document_type}</td><td><span class="status">${doc.status}</span></td></tr>`).join("")}</tbody></table>`;
    }

    function documentAnalysis() {
      if (!state.documents.length) return '<p class="muted">Financial and audit document analysis will populate after upload.</p>';
      return state.documents.map((doc) => `<div class="fact"><span>${doc.file_name}</span><strong>${doc.analysis.risk} risk</strong></div>`).join("");
    }

    function seedTable() {
      const rows = state.seed_analysis.records;
      if (!rows.length) return '<p class="muted">No declared seed-production records yet.</p>';
      return `
        ${[
          fact("Collective sample farms", state.seed_analysis.summary.sample_farms),
          fact("Operating cost", money(state.seed_analysis.summary.total_operating_cost_eur), "warn-text"),
          fact("Gross seed-linked revenue", money(state.seed_analysis.summary.total_gross_revenue_eur), "money"),
          fact("Net margin", money(state.seed_analysis.summary.total_net_margin_eur), "money"),
          fact("Average ROI", `${Number(state.seed_analysis.summary.average_roi_percent).toFixed(1)}%`, "money"),
        ].join("")}
        <table style="margin-top:12px"><thead><tr><th>Parcel</th><th>Variety</th><th>Expected</th><th>Margin</th><th>Status</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${row.cadastral_reference}</td><td>${row.seed_variety}<br><span class="muted">${row.seed_lot}</span></td><td>${row.expected_production_tonnes} t</td><td>${money(row.net_margin_eur)}</td><td><span class="tag ${row.status === "review" ? "warn" : ""}">${row.status}</span></td></tr>`).join("")}</tbody></table>
        <h3 style="margin-top:14px">Collective Benchmark Database</h3>
        <table><thead><tr><th>Crop</th><th>Region</th><th>Seed rate</th><th>Yield</th><th>Price</th></tr></thead><tbody>${state.seed_analysis.collective_database.map((row) => `<tr><td>${row.production_type}</td><td>${row.sample_region}<br><span class="muted">${row.sample_farms} farms</span></td><td>${row.seed_rate_tonnes_per_ha} t/ha</td><td>${row.expected_yield_tonnes_per_ha} t/ha</td><td>${money(row.market_price_eur_per_tonne)}/t</td></tr>`).join("")}</tbody></table>
        <h3 style="margin-top:14px">Techno-economic Recommendations</h3>
        ${state.seed_analysis.recommendations.map((text) => `<div class="fact"><span>${text}</span><strong class="money">active</strong></div>`).join("")}
      `;
    }

    function sourcesList(sources) {
      return `<div style="margin-top:12px">${sources.map((source) => `<div class="fact"><span>${source.name}</span><strong class="money">${source.status}</strong></div>`).join("")}</div>`;
    }

    function addMessage(role, message) {
      const row = document.createElement("div");
      row.className = `message ${role === "user" ? "user" : ""}`;
      row.textContent = message;
      document.getElementById("messages").appendChild(row);
      row.scrollIntoView({block: "end"});
    }

    function assistantReply(text) {
      const q = text.toLowerCase();
      if (q.includes("land") || q.includes("map")) return "Open Land Declaration, then choose Google Maps draw for a new boundary or Google Earth KML for an existing parcel file. The eligible hectares update before payment calculation.";
      if (q.includes("document") || q.includes("upload")) return "Open Upload, choose the document type, and submit the file. I will mark the record as submitted and refresh audit and financial coverage.";
      if (q.includes("payment") || q.includes("subsidy")) return `Your current disbursable subsidy is ${money(state.subsidy_claim.debt_offset.disbursable_eur)} before any new holds. Crisis gross payment is ${money(state.crisis_management.gross_payment_eur)}.`;
      if (q.includes("crisis") || q.includes("incident")) return "Use Crisis Management to upload incident evidence, request inspection, and compare gross compensation scenarios by damage condition.";
      if (q.includes("weather")) return `Current field risk is ${state.weather_conditions.current.risk}, with ${state.weather_conditions.current.rainfall_7d_mm} mm rainfall in the last 7 days.`;
      if (q.includes("yield") || q.includes("crop forecast")) return `Open Crop Forecast to compare 20 crop yields. The current best net margin is ${state.crop_forecast.best_option.label} at ${money(state.crop_forecast.best_option.net_margin_eur)}.`;
      if (q.includes("seed")) return "Seed analysis compares declared seed use, expected production, declared tonnes, verified tonnes, and variance for each owned land parcel.";
      if (q.includes("deduction") || q.includes("sold")) return `First sold units currently net ${money(state.financial_analysis.first_sale_deductions.net_product_after_deductions_eur)} after tax and market-fee deductions.`;
      if (q.includes("finance") || q.includes("tax")) return "Financial analysis reconciles first-sale revenue, tax exposure, debt offset, subsidy, compensation, and uploaded invoice records.";
      return "I can help with land declaration, document upload, audit findings, financial analysis, crisis response, and payment due forecasts.";
    }

    function drawCharts() {
      if (!state) return;
      drawBars("payment-chart", state.financial_analysis.payment_scenarios.map((x) => ({label: x.label, value: Number(x.net)})), ["#2d7650", "#286f9e", "#a6473b"]);
      drawBars("finance-chart", state.financial_analysis.series.map((x) => ({label: x.label, value: Number(x.value)})), ["#286f9e", "#ad7a25", "#2d7650", "#6656a6", "#a6473b"]);
      drawBars("crisis-chart", state.crisis_management.scenarios.map((x) => ({label: x.label, value: Number(x.value)})), ["#ad7a25", "#2d7650", "#286f9e", "#a6473b"]);
      drawBars("forecast-weather-chart", state.crop_forecast.weather_forecast.forecast.map((x) => ({label: x.day, value: Number(x.rain_mm)})), ["#286f9e", "#2d7650", "#ad7a25", "#6656a6"]);
      drawBars("market-cap-chart", state.crop_forecast.options.slice(0, 10).map((row) => ({label: row.label, value: Number(row.market_cap_eur)})), ["#286f9e", "#2d7650", "#ad7a25", "#6656a6"]);
      const selected = selectedForecast();
      drawBars("crop-yield-chart", [
        {label: "Forecast", value: Number(selected.forecast_yield_tonnes)},
        {label: "Max", value: Number(selected.max_yield_tonnes)},
      ], ["#286f9e", "#2d7650"]);
      drawBars("crop-finance-chart", [
        {label: "Costs", value: Number(selected.total_cost_eur)},
        {label: "Income", value: Number(selected.gross_income_eur)},
        {label: "Subsidy", value: Number(selected.subsidy_eur)},
        {label: "Margin", value: Math.max(Number(selected.net_margin_eur), 0)},
      ], ["#ad7a25", "#286f9e", "#2d7650", "#6656a6"]);
      drawBars("crop-subsidy-chart", state.crop_forecast.options.slice(0, 10).map((row) => ({label: row.label, value: Number(row.subsidy_eur)})), ["#2d7650", "#286f9e", "#ad7a25", "#6656a6"]);
      drawBars("finance-yield-chart", [
        {label: "Product", value: Number(selected.gross_income_eur)},
        {label: "By-products", value: Number(selected.byproduct_income_eur)},
        {label: "Subsidy", value: Number(selected.subsidy_eur)},
      ], ["#286f9e", "#ad7a25", "#2d7650"]);
      drawBars("industry-rates-chart", [
        {label: "Product", value: Number(selected.market_price_eur_per_tonne)},
        ...selected.industry_rates.byproducts.map((row) => ({label: row.name, value: Number(row.market_price_eur_per_tonne)})),
      ], ["#286f9e", "#ad7a25", "#2d7650", "#6656a6"]);
      drawBars("finance-market-chart", [
        {label: "Market cap", value: Number(selected.market_cap_eur)},
        {label: "Gross", value: Number(selected.gross_income_eur)},
        {label: "Net margin", value: Math.max(Number(selected.net_margin_eur), 0)},
      ], ["#6656a6", "#286f9e", "#2d7650"]);
      drawGauge("audit-chart", state.audit_analysis.score);
    }

    function drawBars(id, rows, colors) {
      const canvas = document.getElementById(id);
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(320, rect.width * devicePixelRatio);
      canvas.height = 210 * devicePixelRatio;
      const ctx = canvas.getContext("2d");
      ctx.scale(devicePixelRatio, devicePixelRatio);
      ctx.clearRect(0, 0, rect.width, 210);
      const max = Math.max(...rows.map((row) => row.value), 1);
      const gap = 12;
      const barWidth = Math.max(24, (rect.width - 46 - gap * rows.length) / rows.length);
      rows.forEach((row, index) => {
        const height = (row.value / max) * 132;
        const x = 28 + index * (barWidth + gap);
        const y = 158 - height;
        ctx.fillStyle = colors[index % colors.length];
        ctx.fillRect(x, y, barWidth, height);
        ctx.fillStyle = "#18221d";
        ctx.font = "12px Arial";
        ctx.fillText(row.label.slice(0, 13), x, 184);
      });
    }

    function drawGauge(id, score) {
      const canvas = document.getElementById(id);
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(320, rect.width * devicePixelRatio);
      canvas.height = 210 * devicePixelRatio;
      const ctx = canvas.getContext("2d");
      ctx.scale(devicePixelRatio, devicePixelRatio);
      const cx = rect.width / 2;
      ctx.clearRect(0, 0, rect.width, 210);
      ctx.lineWidth = 18;
      ctx.strokeStyle = "#d7dfdb";
      ctx.beginPath();
      ctx.arc(cx, 116, 72, Math.PI, 0);
      ctx.stroke();
      ctx.strokeStyle = score > 80 ? "#2d7650" : "#ad7a25";
      ctx.beginPath();
      ctx.arc(cx, 116, 72, Math.PI, Math.PI + Math.PI * (score / 100));
      ctx.stroke();
      ctx.fillStyle = "#18221d";
      ctx.font = "700 30px Arial";
      ctx.textAlign = "center";
      ctx.fillText(`${score}%`, cx, 122);
      ctx.font = "13px Arial";
      ctx.fillText("audit confidence", cx, 146);
      ctx.textAlign = "left";
    }

    function rebindDynamicButtons() {
      document.querySelectorAll("[data-open]").forEach((button) => {
        button.onclick = () => document.getElementById(`${button.dataset.open}-modal`).classList.add("open");
      });
      document.querySelectorAll("[data-section-jump]").forEach((button) => {
        button.onclick = () => showSection(button.dataset.sectionJump);
      });
    }
  </script>
</body>
</html>
"""
