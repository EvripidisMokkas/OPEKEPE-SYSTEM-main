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
            ("POST", "/applicant-screening"): self.screen_applicant,
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

    def screen_applicant(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        return 200, {"screening": _screen_applicant(payload)}

    def submit_document(self, query: dict[str, list[str]], payload: dict[str, Any]) -> HandlerResult:
        document_type = str(payload["document_type"])
        file_name = str(payload["file_name"])
        file_size = int(payload.get("file_size", 0))
        analysis = _document_analysis(
            document_type,
            file_name,
            file_size,
            enhanced_audit=bool(payload.get("enhanced_audit", False)),
        )
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
            {"name": "Ταυτότητα δικαιούχου", "status": "αρχικοποιημένη", "records": len(farmers)},
            {"name": "Μητρώο αγροτεμαχίων", "status": "αρχικοποιημένη", "records": len(parcels)},
            {"name": "Δηλώσεις παραγωγής", "status": "αρχικοποιημένη", "records": len(crop_seasons)},
            {"name": "Τεκμήρια τηλεπισκόπησης", "status": "αρχικοποιημένη", "records": len(observations)},
            {"name": "Συμφωνία φόρου πρώτης πώλησης", "status": "αρχικοποιημένη", "records": len(first_sales)},
            {"name": "Διαχείριση συμψηφισμού οφειλών", "status": "αρχικοποιημένη", "records": len(debts)},
            {"name": "Υποδοχή και έλεγχος δικαιολογητικών", "status": "αρχικοποιημένη", "records": len(documents)},
            {"name": "Υπολογισμός ενίσχυσης ΚΑΠ", "status": "αρχικοποιημένη", "records": len(subsidy_claim.line_items)},
            {"name": "Πρόβλεψη καιρού καλλιέργειας", "status": "αρχικοποιημένη", "records": 20},
            {"name": "Αποζημίωση κρίσης", "status": "αρχικοποιημένη", "records": len(crisis_events)},
            {"name": "Καθοδήγηση βοηθού", "status": "αρχικοποιημένη", "records": 4},
            {"name": "Ιστορικό ελέγχου", "status": "αρχικοποιημένη", "records": len(service.repository.audit_events())},
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


def _screen_applicant(payload: dict[str, Any]) -> dict[str, Any]:
    first_name = str(payload["first_name"]).strip()
    surname = str(payload["surname"]).strip()
    occupation = str(payload["occupation"]).strip()
    declared_exposure = str(payload.get("public_integrity_exposure", "no")).strip().lower() == "yes"
    normalized_name = f"{first_name} {surname}".casefold()
    local_disclosure_database = {
        "demo olive farmer": "demo public-integrity disclosure list",
        "alexis papadopoulos": "public office declaration list",
        "maria georgiou": "procurement conflict register",
    }
    database_source = local_disclosure_database.get(normalized_name)
    enhanced_audit = declared_exposure or database_source is not None
    status = "enhanced_audit" if enhanced_audit else "off_the_hook"
    reasons = []
    if declared_exposure:
        reasons.append("applicant_declared_public_integrity_exposure")
    if database_source is not None:
        reasons.append("name_surname_matched_public_integrity_database")
    if not reasons:
        reasons.append("no_declared_exposure_or_database_match")
    return {
        "applicant_name": f"{first_name} {surname}",
        "occupation": occupation,
        "status": status,
        "enhanced_audit": enhanced_audit,
        "database_checked": True,
        "database_source": database_source or "no match",
        "reasons": reasons,
        "document_audit_mode": "close_audit" if enhanced_audit else "standard_audit",
        "note": (
            "Ο ενισχυμένος έλεγχος βασίζεται σε δηλωμένη έκθεση δημόσιου αξιώματος/σύγκρουσης "
            "ή σε ουδέτερη αντιστοίχιση βάσης δεδομένων, όχι σε πολιτική άποψη ή κομματική προτίμηση."
        ),
    }


def _document_analysis(
    document_type: str,
    file_name: str,
    file_size: int,
    *,
    enhanced_audit: bool,
) -> dict[str, Any]:
    checks = {
        "identity": ["tax_identifier_detected", "name_match_pending"],
        "land": ["parcel_reference_detected", "geometry_review_required"],
        "finance": ["invoice_totals_read", "tax_reconciliation_pending"],
        "bank": ["iban_format_check", "beneficiary_match_pending"],
        "crisis": ["incident_date_detected", "evidence_review_required"],
    }
    normalized_type = document_type if document_type in checks else "general"
    selected_checks = checks.get(normalized_type, ["manual_review_required"])
    if enhanced_audit:
        selected_checks = selected_checks + ["enhanced_audit_queue", "cross_document_consistency_review"]
    return {
        "summary": f"Το {file_name} μπήκε σε ουρά ελέγχου για {document_type}",
        "file_size": file_size,
        "confidence": "0.82" if file_size else "0.58",
        "checks": selected_checks,
        "risk": "high" if enhanced_audit else "medium" if normalized_type in {"finance", "crisis"} else "low",
        "audit_mode": "close_audit" if enhanced_audit else "standard_audit",
    }


def _document_requirements(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    submitted = {document["document_type"] for document in documents}
    required = [
        ("identity", "Ταυτότητα και φορολογικό πιστοποιητικό"),
        ("land", "Τίτλος γης, μίσθωση ή κτηματολογικό απόσπασμα"),
        ("finance", "Τιμολόγια, εγγραφές myDATA και τραπεζική κίνηση"),
        ("bank", "Απόδειξη IBAN για πληρωμή"),
        ("crisis", "Φωτογραφίες συμβάντος ή δήλωση αρχής"),
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
        "document_coverage": "πλήρης" if finance_docs else "λείπουν οικονομικά δικαιολογητικά",
        "first_sale_deductions": {
            "sold_quantity_tonnes": str(sold_quantity),
            "gross_product_value_eur": str(gross_product_value),
            "first_sale_tax_eur": str(first_sale_tax),
            "market_fee_eur": str(market_fee),
            "net_product_after_deductions_eur": str(net_product_after_deductions),
        },
        "series": [
            {"label": "Έσοδα πωλήσεων", "value": str(annual_ledger.first_sale_revenue_eur)},
            {"label": "Οφειλόμενος φόρος", "value": str(annual_ledger.first_sale_tax_eur)},
            {"label": "Ενίσχυση", "value": str(subsidy_claim.final_amount_eur)},
            {"label": "Αποζημίωση", "value": str(compensation_amount)},
            {"label": "Οφειλή", "value": str(annual_ledger.open_debt_eur)},
        ],
        "payment_scenarios": [
            {"label": "Κανονική εκκαθάριση", "gross": str(subsidy_claim.final_amount_eur), "net": str(subsidy_claim.debt_offset.disbursable_eur)},
            {"label": "Έγκριση κρίσης", "gross": str(gross_public_support), "net": str(net_after_obligations + compensation_amount)},
            {"label": "Δέσμευση δικαιολογητικών", "gross": str(gross_public_support), "net": "0.00"},
        ],
    }


def _weather_conditions() -> dict[str, Any]:
    return {
        "station": "Πλέγμα demo καιρού Αττικής",
        "current": {
            "temperature_c": "31",
            "humidity_percent": "42",
            "wind_kph": "18",
            "rainfall_7d_mm": "4",
            "soil_moisture": "low",
            "risk": "drought watch",
        },
        "forecast": [
            {"day": "Σήμερα", "condition": "ζέστη", "rain_mm": "0", "risk": "μέτριος"},
            {"day": "Αύριο", "condition": "άνεμος", "rain_mm": "0", "risk": "μέτριος"},
            {"day": "Ημέρα 3", "condition": "ξηρασία", "rain_mm": "1", "risk": "υψηλός"},
            {"day": "Ημέρα 4", "condition": "νεφώσεις", "rain_mm": "3", "risk": "χαμηλός"},
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
        "service_name": "Πρόβλεψη Αποδόσεων και Τεχνοοικονομική Ανάλυση",
        "declared_area_ha": str(declared_area),
        "declared_crop": declared_crop,
        "forecast_source": "βάση αποθηκευμένων αποδόσεων",
        "weather_forecast": weather_forecast,
        "soil_profile": soil_profile,
        "options": options,
        "best_option": best,
        "solutions": [
            "Χρησιμοποιήστε ανθεκτικές στην ξηρασία ποικιλίες ή καθυστερήστε τη φύτευση όταν η βαθμολογία καιρού πέφτει κάτω από 75%.",
            "Δώστε προτεραιότητα σε καλλιέργειες με υψηλό καθαρό περιθώριο μετά την ενίσχυση, όχι μόνο σε υψηλό ακαθάριστο εισόδημα.",
            "Προσθέστε οργανική ουσία και μέτρα συγκράτησης υγρασίας για θερινές καλλιέργειες σε αργιλοπηλώδη εδάφη.",
            "Συνδέστε τα τιμολόγια πρώτης πώλησης με την επιλεγμένη καλλιέργεια ώστε να συμφωνείται το εισόδημα με τις ενισχύσεις.",
        ],
    }


def _crop_forecast_catalog() -> list[dict[str, Any]]:
    return [
        {"id": "olives", "label": "Ελιές", "category": "πολυετής", "base_yield_tonnes_per_ha": "4.5", "max_factor": "1.18", "market_price_eur_per_tonne": "4300", "input_cost_eur_per_ha": "360", "field_operations_eur_per_ha": "540", "irrigation_eur_per_ha": "210", "crop_protection_eur_per_ha": "185", "subsidy_eur_per_ha": "560", "water_need_mm": "420", "soil_factor": "0.94", "soil_note": "Το αργιλοπηλώδες έδαφος υποστηρίζει τις ελιές όταν διατηρείται η αποστράγγιση.", "weather_note": "Η επιτήρηση ξηρασίας μειώνει την καρπόδεση χωρίς άρδευση.", "solution": "Χρησιμοποιήστε ελλειμματική άρδευση, κλάδεμα και παρακολούθηση δάκου πριν από τις θερμικές αιχμές."},
        {"id": "durum_wheat", "label": "Σκληρό σιτάρι", "category": "σιτηρό", "base_yield_tonnes_per_ha": "5.8", "max_factor": "1.12", "market_price_eur_per_tonne": "315", "input_cost_eur_per_ha": "155", "field_operations_eur_per_ha": "410", "irrigation_eur_per_ha": "165", "crop_protection_eur_per_ha": "120", "subsidy_eur_per_ha": "390", "water_need_mm": "360", "soil_factor": "0.91", "soil_note": "Καλή προσαρμογή σε ουδέτερο pH και μέτρια υδατοϊκανότητα.", "weather_note": "Η χαμηλή βροχόπτωση επηρεάζει το γέμισμα του κόκκου.", "solution": "Μετακινήστε την ημερομηνία σποράς και κρατήστε τη λίπανση αζώτου κοντά στα γεγονότα βροχής."},
        {"id": "barley", "label": "Κριθάρι", "category": "σιτηρό", "base_yield_tonnes_per_ha": "5.2", "max_factor": "1.10", "market_price_eur_per_tonne": "260", "input_cost_eur_per_ha": "130", "field_operations_eur_per_ha": "360", "irrigation_eur_per_ha": "120", "crop_protection_eur_per_ha": "95", "subsidy_eur_per_ha": "350", "water_need_mm": "310", "soil_factor": "0.90", "soil_note": "Αντέχει ελαφρύτερο στρες υγρασίας από το σιτάρι.", "weather_note": "Η πρόβλεψη ευνοεί το κριθάρι έναντι πιο υδροβόρων σιτηρών.", "solution": "Χρησιμοποιήστε πιστοποιημένο σπόρο και πρώιμη ζιζανιοκτονία για προστασία του αδελφώματος."},
        {"id": "corn", "label": "Καλαμπόκι", "category": "αρδευόμενο", "base_yield_tonnes_per_ha": "11.5", "max_factor": "1.20", "market_price_eur_per_tonne": "245", "input_cost_eur_per_ha": "410", "field_operations_eur_per_ha": "620", "irrigation_eur_per_ha": "520", "crop_protection_eur_per_ha": "210", "subsidy_eur_per_ha": "420", "water_need_mm": "620", "soil_factor": "0.86", "soil_note": "Χρειάζεται ισχυρή διαχείριση υγρασίας σε μέτρια-χαμηλή υδατοϊκανότητα.", "weather_note": "Η τρέχουσα επιτήρηση ξηρασίας περιορίζει έντονα τη ξηρική απόδοση.", "solution": "Φυτέψτε μόνο με εξασφαλισμένο πρόγραμμα άρδευσης και παρακολούθηση εξατμισοδιαπνοής."},
        {"id": "cotton", "label": "Βαμβάκι", "category": "βιομηχανική", "base_yield_tonnes_per_ha": "3.6", "max_factor": "1.16", "market_price_eur_per_tonne": "760", "input_cost_eur_per_ha": "390", "field_operations_eur_per_ha": "610", "irrigation_eur_per_ha": "430", "crop_protection_eur_per_ha": "260", "subsidy_eur_per_ha": "740", "water_need_mm": "560", "soil_factor": "0.88", "soil_note": "Μέτρια καταλληλότητα· η συμπίεση πρέπει να αποφεύγεται.", "weather_note": "Η ζέστη βοηθά το βαμβάκι αλλά το υδατικό στρες μειώνει τη συγκράτηση καρυδιών.", "solution": "Χρησιμοποιήστε προγραμματισμό στάγδην άρδευσης και επιτήρηση εχθρών πριν την άνθηση."},
        {"id": "tomatoes", "label": "Βιομηχανική ντομάτα", "category": "κηπευτικό", "base_yield_tonnes_per_ha": "78", "max_factor": "1.14", "market_price_eur_per_tonne": "115", "input_cost_eur_per_ha": "1250", "field_operations_eur_per_ha": "1450", "irrigation_eur_per_ha": "780", "crop_protection_eur_per_ha": "560", "subsidy_eur_per_ha": "520", "water_need_mm": "590", "soil_factor": "0.89", "soil_note": "Καλό pH, αλλά η αποστράγγιση και το ασβέστιο είναι κρίσιμα.", "weather_note": "Οι θερμές ξηρές ημέρες αυξάνουν το στρες στην καρπόδεση.", "solution": "Χρησιμοποιήστε στάγδην υδρολίπανση, εδαφοκάλυψη και παρακολούθηση ασβεστίου."},
        {"id": "potatoes", "label": "Πατάτες", "category": "κηπευτικό", "base_yield_tonnes_per_ha": "34", "max_factor": "1.13", "market_price_eur_per_tonne": "410", "input_cost_eur_per_ha": "980", "field_operations_eur_per_ha": "1380", "irrigation_eur_per_ha": "650", "crop_protection_eur_per_ha": "480", "subsidy_eur_per_ha": "450", "water_need_mm": "520", "soil_factor": "0.82", "soil_note": "Το αργιλοπηλώδες έδαφος μπορεί να μειώσει το σχήμα κονδύλων χωρίς καλή προετοιμασία.", "weather_note": "Η ζέστη και η χαμηλή υγρασία μειώνουν την ανάπτυξη κονδύλων.", "solution": "Βελτιώστε τις γραμμές, προγραμματίστε άρδευση και παρακολουθήστε τον περονόσπορο."},
        {"id": "grapes", "label": "Οινοστάφυλα", "category": "πολυετής", "base_yield_tonnes_per_ha": "9.0", "max_factor": "1.11", "market_price_eur_per_tonne": "820", "input_cost_eur_per_ha": "520", "field_operations_eur_per_ha": "860", "irrigation_eur_per_ha": "260", "crop_protection_eur_per_ha": "340", "subsidy_eur_per_ha": "480", "water_need_mm": "390", "soil_factor": "0.92", "soil_note": "Ουδέτερο pH και μέτρια αποστράγγιση υποστηρίζουν ποιοτικά σταφύλια.", "weather_note": "Ο ξηρός καιρός μειώνει την πίεση ασθενειών αλλά μπορεί να μειώσει το μέγεθος ραγών.", "solution": "Χρησιμοποιήστε διαχείριση κόμης και στοχευμένη άρδευση στον περκασμό."},
        {"id": "almonds", "label": "Αμύγδαλα", "category": "πολυετής", "base_yield_tonnes_per_ha": "2.4", "max_factor": "1.18", "market_price_eur_per_tonne": "3900", "input_cost_eur_per_ha": "620", "field_operations_eur_per_ha": "760", "irrigation_eur_per_ha": "420", "crop_protection_eur_per_ha": "310", "subsidy_eur_per_ha": "530", "water_need_mm": "520", "soil_factor": "0.87", "soil_note": "Χρειάζεται αποστράγγιση και παρακολούθηση αλατότητας.", "weather_note": "Το υδατικό στρες μειώνει το γέμισμα της ψίχας.", "solution": "Χρησιμοποιήστε ρυθμιζόμενη ελλειμματική άρδευση και σχεδιασμό επικονίασης."},
        {"id": "pistachios", "label": "Φιστίκια", "category": "πολυετής", "base_yield_tonnes_per_ha": "1.9", "max_factor": "1.20", "market_price_eur_per_tonne": "6200", "input_cost_eur_per_ha": "690", "field_operations_eur_per_ha": "820", "irrigation_eur_per_ha": "390", "crop_protection_eur_per_ha": "360", "subsidy_eur_per_ha": "540", "water_need_mm": "470", "soil_factor": "0.86", "soil_note": "Μέτρια καταλληλότητα με προσεκτική αποστράγγιση.", "weather_note": "Η ξηρή ζέστη είναι αποδεκτή αν η άρδευση είναι αξιόπιστη.", "solution": "Προστατέψτε την παρενιαυτοφορία με ισορροπημένο κλάδεμα και άρδευση."},
        {"id": "chickpeas", "label": "Ρεβίθια", "category": "ψυχανθές", "base_yield_tonnes_per_ha": "2.2", "max_factor": "1.10", "market_price_eur_per_tonne": "780", "input_cost_eur_per_ha": "150", "field_operations_eur_per_ha": "330", "irrigation_eur_per_ha": "80", "crop_protection_eur_per_ha": "100", "subsidy_eur_per_ha": "410", "water_need_mm": "260", "soil_factor": "0.90", "soil_note": "Καλή επιλογή χαμηλών εισροών για ουδέτερο έδαφος.", "weather_note": "Η επιτήρηση ξηρασίας είναι λιγότερο επιζήμια από ό,τι σε αρδευόμενες καλλιέργειες.", "solution": "Χρησιμοποιήστε εμβολιασμένο σπόρο και αποφύγετε υπερβολική άρδευση στην άνθηση."},
        {"id": "lentils", "label": "Φακές", "category": "ψυχανθές", "base_yield_tonnes_per_ha": "1.8", "max_factor": "1.09", "market_price_eur_per_tonne": "950", "input_cost_eur_per_ha": "135", "field_operations_eur_per_ha": "310", "irrigation_eur_per_ha": "70", "crop_protection_eur_per_ha": "90", "subsidy_eur_per_ha": "405", "water_need_mm": "240", "soil_factor": "0.88", "soil_note": "Λειτουργεί όπου η αποστράγγιση αποφεύγει την υπεράρδευση.", "weather_note": "Οι ξηρές συνθήκες είναι διαχειρίσιμες αν προστατευτεί το φύτρωμα.", "solution": "Χρησιμοποιήστε καθαρό σπόρο και πρώιμη συγκομιδή για περιορισμό τινάγματος."},
        {"id": "beans", "label": "Ξηρά φασόλια", "category": "ψυχανθές", "base_yield_tonnes_per_ha": "3.0", "max_factor": "1.12", "market_price_eur_per_tonne": "1050", "input_cost_eur_per_ha": "220", "field_operations_eur_per_ha": "420", "irrigation_eur_per_ha": "310", "crop_protection_eur_per_ha": "150", "subsidy_eur_per_ha": "430", "water_need_mm": "430", "soil_factor": "0.84", "soil_note": "Χρειάζεται καλύτερη υδατοϊκανότητα από αυτή που δείχνει σήμερα το δηλωμένο αγροτεμάχιο.", "weather_note": "Η χαμηλή υγρασία αυξάνει τον κίνδυνο αποβολής ανθέων.", "solution": "Επιλέξτε μόνο με άρδευση και αποφύγετε ζέστη στην άνθηση."},
        {"id": "sunflower", "label": "Ηλίανθος", "category": "ελαιούχος", "base_yield_tonnes_per_ha": "3.1", "max_factor": "1.13", "market_price_eur_per_tonne": "470", "input_cost_eur_per_ha": "210", "field_operations_eur_per_ha": "390", "irrigation_eur_per_ha": "150", "crop_protection_eur_per_ha": "130", "subsidy_eur_per_ha": "360", "water_need_mm": "340", "soil_factor": "0.89", "soil_note": "Η βαθιά ρίζα ταιριάζει καλύτερα σε μέτρια-χαμηλή υγρασία από το καλαμπόκι.", "weather_note": "Η πρόβλεψη υποστηρίζει τον ηλίανθο αν πετύχει η εγκατάσταση.", "solution": "Χρησιμοποιήστε συντηρητική κατεργασία και παρακολουθήστε οροβάγχη."},
        {"id": "rapeseed", "label": "Ελαιοκράμβη", "category": "ελαιούχος", "base_yield_tonnes_per_ha": "3.3", "max_factor": "1.10", "market_price_eur_per_tonne": "510", "input_cost_eur_per_ha": "250", "field_operations_eur_per_ha": "420", "irrigation_eur_per_ha": "130", "crop_protection_eur_per_ha": "170", "subsidy_eur_per_ha": "365", "water_need_mm": "380", "soil_factor": "0.86", "soil_note": "Μέτρια καταλληλότητα· αποφύγετε τη συμπίεση.", "weather_note": "Χρειάζεται βροχή κατά την φθινοπωρινή εγκατάσταση.", "solution": "Σχεδιάστε σπορά μετά από βροχόπτωση και χρησιμοποιήστε εδαφοκάλυψη για διατήρηση υγρασίας."},
        {"id": "alfalfa", "label": "Μηδική", "category": "κτηνοτροφικό", "base_yield_tonnes_per_ha": "14.0", "max_factor": "1.15", "market_price_eur_per_tonne": "215", "input_cost_eur_per_ha": "240", "field_operations_eur_per_ha": "520", "irrigation_eur_per_ha": "430", "crop_protection_eur_per_ha": "110", "subsidy_eur_per_ha": "380", "water_need_mm": "650", "soil_factor": "0.85", "soil_note": "Χρειάζεται αξιόπιστο νερό για πολλαπλές κοπές.", "weather_note": "Η επιτήρηση ξηρασίας μειώνει τις επόμενες κοπές.", "solution": "Χρησιμοποιήστε προϋπολογισμό άρδευσης και χρονισμό κοπών με βάση την εξατμισοδιαπνοή."},
        {"id": "oranges", "label": "Πορτοκάλια", "category": "πολυετής", "base_yield_tonnes_per_ha": "32", "max_factor": "1.12", "market_price_eur_per_tonne": "430", "input_cost_eur_per_ha": "760", "field_operations_eur_per_ha": "920", "irrigation_eur_per_ha": "520", "crop_protection_eur_per_ha": "390", "subsidy_eur_per_ha": "500", "water_need_mm": "700", "soil_factor": "0.83", "soil_note": "Χρειάζεται υψηλότερη υδατοϊκανότητα και έλεγχο αλατότητας.", "weather_note": "Το τρέχον ξηρό μοτίβο αυξάνει τον κίνδυνο καρπόπτωσης.", "solution": "Χρησιμοποιήστε εδαφοκάλυψη, ελέγχους αλατότητας και σταθερή άρδευση."},
        {"id": "apples", "label": "Μήλα", "category": "πολυετής", "base_yield_tonnes_per_ha": "38", "max_factor": "1.12", "market_price_eur_per_tonne": "620", "input_cost_eur_per_ha": "900", "field_operations_eur_per_ha": "1180", "irrigation_eur_per_ha": "560", "crop_protection_eur_per_ha": "620", "subsidy_eur_per_ha": "510", "water_need_mm": "610", "soil_factor": "0.80", "soil_note": "Το δηλωμένο αγροτεμάχιο δεν είναι ιδανικό για μήλα υψηλής ποιότητας.", "weather_note": "Το θερμικό στρες μπορεί να μειώσει χρώμα και μέγεθος.", "solution": "Χρησιμοποιήστε δίχτυα σκίασης και άρδευση ακριβείας αν φυτευτεί."},
        {"id": "kiwi", "label": "Ακτινίδια", "category": "πολυετής", "base_yield_tonnes_per_ha": "30", "max_factor": "1.13", "market_price_eur_per_tonne": "850", "input_cost_eur_per_ha": "1050", "field_operations_eur_per_ha": "1280", "irrigation_eur_per_ha": "720", "crop_protection_eur_per_ha": "520", "subsidy_eur_per_ha": "520", "water_need_mm": "760", "soil_factor": "0.78", "soil_note": "Απαιτεί καλύτερη υγρασία και ανεμοπροστασία από αυτή που δείχνει το demo αγροτεμάχιο.", "weather_note": "Ο ξηρός άνεμος δημιουργεί υψηλό στρες.", "solution": "Εγκαταστήστε ανεμοφράκτες, υδρολίπανση και αισθητήρες υγρασίας πριν την επένδυση."},
        {"id": "watermelon", "label": "Καρπούζι", "category": "κηπευτικό", "base_yield_tonnes_per_ha": "48", "max_factor": "1.16", "market_price_eur_per_tonne": "280", "input_cost_eur_per_ha": "620", "field_operations_eur_per_ha": "880", "irrigation_eur_per_ha": "520", "crop_protection_eur_per_ha": "330", "subsidy_eur_per_ha": "390", "water_need_mm": "500", "soil_factor": "0.84", "soil_note": "Οι αναχώματα και η αποστράγγιση είναι σημαντικά σε αργιλοπηλώδες έδαφος.", "weather_note": "Η ζέστη είναι χρήσιμη, αλλά το υδατικό στρες μειώνει το μέγεθος καρπού.", "solution": "Χρησιμοποιήστε εδαφοκάλυψη, στάγδην άρδευση και προβλέψεις σταδιακής συγκομιδής."},
    ]


def _industry_byproduct_rates(crop_id: str) -> list[dict[str, str]]:
    rates = {
        "olives": [
            {"name": "ελαιοπυρήνας", "yield_ratio": "0.35", "market_price_eur_per_tonne": "85"},
            {"name": "βιομάζα φύλλων ελιάς", "yield_ratio": "0.08", "market_price_eur_per_tonne": "55"},
        ],
        "durum_wheat": [
            {"name": "άχυρο", "yield_ratio": "0.80", "market_price_eur_per_tonne": "95"},
            {"name": "πίτυρο άλεσης", "yield_ratio": "0.12", "market_price_eur_per_tonne": "185"},
        ],
        "barley": [
            {"name": "άχυρο", "yield_ratio": "0.75", "market_price_eur_per_tonne": "90"},
            {"name": "διαλογές ζωοτροφής", "yield_ratio": "0.05", "market_price_eur_per_tonne": "150"},
        ],
        "corn": [
            {"name": "υπολείμματα καλαμποκιού", "yield_ratio": "0.90", "market_price_eur_per_tonne": "65"},
            {"name": "σπάδικες", "yield_ratio": "0.18", "market_price_eur_per_tonne": "70"},
        ],
        "cotton": [
            {"name": "βαμβακόσπορος", "yield_ratio": "0.55", "market_price_eur_per_tonne": "310"},
            {"name": "βιομάζα στελεχών", "yield_ratio": "0.70", "market_price_eur_per_tonne": "45"},
        ],
        "tomatoes": [
            {"name": "υπολείμματα ντομάτας", "yield_ratio": "0.06", "market_price_eur_per_tonne": "42"},
            {"name": "υλικό εκχυλίσματος σπόρου", "yield_ratio": "0.01", "market_price_eur_per_tonne": "260"},
        ],
        "potatoes": [
            {"name": "φλούδα επεξεργασίας", "yield_ratio": "0.08", "market_price_eur_per_tonne": "38"},
            {"name": "πατάτες διαλογής για ζωοτροφή", "yield_ratio": "0.07", "market_price_eur_per_tonne": "70"},
        ],
        "grapes": [
            {"name": "στέμφυλα", "yield_ratio": "0.20", "market_price_eur_per_tonne": "70"},
            {"name": "κουκούτσι σταφυλιού", "yield_ratio": "0.04", "market_price_eur_per_tonne": "220"},
        ],
        "almonds": [
            {"name": "περικάρπια αμυγδάλου", "yield_ratio": "1.20", "market_price_eur_per_tonne": "135"},
            {"name": "κελύφη αμυγδάλου", "yield_ratio": "0.45", "market_price_eur_per_tonne": "75"},
        ],
        "pistachios": [
            {"name": "περικάρπια φιστικιού", "yield_ratio": "0.90", "market_price_eur_per_tonne": "80"},
            {"name": "κελύφη φιστικιού", "yield_ratio": "0.35", "market_price_eur_per_tonne": "95"},
        ],
        "chickpeas": [
            {"name": "υπολείμματα φυτών για ζωοτροφή", "yield_ratio": "0.70", "market_price_eur_per_tonne": "85"},
            {"name": "σπασμένα όσπρια", "yield_ratio": "0.04", "market_price_eur_per_tonne": "420"},
        ],
        "lentils": [
            {"name": "άχυρο ζωοτροφής", "yield_ratio": "0.65", "market_price_eur_per_tonne": "80"},
            {"name": "σπασμένα όσπρια", "yield_ratio": "0.04", "market_price_eur_per_tonne": "500"},
        ],
        "beans": [
            {"name": "υπολείμματα φυτών για ζωοτροφή", "yield_ratio": "0.60", "market_price_eur_per_tonne": "75"},
            {"name": "σπασμένα φασόλια", "yield_ratio": "0.05", "market_price_eur_per_tonne": "520"},
        ],
        "sunflower": [
            {"name": "ηλιάλευρο", "yield_ratio": "0.58", "market_price_eur_per_tonne": "255"},
            {"name": "φλοιοί", "yield_ratio": "0.18", "market_price_eur_per_tonne": "70"},
        ],
        "rapeseed": [
            {"name": "κραμβάλευρο", "yield_ratio": "0.60", "market_price_eur_per_tonne": "285"},
            {"name": "βιομάζα αχύρου", "yield_ratio": "0.70", "market_price_eur_per_tonne": "55"},
        ],
        "alfalfa": [
            {"name": "άλευρο φύλλων", "yield_ratio": "0.18", "market_price_eur_per_tonne": "240"},
            {"name": "στρωμνή στελεχών", "yield_ratio": "0.20", "market_price_eur_per_tonne": "65"},
        ],
        "oranges": [
            {"name": "φλούδα εσπεριδοειδών", "yield_ratio": "0.45", "market_price_eur_per_tonne": "55"},
            {"name": "κλάσμα αιθέριου ελαίου", "yield_ratio": "0.004", "market_price_eur_per_tonne": "1800"},
        ],
        "apples": [
            {"name": "πούλπα μήλου", "yield_ratio": "0.25", "market_price_eur_per_tonne": "52"},
            {"name": "διαλογές για χυμό", "yield_ratio": "0.08", "market_price_eur_per_tonne": "110"},
        ],
        "kiwi": [
            {"name": "διαλογές για χυμό", "yield_ratio": "0.08", "market_price_eur_per_tonne": "130"},
            {"name": "πούλπα ακτινιδίου", "yield_ratio": "0.12", "market_price_eur_per_tonne": "50"},
        ],
        "watermelon": [
            {"name": "καρπός για χυμό", "yield_ratio": "0.10", "market_price_eur_per_tonne": "75"},
            {"name": "βιομάζα φλούδας", "yield_ratio": "0.18", "market_price_eur_per_tonne": "28"},
        ],
    }
    return rates.get(crop_id, [{"name": "υπόλειμμα αγρού", "yield_ratio": "0.20", "market_price_eur_per_tonne": "40"}])


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
            {"level": "ok", "text": "Τα αγροτεμάχια και οι καλλιεργητικές περίοδοι είναι συνδεδεμένα"},
            {"level": "ok", "text": "Η εμπιστοσύνη τηλεπισκόπησης είναι πάνω από το όριο ελέγχου"},
            {"level": "warn", "text": f"{len(missing_documents)} ομάδες απαιτούμενων δικαιολογητικών χρειάζονται ακόμη υποβολή"},
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
        "active_incident": "Demo συμβάν ξηρασίας",
        "severity": "μέτρια",
        "response_status": "επιλέξιμο για αξιολόγηση",
        "gross_payment_eur": str(final_amount),
        "property_value_eur": str(property_value),
        "property_destruction_loss_eur": str(destruction_loss),
        "collective_revenue_loss_eur": str(collective_loss),
        "weather_trigger": "έλλειμμα βροχόπτωσης και χαμηλή υγρασία εδάφους",
        "scenarios": [
            {"label": "Ξηρασία 20%", "value": "234.60"},
            {"label": "Ξηρασία 40%", "value": str(final_amount)},
            {"label": "Πλημμύρα 60%", "value": "703.80"},
            {"label": "Πυρκαγιά 80%", "value": "938.40"},
        ],
    }


def _assistant_prompts(documents: list[dict[str, Any]], subsidy_claim: Any) -> list[dict[str, str]]:
    missing = [requirement["label"] for requirement in _document_requirements(documents) if requirement["status"] == "needed"]
    next_step = "Υποβολή υπολοίπων δικαιολογητικών" if missing else "Έλεγχος υπολογισμού πληρωμής"
    risk_note = "Δεν υπάρχουν ενεργές σημάνσεις κινδύνου ενίσχυσης" if not subsidy_claim.risk_flags else ", ".join(subsidy_claim.risk_flags)
    return [
        {"role": "assistant", "message": "Καλώς ήρθατε. Μπορώ να σας καθοδηγήσω στη δήλωση γης, την υποβολή δικαιολογητικών, τον έλεγχο και την πρόβλεψη πληρωμών."},
        {"role": "assistant", "message": f"Προτεινόμενη επόμενη ενέργεια: {next_step}."},
        {"role": "assistant", "message": f"Κατάσταση ελέγχου: {risk_note}."},
        {"role": "assistant", "message": "Για δήλωση γης, ξεκινήστε με σχεδίαση Google Maps ή εισαγωγή ορίου Google Earth KML."},
    ]


DASHBOARD_HTML = """<!doctype html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Πύλη Αγροτικών Ενισχύσεων AgroLedger</title>
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
    .login-copy, .login-form, .registration-form, .card, .modal-panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .login-copy { padding: 30px; }
    .login-copy h1 { margin: 0 0 10px; font-size: 32px; letter-spacing: 0; }
    .login-copy p { margin: 0; color: var(--muted); line-height: 1.5; }
    .login-form, .registration-form { padding: 22px; }
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
    input[type="radio"] { width: auto; min-height: 0; }
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
    .quick-actions label {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin: 0;
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
    }
    .language-switch {
      position: fixed;
      top: 14px;
      right: 14px;
      z-index: 60;
      display: inline-flex;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, .94);
      box-shadow: var(--shadow);
    }
    .language-switch button {
      min-height: 30px;
      padding: 5px 9px;
      border-color: transparent;
      background: transparent;
      color: var(--ink);
    }
    .language-switch button.active {
      background: var(--green);
      color: white;
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
  <div class="language-switch" aria-label="Language selection">
    <button id="language-el" type="button" class="active">EL</button>
    <button id="language-en" type="button">EN</button>
  </div>
  <section class="login" id="login">
    <div class="login-panel">
      <div class="login-copy">
        <h1>Πύλη Αγροτικών Ενισχύσεων AgroLedger</h1>
        <p>Ασφαλής τοπική πύλη για δηλώσεις γης, υποβολή δικαιολογητικών, ελεγκτική ανάλυση, οικονομικό έλεγχο, προβλέψεις πληρωμών, διαχείριση κρίσεων και καθοδήγηση.</p>
        <div class="quick-actions">
          <span class="tag">Υπηρεσίες έτοιμες</span>
          <span class="tag blue">Demo ταυτότητα ενεργή</span>
          <span class="tag warn">Τοπική λειτουργία MVP</span>
        </div>
      </div>
      <form class="login-form" id="login-form">
        <h2>Σύνδεση</h2>
        <div class="field">
          <label for="tax-id">ΑΦΜ</label>
          <input id="tax-id" value="EL123456789" autocomplete="username">
        </div>
        <div class="field">
          <label for="password">Κωδικός πρόσβασης</label>
          <input id="password" type="password" value="demo" autocomplete="current-password">
        </div>
        <button type="submit">Είσοδος στο σύστημα</button>
        <div class="quick-actions">
          <button class="secondary" id="show-register" type="button">Εγγραφή νέου αιτούντος</button>
        </div>
        <p class="muted">Χρησιμοποιήστε τα demo στοιχεία που είναι ήδη συμπληρωμένα ή κάντε πρώτα εγγραφή νέου αιτούντος.</p>
      </form>
    </div>
  </section>

  <section class="login" id="registration" style="display:none">
    <div class="login-panel">
      <div class="login-copy">
        <h1>Εγγραφή Αιτούντος</h1>
        <p>Συμπληρώστε το προφίλ του αιτούντος και τον έλεγχο δημόσιας ακεραιότητας πριν επιστρέψετε στη σύνδεση.</p>
        <div class="quick-actions">
          <span class="tag">Προφίλ αιτούντος</span>
          <span class="tag blue">Έλεγχος ακεραιότητας</span>
          <span class="tag warn">Δρομολόγηση ελέγχου</span>
        </div>
      </div>
      <form class="registration-form" id="registration-form">
        <h2>Δημιουργία λογαριασμού</h2>
        <div class="field">
          <label for="first-name">Όνομα</label>
          <input id="first-name" value="Demo" autocomplete="given-name" required>
        </div>
        <div class="field">
          <label for="surname">Επώνυμο</label>
          <input id="surname" value="Παραγωγός Ελιάς" autocomplete="family-name" required>
        </div>
        <div class="field">
          <label for="occupation">Επάγγελμα</label>
          <input id="occupation" value="Αγρότης" autocomplete="organization-title" required>
        </div>
        <div class="field">
          <label for="registration-tax-id">ΑΦΜ</label>
          <input id="registration-tax-id" value="EL123456789" autocomplete="username" required>
        </div>
        <div class="field">
          <label for="registration-password">Κωδικός πρόσβασης</label>
          <input id="registration-password" type="password" value="demo" autocomplete="new-password" required>
        </div>
        <div class="field">
          <label>Δημόσιο αξίωμα ή έκθεση σε σύγκρουση συμφερόντων</label>
          <div class="quick-actions">
            <label><input type="radio" name="integrity-exposure" value="yes"> Ναι</label>
            <label><input type="radio" name="integrity-exposure" value="no" checked> Όχι</label>
          </div>
        </div>
        <button type="submit">Ολοκλήρωση εγγραφής</button>
        <div class="quick-actions">
          <button class="secondary" id="back-to-login" type="button">Επιστροφή στη σύνδεση</button>
        </div>
        <p class="muted">Ο έλεγχος ακεραιότητας χρησιμοποιεί δηλώσεις δημόσιου αξιώματος/σύγκρουσης και ουδέτερη αντιστοίχιση βάσεων δεδομένων, όχι κομματική προτίμηση.</p>
      </form>
    </div>
  </section>

  <section class="app" id="app">
    <div class="shell">
      <aside>
        <div class="brand">AgroLedger</div>
        <nav id="nav">
          <button class="active" data-section="overview">Επισκόπηση</button>
          <button data-section="documents">Δικαιολογητικά</button>
          <button data-section="land">Δήλωση Γης</button>
          <button data-section="forecast">Πρόβλεψη Καλλιέργειας</button>
          <button data-section="audit">Ελεγκτική Ανάλυση</button>
          <button data-section="finance">Οικονομικά</button>
          <button data-section="crisis">Διαχείριση Κρίσεων</button>
        </nav>
      </aside>
      <main>
        <header>
          <div>
            <h1 id="page-title">Επισκόπηση</h1>
            <p id="page-subtitle">Φόρτωση αρχικοποιημένων υπηρεσιών</p>
          </div>
          <div class="quick-actions">
            <button class="secondary" id="refresh" type="button">Ανανέωση</button>
            <button class="blue" data-open="upload">Υποβολή</button>
            <button class="gold" data-open="assistant">Βοηθός</button>
            <button class="secondary" id="logout" type="button">Έξοδος</button>
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
      <button title="Υποβολή δικαιολογητικών" data-open="upload">ΥΔ</button>
      <button title="Δήλωση γης" data-section-jump="land">ΔΓ</button>
      <button title="Άνοιγμα βοηθού" data-open="assistant">ΒΟ</button>
    </div>
  </section>

  <div class="modal" id="upload-modal">
    <div class="modal-panel">
      <div class="modal-head">
        <h2>Υποβολή Απαιτούμενου Δικαιολογητικού</h2>
        <button class="secondary" data-close="upload">Κλείσιμο</button>
      </div>
      <form id="upload-form">
        <div class="field">
          <label for="document-type">Τύπος δικαιολογητικού</label>
          <select id="document-type">
            <option value="identity">Ταυτότητα και φορολογικό πιστοποιητικό</option>
            <option value="land">Τίτλος γης, μίσθωση ή κτηματολογικό απόσπασμα</option>
            <option value="finance">Οικονομικά στοιχεία και τιμολόγια</option>
            <option value="bank">Απόδειξη IBAN</option>
            <option value="crisis">Τεκμήρια συμβάντος κρίσης</option>
          </select>
        </div>
        <div class="field">
          <label for="file-input">Αρχείο</label>
          <input id="file-input" type="file">
        </div>
        <button type="submit">Υποβολή δικαιολογητικού</button>
      </form>
    </div>
  </div>

  <div class="modal" id="assistant-modal">
    <div class="modal-panel">
      <div class="modal-head">
        <h2>Βοηθός Εφαρμογής</h2>
        <button class="secondary" data-close="assistant">Κλείσιμο</button>
      </div>
      <div class="messages" id="messages"></div>
      <form class="chat-row" id="chat-form">
        <input id="chat-input" placeholder="Ρωτήστε για δικαιολογητικά, γη, έλεγχο, οικονομικά, κρίσεις ή πληρωμές">
        <button type="submit">Αποστολή</button>
      </form>
    </div>
  </div>

  <script>
    let state = null;
    let selectedCropId = null;
    let cropAnalysisReady = false;
    let applicantScreening = null;
    let applicantProfile = null;
    let currentLanguage = localStorage.getItem("agroledger-language") || "el";
    const greekToEnglish = {
      "Πύλη Αγροτικών Ενισχύσεων AgroLedger": "AgroLedger Agricultural Support Portal",
      "Ασφαλής τοπική πύλη για δηλώσεις γης, υποβολή δικαιολογητικών, ελεγκτική ανάλυση, οικονομικό έλεγχο, προβλέψεις πληρωμών, διαχείριση κρίσεων και καθοδήγηση.": "Secure local portal for land declarations, document submission, audit analysis, financial review, payment forecasts, crisis management, and guidance.",
      "Υπηρεσίες έτοιμες": "Services ready",
      "Demo ταυτότητα ενεργή": "Demo identity active",
      "Τοπική λειτουργία MVP": "Local MVP mode",
      "Σύνδεση": "Sign in",
      "ΑΦΜ": "Tax identifier",
      "Κωδικός πρόσβασης": "Password",
      "Είσοδος στο σύστημα": "Enter system",
      "Εγγραφή νέου αιτούντος": "Register new applicant",
      "Χρησιμοποιήστε τα demo στοιχεία που είναι ήδη συμπληρωμένα ή κάντε πρώτα εγγραφή νέου αιτούντος.": "Use the pre-filled demo details or register a new applicant first.",
      "Εγγραφή Αιτούντος": "Applicant Registration",
      "Συμπληρώστε το προφίλ του αιτούντος και τον έλεγχο δημόσιας ακεραιότητας πριν επιστρέψετε στη σύνδεση.": "Complete the applicant profile and public-integrity check before returning to sign in.",
      "Προφίλ αιτούντος": "Applicant profile",
      "Έλεγχος ακεραιότητας": "Integrity check",
      "Δρομολόγηση ελέγχου": "Audit routing",
      "Δημιουργία λογαριασμού": "Create account",
      "Όνομα": "First name",
      "Επώνυμο": "Surname",
      "Επάγγελμα": "Occupation",
      "Δημόσιο αξίωμα ή έκθεση σε σύγκρουση συμφερόντων": "Public office or conflict-of-interest exposure",
      "Ναι": "Yes",
      "Όχι": "No",
      "Ολοκλήρωση εγγραφής": "Complete registration",
      "Επιστροφή στη σύνδεση": "Back to sign in",
      "Ο έλεγχος ακεραιότητας χρησιμοποιεί δηλώσεις δημόσιου αξιώματος/σύγκρουσης και ουδέτερη αντιστοίχιση βάσεων δεδομένων, όχι κομματική προτίμηση.": "The integrity check uses public-office/conflict declarations and neutral database matching, not party preference.",
      "Επισκόπηση": "Overview",
      "Δικαιολογητικά": "Documents",
      "Δήλωση Γης": "Land Declaration",
      "Πρόβλεψη Καλλιέργειας": "Crop Forecast",
      "Ελεγκτική Ανάλυση": "Audit Analysis",
      "Οικονομικά": "Financials",
      "Διαχείριση Κρίσεων": "Crisis Management",
      "Φόρτωση αρχικοποιημένων υπηρεσιών": "Loading initialized services",
      "Ανανέωση": "Refresh",
      "Υποβολή": "Upload",
      "Βοηθός": "Assistant",
      "Έξοδος": "Logout",
      "Υποβολή Απαιτούμενου Δικαιολογητικού": "Upload Required Document",
      "Κλείσιμο": "Close",
      "Τύπος δικαιολογητικού": "Document type",
      "Ταυτότητα και φορολογικό πιστοποιητικό": "Identity and tax certificate",
      "Τίτλος γης, μίσθωση ή κτηματολογικό απόσπασμα": "Land title, lease, or cadastral extract",
      "Οικονομικά στοιχεία και τιμολόγια": "Financial records and invoices",
      "Απόδειξη IBAN": "IBAN proof",
      "Τεκμήρια συμβάντος κρίσης": "Crisis incident evidence",
      "Αρχείο": "File",
      "Υποβολή δικαιολογητικού": "Upload document",
      "Βοηθός Εφαρμογής": "Application Assistant",
      "Αποστολή": "Send",
      "Αρχικοποιημένες υπηρεσίες, εικόνα πληρωμών και προφίλ δικαιούχου": "Initialized services, payment view, and beneficiary profile",
      "Υποβολή και έλεγχος όλων των απαιτούμενων στοιχείων": "Submit and review all required evidence",
      "Δήλωση αγροτεμαχίων από Google Maps, Google Earth ή GeoJSON": "Declare parcels from Google Maps, Google Earth, or GeoJSON",
      "Βάση αποδόσεων και τεχνοοικονομική ανάλυση": "Yield database and techno-economic analysis",
      "Βαθμολόγηση κινδύνου, έλεγχοι τεκμηρίων και ιστορικό ελέγχου": "Risk score, evidence checks, and audit history",
      "Οικονομικά στοιχεία και σενάρια πληρωμής ενίσχυσης": "Financial records and support-payment scenarios",
      "Αντιμετώπιση συμβάντων και προβλέψεις ακαθάριστης πληρωμής": "Incident response and gross-payment forecasts",
      "Ακαθάριστη στήριξη": "Gross support",
      "Καθαρό μετά συμψηφισμούς": "Net after offsets",
      "Καθαρή αξία προϊόντος": "Net product value",
      "Κίνδυνος πρόβλεψης": "Forecast risk",
      "Καλύτερη καλλιέργεια": "Best crop",
      "Προφίλ Δικαιούχου": "Beneficiary Profile",
      "Όνομα": "Name",
      "Τύπος δικαιούχου": "Beneficiary type",
      "Ενεργός αγρότης": "Active farmer",
      "Έλεγχος Ακεραιότητας Εγγραφής": "Registration Integrity Check",
      "Πληρωτέο Ποσό": "Payable Amount",
      "Τελική ενίσχυση": "Final support",
      "Συμψηφισμός οφειλής": "Debt offset",
      "Καταβλητέα ενίσχυση": "Disbursable support",
      "Ακαθάριστη κρίσης": "Crisis gross",
      "Απώλεια εσόδων": "Revenue loss",
      "Αρχικοποιημένες Υπηρεσίες": "Initialized Services",
      "Γράφημα Πληρωμών": "Payment Graph",
      "Απαιτούμενα Στοιχεία": "Required Evidence",
      "Υποβληθέντα Δικαιολογητικά": "Submitted Documents",
      "Ενέργειες Υποβολής": "Upload Actions",
      "Έλεγχος ελέγχου": "Review audit",
      "Ανάλυση Δικαιολογητικών": "Document Analysis",
      "Χώρος Δήλωσης μέσω Google Maps": "Declaration Workspace through Google Maps",
      "Άνοιγμα Google Maps": "Open Google Maps",
      "Εισαγωγή Google Earth KML": "Import Google Earth KML",
      "Υποβολή GeoJSON": "Submit GeoJSON",
      "Κατάσταση Αγροτεμαχίου": "Parcel Status",
      "Ενεργή πηγή": "Active source",
      "Κέντρο χάρτη": "Map center",
      "Δηλωμένη έκταση": "Declared area",
      "Επιλέξιμη έκταση": "Eligible area",
      "Τεχνοοικονομική Ανάλυση": "Techno-Economic Analysis",
      "Τύπος απόδοσης καλλιέργειας": "Crop yield type",
      "Πηγή πρόβλεψης": "Forecast source",
      "Εκτέλεση Ανάλυσης": "Run Analysis",
      "Αποδόσεις Βάσης Δεδομένων": "Database Yields",
      "Καιρός Υπηρεσίας Πρόβλεψης": "Forecast Service Weather",
      "Γράφημα Βροχόπτωσης": "Rainfall Graph",
      "Γράφημα Μέγιστης Αγοραίας Αξίας": "Market Cap Graph",
      "Βαθμολογία Ελέγχου": "Audit Score",
      "Κατάσταση Ελέγχου Αιτούντος": "Applicant Audit Status",
      "Ευρήματα": "Findings",
      "Ενέργειες Ελέγχου Αιτούντος": "Applicant Review Actions",
      "Πρόσφατο Ιστορικό Ελέγχου": "Recent Audit History",
      "Ενέργεια": "Action",
      "Οντότητα": "Entity",
      "Δημιουργήθηκε": "Created",
      "Επιλεγμένη δηλωμένη απόδοση": "Selected stated yield",
      "Προβλεπόμενη απόδοση": "Forecast yield",
      "Μέγιστη αγοραία αξία": "Market cap",
      "Αξία υποπροϊόντων": "By-product value",
      "Οικονομική Ανάλυση": "Financial Analysis",
      "Γράφημα Εσόδων και Στήριξης": "Revenue and Support Graph",
      "Σενάρια Πληρωμής": "Payment Scenarios",
      "Κρατήσεις Πρώτης Πώλησης": "First-Sale Deductions",
      "Βιομηχανική Ανάλυση Δηλωμένης Απόδοσης": "Industry Analysis of Stated Yield",
      "Γράφημα Αξίας Απόδοσης": "Yield Value Graph",
      "Τιμές Προϊόντων και Υποπροϊόντων": "Product and By-product Rates",
      "Μέγιστη Αξία έναντι Περιθωρίου": "Market Cap vs Margin",
      "Πίνακας Εσόδων Υποπροϊόντων": "By-product Revenue Table",
      "Ανάλυση Παραγωγής Σπόρου": "Seed Production Analysis",
      "Αντιμετώπιση Συμβάντος": "Incident Response",
      "Γράφημα Πληρωμής Κρίσης": "Crisis Payment Graph",
      "Ενέργειες Συμβάντος": "Incident Actions",
      "Υποβολή τεκμηρίων συμβάντος": "Upload incident evidence",
      "Αίτημα επιτόπιου ελέγχου": "Request field inspection",
      "Εξαγωγή φακέλου κρίσης": "Export crisis file",
      "Πρόβλεψη": "Forecast",
      "Μέγιστο": "Maximum",
      "Κόστη": "Costs",
      "Εισόδημα": "Income",
      "Ενίσχυση": "Support",
      "Περιθώριο": "Margin",
      "Προϊόν": "Product",
      "Υποπροϊόντα": "By-products",
      "Μέγ. αξία": "Market cap",
      "Ακαθάριστο": "Gross",
      "Καθ. περιθώριο": "Net margin",
      "εμπιστοσύνη ελέγχου": "audit confidence"
    };
    const englishToGreek = Object.fromEntries(Object.entries(greekToEnglish).map(([key, value]) => [value, key]));
    const placeholderTranslations = {
      "Ρωτήστε για δικαιολογητικά, γη, έλεγχο, οικονομικά, κρίσεις ή πληρωμές": "Ask about documents, land, audit, financials, crises, or payments"
    };
    const reversePlaceholderTranslations = Object.fromEntries(Object.entries(placeholderTranslations).map(([key, value]) => [value, key]));
    const titles = {
      overview: ["Επισκόπηση", "Αρχικοποιημένες υπηρεσίες, εικόνα πληρωμών και προφίλ δικαιούχου"],
      documents: ["Δικαιολογητικά", "Υποβολή και έλεγχος όλων των απαιτούμενων στοιχείων"],
      land: ["Δήλωση Γης", "Δήλωση αγροτεμαχίων από Google Maps, Google Earth ή GeoJSON"],
      forecast: ["Πρόβλεψη Καλλιέργειας", "Βάση αποδόσεων και τεχνοοικονομική ανάλυση"],
      audit: ["Ελεγκτική Ανάλυση", "Βαθμολόγηση κινδύνου, έλεγχοι τεκμηρίων και ιστορικό ελέγχου"],
      finance: ["Οικονομικά", "Οικονομικά στοιχεία και σενάρια πληρωμής ενίσχυσης"],
      crisis: ["Διαχείριση Κρίσεων", "Αντιμετώπιση συμβάντων και προβλέψεις ακαθάριστης πληρωμής"],
    };
    const money = (value) => `${Number(value || 0).toLocaleString(currentLanguage === "el" ? "el-GR" : "en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2})} EUR`;
    const fact = (label, value, cls = "") => `<div class="fact"><span class="muted">${label}</span><strong class="${cls}">${value}</strong></div>`;
    const card = (title, body) => `<div class="card"><h2>${title}</h2>${body}</div>`;

    document.getElementById("language-el").addEventListener("click", () => setLanguage("el"));
    document.getElementById("language-en").addEventListener("click", () => setLanguage("en"));
    setLanguage(currentLanguage);

    document.getElementById("show-register").addEventListener("click", () => {
      document.getElementById("login").style.display = "none";
      document.getElementById("registration").style.display = "grid";
      applyLanguage();
    });

    document.getElementById("back-to-login").addEventListener("click", () => {
      document.getElementById("registration").style.display = "none";
      document.getElementById("login").style.display = "grid";
      applyLanguage();
    });

    document.getElementById("registration-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      applicantProfile = {
        first_name: document.getElementById("first-name").value.trim(),
        surname: document.getElementById("surname").value.trim(),
        occupation: document.getElementById("occupation").value.trim(),
        tax_identifier: document.getElementById("registration-tax-id").value.trim(),
        public_integrity_exposure: document.querySelector("input[name='integrity-exposure']:checked").value,
      };
      const screeningResponse = await fetch("/applicant-screening", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(applicantProfile),
      });
      if (!screeningResponse.ok) throw new Error(`Ο έλεγχος αιτούντος απέτυχε: ${screeningResponse.status}`);
      applicantScreening = (await screeningResponse.json()).screening;
      document.getElementById("tax-id").value = applicantProfile.tax_identifier;
      document.getElementById("password").value = document.getElementById("registration-password").value;
      document.getElementById("registration").style.display = "none";
      document.getElementById("login").style.display = "grid";
    });

    document.getElementById("login-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!applicantScreening) {
        applicantProfile = {
          first_name: "Demo",
          surname: "Παραγωγός Ελιάς",
          occupation: "Αγρότης",
          tax_identifier: document.getElementById("tax-id").value.trim(),
          public_integrity_exposure: "no",
        };
        const screeningResponse = await fetch("/applicant-screening", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(applicantProfile),
        });
        if (!screeningResponse.ok) throw new Error(`Ο έλεγχος αιτούντος απέτυχε: ${screeningResponse.status}`);
        applicantScreening = (await screeningResponse.json()).screening;
      }
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
          enhanced_audit: applicantScreening?.enhanced_audit || false,
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
      applyLanguage();
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
      document.getElementById("page-subtitle").textContent = `${state.farmer.legal_name} - όλες οι υπηρεσίες έχουν αρχικοποιηθεί`;
      applyLanguage();
      requestAnimationFrame(drawCharts);
    }

    function renderOverview() {
      const s = state.summary;
      document.getElementById("overview").innerHTML = `
        <div class="grid metrics">
          ${metric("Ακαθάριστη στήριξη", money(state.financial_analysis.gross_public_support_eur))}
          ${metric("Καθαρό μετά συμψηφισμούς", money(state.financial_analysis.net_after_offsets_eur))}
          ${metric("Καθαρή αξία προϊόντος", money(state.financial_analysis.first_sale_deductions.net_product_after_deductions_eur))}
          ${metric("Δικαιολογητικά", `${s.documents}/5`)}
          ${metric("Κίνδυνος πρόβλεψης", state.crop_forecast.weather_forecast.current.risk)}
          ${metric("Καλύτερη καλλιέργεια", state.crop_forecast.best_option.label)}
        </div>
        <div class="grid two">
          ${card("Προφίλ Δικαιούχου", [
            fact("Όνομα", state.farmer.legal_name),
            fact("ΑΦΜ", state.farmer.tax_identifier),
            fact("Τύπος δικαιούχου", state.farmer.farmer_type),
            fact("Ενεργός αγρότης", state.farmer.active_farmer ? "Ναι" : "Όχι"),
          ].join(""))}
          ${card("Έλεγχος Ακεραιότητας Εγγραφής", applicantIntegrity())}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Πληρωτέο Ποσό", [
            fact("Τελική ενίσχυση", money(state.subsidy_claim.final_amount_eur), "money"),
            fact("Συμψηφισμός οφειλής", money(state.subsidy_claim.debt_offset.offset_eur), "warn-text"),
            fact("Καταβλητέα ενίσχυση", money(state.subsidy_claim.debt_offset.disbursable_eur), "money"),
            fact("Ακαθάριστη κρίσης", money(state.crisis_management.gross_payment_eur), "money"),
            fact("Απώλεια εσόδων", money(state.crisis_management.collective_revenue_loss_eur), "warn-text"),
          ].join(""))}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Αρχικοποιημένες Υπηρεσίες", servicesTable())}
          ${card("Γράφημα Πληρωμών", '<canvas id="payment-chart"></canvas>')}
        </div>`;
    }

    function renderDocuments() {
      document.getElementById("documents").innerHTML = `
        <div class="grid two">
          ${card("Απαιτούμενα Στοιχεία", requirementsTable())}
          ${card("Υποβληθέντα Δικαιολογητικά", documentsTable())}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Ενέργειες Υποβολής", '<div class="quick-actions"><button data-open="upload">Υποβολή δικαιολογητικού</button><button class="secondary" data-section-jump="audit">Έλεγχος ελέγχου</button></div><p class="muted">Η πύλη καταγράφει μεταδεδομένα δικαιολογητικών, αποδίδει κατάσταση ελέγχου και τροφοδοτεί την ελεγκτική και οικονομική ανάλυση.</p>')}
          ${card("Ανάλυση Δικαιολογητικών", documentAnalysis())}
        </div>`;
      rebindDynamicButtons();
    }

    function renderLand() {
      const land = state.land_declaration;
      document.getElementById("land").innerHTML = `
        <div class="grid two">
          <div class="card">
            <h2>Χώρος Δήλωσης μέσω Google Maps</h2>
            <iframe class="google-map" title="Google Maps parcel center" loading="lazy" src="${land.google_maps_url}&output=embed"></iframe>
            <div class="map-shell"><div class="parcel"></div></div>
            <div class="map-actions">
              <button onclick="window.open('${land.google_maps_url}', '_blank')">Άνοιγμα Google Maps</button>
              <button class="blue">Εισαγωγή Google Earth KML</button>
              <button class="secondary">Υποβολή GeoJSON</button>
            </div>
          </div>
          ${card("Κατάσταση Αγροτεμαχίου", [
            fact("Ενεργή πηγή", land.active_source),
            fact("Κέντρο χάρτη", `${land.map_center.lat}, ${land.map_center.lon}`),
            fact("Δηλωμένη έκταση", `${land.declared_area_ha} ha`),
            fact("Επιλέξιμη έκταση", `${land.eligible_area_ha} ha`),
          ].join("") + sourcesList(land.sources))}
        </div>`;
    }

    function renderCropForecast() {
      const forecast = state.crop_forecast;
      const selected = selectedForecast();
      const result = cropAnalysisReady ? forecastResult(selected) : `<div class="card"><h2>Τεχνοοικονομική Ανάλυση</h2><p class="muted">Επιλέξτε τύπο καλλιέργειας από τη βάση αποδόσεων και πατήστε Εκτέλεση Ανάλυσης για να υπολογιστούν ετήσια απόδοση, κόστος, ακαθάριστο εισόδημα, ενίσχυση και περιθώριο.</p></div>`;
      document.getElementById("forecast").innerHTML = `
        <div class="forecast-window">
          <div class="forecast-controls">
            <div>
              <label for="crop-select">Τύπος απόδοσης καλλιέργειας</label>
              <select id="crop-select">${forecast.options.map((row) => `<option value="${row.id}" ${row.id === selected.id ? "selected" : ""}>${row.label} - ${row.forecast_yield_tonnes_per_ha} t/ha</option>`).join("")}</select>
            </div>
            <div>${fact("Δηλωμένη έκταση", `${forecast.declared_area_ha} ha`)}</div>
            <div>${fact("Πηγή πρόβλεψης", forecast.forecast_source)}</div>
            <div><button id="run-crop-analysis" type="button">Εκτέλεση Ανάλυσης</button></div>
          </div>
          <div class="grid two">
            ${card("Αποδόσεις Βάσης Δεδομένων", cropForecastTable())}
            ${card("Καιρός Υπηρεσίας Πρόβλεψης", forecastWeather())}
          </div>
          <div class="grid two" style="margin-top:14px">
            ${card("Γράφημα Βροχόπτωσης", '<canvas id="forecast-weather-chart"></canvas>')}
            ${card("Γράφημα Μέγιστης Αγοραίας Αξίας", '<canvas id="market-cap-chart"></canvas>')}
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
          ${card("Βαθμολογία Ελέγχου", `<canvas id="audit-chart"></canvas>`)}
          ${card("Κατάσταση Ελέγχου Αιτούντος", applicantIntegrity())}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Ευρήματα", state.audit_analysis.findings.map((f) => `<div class="fact"><span>${f.text}</span><strong class="${f.level === "warn" ? "warn-text" : "money"}">${f.level}</strong></div>`).join(""))}
          ${card("Ενέργειες Ελέγχου Αιτούντος", applicantReviewActions())}
        </div>
        <div class="card" style="margin-top:14px">
          <h2>Πρόσφατο Ιστορικό Ελέγχου</h2>
          <table><thead><tr><th>Ενέργεια</th><th>Οντότητα</th><th>Δημιουργήθηκε</th></tr></thead><tbody>${state.audit_events.map((event) => `<tr><td>${event.action}</td><td>${event.entity_type}</td><td>${event.created_at}</td></tr>`).join("")}</tbody></table>
        </div>`;
    }

    function renderFinance() {
      const selected = selectedForecast();
      document.getElementById("finance").innerHTML = `
        <div class="forecast-window" style="margin-bottom:14px">
          <div class="forecast-controls">
            <div>
              <label for="finance-crop-select">Επιλεγμένη δηλωμένη απόδοση</label>
              <select id="finance-crop-select">${state.crop_forecast.options.map((row) => `<option value="${row.id}" ${row.id === selected.id ? "selected" : ""}>${row.label} - ${row.forecast_yield_tonnes_per_ha} t/ha</option>`).join("")}</select>
            </div>
            <div>${fact("Προβλεπόμενη απόδοση", `${selected.forecast_yield_tonnes} t`)}</div>
            <div>${fact("Μέγιστη αγοραία αξία", money(selected.market_cap_eur), "money")}</div>
            <div>${fact("Αξία υποπροϊόντων", money(selected.byproduct_income_eur), "money")}</div>
          </div>
        </div>
        <div class="grid two">
          ${card("Οικονομική Ανάλυση", [
            fact("Ακαθάριστη δημόσια στήριξη", money(state.financial_analysis.gross_public_support_eur), "money"),
            fact("Φορολογική και οφειλόμενη έκθεση", money(state.financial_analysis.tax_and_debt_exposure_eur), "warn-text"),
            fact("Καθαρό μετά συμψηφισμούς", money(state.financial_analysis.net_after_offsets_eur), "money"),
            fact("Κάλυψη δικαιολογητικών", state.financial_analysis.document_coverage),
          ].join(""))}
          ${card("Γράφημα Εσόδων και Στήριξης", '<canvas id="finance-chart"></canvas>')}
        </div>
        <div class="card" style="margin-top:14px">
          <h2>Σενάρια Πληρωμής</h2>
          <table><thead><tr><th>Συνθήκη</th><th>Ακαθάριστο αποτέλεσμα</th><th>Καθαρό αποτέλεσμα</th></tr></thead><tbody>${state.financial_analysis.payment_scenarios.map((row) => `<tr><td>${row.label}</td><td>${money(row.gross)}</td><td>${money(row.net)}</td></tr>`).join("")}</tbody></table>
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Κρατήσεις Πρώτης Πώλησης", [
            fact("Πωληθείσα ποσότητα", `${state.financial_analysis.first_sale_deductions.sold_quantity_tonnes} τόνοι`),
            fact("Ακαθάριστη αξία προϊόντος", money(state.financial_analysis.first_sale_deductions.gross_product_value_eur), "money"),
            fact("Φόρος πρώτης πώλησης", money(state.financial_analysis.first_sale_deductions.first_sale_tax_eur), "warn-text"),
            fact("Τέλος αγοράς", money(state.financial_analysis.first_sale_deductions.market_fee_eur), "warn-text"),
            fact("Καθαρή αξία προϊόντος", money(state.financial_analysis.first_sale_deductions.net_product_after_deductions_eur), "money"),
          ].join(""))}
          ${card("Βιομηχανική Ανάλυση Δηλωμένης Απόδοσης", industryAnalysis(selected))}
        </div>
        <div class="grid three" style="margin-top:14px">
          ${card("Γράφημα Αξίας Απόδοσης", '<canvas id="finance-yield-chart"></canvas>')}
          ${card("Τιμές Προϊόντων και Υποπροϊόντων", '<canvas id="industry-rates-chart"></canvas>')}
          ${card("Μέγιστη Αξία έναντι Περιθωρίου", '<canvas id="finance-market-chart"></canvas>')}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Πίνακας Εσόδων Υποπροϊόντων", byproductTable(selected))}
          ${card("Ανάλυση Παραγωγής Σπόρου", seedTable())}
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
          ${card("Αντιμετώπιση Συμβάντος", [
            fact("Ενεργό συμβάν", crisis.active_incident),
            fact("Σοβαρότητα", crisis.severity),
            fact("Κατάσταση απόκρισης", crisis.response_status),
            fact("Ακαθάριστη πληρωμή", money(crisis.gross_payment_eur), "money"),
            fact("Καιρικός ενεργοποιητής", crisis.weather_trigger),
            fact("Αξία περιουσίας", money(crisis.property_value_eur), "money"),
            fact("Απώλεια καταστροφής περιουσίας", money(crisis.property_destruction_loss_eur), "warn-text"),
            fact("Συλλογική απώλεια εσόδων", money(crisis.collective_revenue_loss_eur), "warn-text"),
          ].join(""))}
          ${card("Γράφημα Πληρωμής Κρίσης", '<canvas id="crisis-chart"></canvas>')}
        </div>
        <div class="card" style="margin-top:14px">
          <h2>Ενέργειες Συμβάντος</h2>
          <div class="quick-actions"><button data-open="upload">Υποβολή τεκμηρίων συμβάντος</button><button class="blue">Αίτημα επιτόπιου ελέγχου</button><button class="secondary">Εξαγωγή φακέλου κρίσης</button></div>
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
          ${miniMetric("Ετήσια απόδοση", `${selected.forecast_yield_tonnes} t`, `${selected.forecast_yield_tonnes_per_ha} t/ha απόδοση βάσης`)}
          ${miniMetric("Μέγιστη απόδοση", `${selected.max_yield_tonnes} t`, `${selected.max_yield_tonnes_per_ha} t/ha μέγιστο benchmark`)}
          ${miniMetric("Ακαθάριστο εισόδημα", money(selected.gross_income_eur), "αξία προϊόντος")}
          ${miniMetric("Μέγιστη αγοραία αξία", money(selected.market_cap_eur), "μέγιστη απόδοση στην τιμή προϊόντος")}
        </div>
        <div class="grid two">
          ${card("Τεχνοοικονομική Ανάλυση", [
            fact("Επιλεγμένη καλλιέργεια", selected.label),
            fact("Κατηγορία", selected.category),
            fact("Πηγή απόδοσης", selected.yield_source),
            fact("Ταύτιση δηλωμένης καλλιέργειας", selected.declared_crop_match ? "ναι" : "εναλλακτικό σενάριο"),
            fact("Βαθμολογία εδάφους", `${selected.soil_score}%`, "money"),
            fact("Τιμή αγοράς", `${money(selected.market_price_eur_per_tonne)}/t`),
            fact("Αξία υποπροϊόντων", money(selected.byproduct_income_eur), "money"),
          ].join(""))}
          ${card("Κόστος και Ακαθάριστο Προϊόν", [
            fact("Συνολικά κόστη", money(selected.total_cost_eur), "warn-text"),
            fact("Ακαθάριστο εισόδημα προϊόντος", money(selected.gross_income_eur), "money"),
            fact("Μέγιστη αγοραία αξία", money(selected.market_cap_eur), "money"),
            fact("Ποσό ενίσχυσης", money(selected.subsidy_eur), "money"),
            fact("Ακαθάριστο με ενίσχυση", money(selected.gross_with_subsidy_eur), "money"),
            fact("Καθαρό περιθώριο", money(selected.net_margin_eur), Number(selected.net_margin_eur) >= 0 ? "money" : "warn-text"),
          ].join(""))}
        </div>
        <div class="grid three" style="margin-top:14px">
          ${card("Γράφημα Απόδοσης", '<canvas id="crop-yield-chart"></canvas>')}
          ${card("Γράφημα Εισοδήματος", '<canvas id="crop-finance-chart"></canvas>')}
          ${card("Σύγκριση Ενισχύσεων", '<canvas id="crop-subsidy-chart"></canvas>')}
        </div>
        <div class="grid two" style="margin-top:14px">
          ${card("Έδαφος και Λύση Αγρού", [
            fact("Ανάλυση εδάφους", selected.soil_note),
            fact("Ανάλυση καιρού", selected.weather_note, "warn-text"),
            fact("Προτεινόμενη ενέργεια", selected.solution, "money"),
          ].join(""))}
          ${card("Προτάσεις Σχεδιασμού", state.crop_forecast.solutions.map((text) => `<div class="fact"><span>${text}</span><strong class="money">λύση</strong></div>`).join(""))}
        </div>`;
    }

    function forecastWeather() {
      const weather = state.crop_forecast.weather_forecast;
      return `
        ${[
          fact("Σταθμός", weather.station),
          fact("Θερμοκρασία", `${weather.current.temperature_c} C`),
          fact("Υγρασία", `${weather.current.humidity_percent}%`),
          fact("Άνεμος", `${weather.current.wind_kph} kph`),
          fact("Βροχόπτωση 7 ημερών", `${weather.current.rainfall_7d_mm} mm`),
          fact("Υγρασία εδάφους", weather.current.soil_moisture, "warn-text"),
          fact("Κίνδυνος", weather.current.risk, "warn-text"),
        ].join("")}
        <table style="margin-top:12px"><thead><tr><th>Ημέρα</th><th>Συνθήκη</th><th>Βροχή</th><th>Κίνδυνος</th></tr></thead><tbody>${weather.forecast.map((row) => `<tr><td>${row.day}</td><td>${row.condition}</td><td>${row.rain_mm} mm</td><td><span class="tag ${row.risk === "high" ? "warn" : "blue"}">${row.risk}</span></td></tr>`).join("")}</tbody></table>`;
    }

    function industryAnalysis(selected) {
      return [
        fact("Επιλογή δηλωμένης απόδοσης", selected.label),
        fact("Προβλεπόμενη απόδοση", `${selected.forecast_yield_tonnes} t (${selected.forecast_yield_tonnes_per_ha} t/ha)`, "money"),
        fact("Μέγιστο benchmark απόδοσης", `${selected.max_yield_tonnes} t (${selected.max_yield_tonnes_per_ha} t/ha)`),
        fact("Τιμή κύριου προϊόντος", `${money(selected.industry_rates.primary_product_rate_eur_per_tonne)}/t`),
        fact("Ακαθάριστη μέγιστη αγοραία αξία", money(selected.market_cap_eur), "money"),
        fact("Αξία υποπροϊόντων", money(selected.byproduct_income_eur), "money"),
        fact("Καθαρό περιθώριο", money(selected.net_margin_eur), Number(selected.net_margin_eur) >= 0 ? "money" : "warn-text"),
      ].join("");
    }

    function byproductTable(selected) {
      return `<table><thead><tr><th>Υποπροϊόν</th><th>Αναλογία απόδοσης</th><th>Τιμή</th><th>Εκτιμώμενη αξία</th></tr></thead><tbody>${selected.industry_rates.byproducts.map((row) => {
        const value = Number(selected.forecast_yield_tonnes) * Number(row.yield_ratio) * Number(row.market_price_eur_per_tonne);
        return `<tr><td>${row.name}</td><td>${Number(row.yield_ratio).toFixed(2)} t/t</td><td>${money(row.market_price_eur_per_tonne)}/t</td><td><span class="money">${money(value)}</span></td></tr>`;
      }).join("")}</tbody></table>`;
    }

    function cropForecastTable() {
      return `<table><thead><tr><th>Καλλιέργεια</th><th>Απόδοση</th><th>Ακαθάριστο</th><th>Ενίσχυση</th><th>Περιθώριο</th></tr></thead><tbody>${state.crop_forecast.options.map((row) => `<tr><td>${row.label}<br><span class="muted">${row.category}</span></td><td>${row.forecast_yield_tonnes} t</td><td>${money(row.gross_income_eur)}</td><td>${money(row.subsidy_eur)}</td><td><span class="${Number(row.net_margin_eur) >= 0 ? "money" : "warn-text"}">${money(row.net_margin_eur)}</span></td></tr>`).join("")}</tbody></table>`;
    }

    function servicesTable() {
      return `<table><thead><tr><th>Υπηρεσία</th><th>Κατάσταση</th><th>Εγγραφές</th></tr></thead><tbody>${state.services.map((service) => `<tr><td>${service.name}</td><td><span class="status">${service.status}</span></td><td>${service.records}</td></tr>`).join("")}</tbody></table>`;
    }

    function requirementsTable() {
      return `<table><thead><tr><th>Απαιτούμενο στοιχείο</th><th>Κατάσταση</th></tr></thead><tbody>${state.document_requirements.map((row) => `<tr><td>${row.label}</td><td><span class="tag ${row.status === "needed" ? "warn" : ""}">${row.status}</span></td></tr>`).join("")}</tbody></table>`;
    }

    function documentsTable() {
      if (!state.documents.length) return '<p class="muted">Δεν υπάρχουν ακόμη υποβολές. Χρησιμοποιήστε την Υποβολή για ταυτότητα, γη, οικονομικά, τράπεζα ή τεκμήρια κρίσης.</p>';
      return `<table><thead><tr><th>Αρχείο</th><th>Τύπος</th><th>Κατάσταση</th></tr></thead><tbody>${state.documents.map((doc) => `<tr><td>${doc.file_name}</td><td>${doc.document_type}</td><td><span class="status">${doc.status}</span></td></tr>`).join("")}</tbody></table>`;
    }

    function documentAnalysis() {
      if (!state.documents.length) return '<p class="muted">Η οικονομική και ελεγκτική ανάλυση δικαιολογητικών θα εμφανιστεί μετά την υποβολή.</p>';
      return state.documents.map((doc) => `<div class="fact"><span>${doc.file_name}<br><span class="muted">${doc.analysis.audit_mode || "standard_audit"}</span></span><strong>${doc.analysis.risk} κίνδυνος</strong></div>`).join("");
    }

    function applicantIntegrity() {
      if (!applicantScreening) return '<p class="muted">Ο έλεγχος αιτούντος δεν έχει εκτελεστεί σε αυτή τη συνεδρία.</p>';
      const statusClass = applicantScreening.enhanced_audit ? "warn-text" : "money";
      return [
        fact("Αιτών", applicantScreening.applicant_name),
        fact("Επάγγελμα", applicantScreening.occupation),
        fact("Κατάσταση", applicantScreening.status, statusClass),
        fact("Λειτουργία ελέγχου δικαιολογητικών", applicantScreening.document_audit_mode, statusClass),
        fact("Έλεγχος βάσης δεδομένων", applicantScreening.database_checked ? "ναι" : "όχι"),
        fact("Πηγή βάσης δεδομένων", applicantScreening.database_source),
        fact("Αιτιολογία", applicantScreening.reasons.join(", ")),
      ].join("") + `<p class="muted" style="margin-bottom:0">${applicantScreening.note}</p>`;
    }

    function applicantReviewActions() {
      if (!applicantScreening) return '<p class="muted">Ολοκληρώστε τον έλεγχο εγγραφής για να εμφανιστούν οι ενέργειες αξιολόγησης αιτούντος.</p>';
      if (!applicantScreening.enhanced_audit) {
        return [
          fact("Επίπεδο ελέγχου", "τυπικός έλεγχος", "money"),
          fact("Κατάσταση αποδέσμευσης", "εκτός στενής παρακολούθησης", "money"),
          fact("Χειρισμός δικαιολογητικών", "κανονικοί έλεγχοι τεκμηρίων"),
        ].join("");
      }
      return [
        fact("Επίπεδο ελέγχου", "στενός έλεγχος", "warn-text"),
        fact("Χειρισμός δικαιολογητικών", "έλεγχος συνέπειας μεταξύ δικαιολογητικών", "warn-text"),
        fact("Επιλογές εντός συστήματος", "επισήμανση ουσιωδών αλλαγών για ελεγκτή", "warn-text"),
        fact("Κατάσταση αποδέσμευσης", "απαιτείται εκκαθάριση από ελεγκτή", "warn-text"),
      ].join("");
    }

    function seedTable() {
      const rows = state.seed_analysis.records;
      if (!rows.length) return '<p class="muted">Δεν υπάρχουν ακόμη δηλωμένες εγγραφές παραγωγής σπόρου.</p>';
      return `
        ${[
          fact("Συλλογικό δείγμα εκμεταλλεύσεων", state.seed_analysis.summary.sample_farms),
          fact("Λειτουργικό κόστος", money(state.seed_analysis.summary.total_operating_cost_eur), "warn-text"),
          fact("Ακαθάριστο έσοδο συνδεδεμένο με σπόρο", money(state.seed_analysis.summary.total_gross_revenue_eur), "money"),
          fact("Καθαρό περιθώριο", money(state.seed_analysis.summary.total_net_margin_eur), "money"),
          fact("Μέση απόδοση επένδυσης", `${Number(state.seed_analysis.summary.average_roi_percent).toFixed(1)}%`, "money"),
        ].join("")}
        <table style="margin-top:12px"><thead><tr><th>Αγροτεμάχιο</th><th>Ποικιλία</th><th>Αναμενόμενο</th><th>Περιθώριο</th><th>Κατάσταση</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${row.cadastral_reference}</td><td>${row.seed_variety}<br><span class="muted">${row.seed_lot}</span></td><td>${row.expected_production_tonnes} t</td><td>${money(row.net_margin_eur)}</td><td><span class="tag ${row.status === "review" ? "warn" : ""}">${row.status}</span></td></tr>`).join("")}</tbody></table>
        <h3 style="margin-top:14px">Συλλογική Βάση Benchmark</h3>
        <table><thead><tr><th>Καλλιέργεια</th><th>Περιοχή</th><th>Δόση σπόρου</th><th>Απόδοση</th><th>Τιμή</th></tr></thead><tbody>${state.seed_analysis.collective_database.map((row) => `<tr><td>${row.production_type}</td><td>${row.sample_region}<br><span class="muted">${row.sample_farms} εκμεταλλεύσεις</span></td><td>${row.seed_rate_tonnes_per_ha} t/ha</td><td>${row.expected_yield_tonnes_per_ha} t/ha</td><td>${money(row.market_price_eur_per_tonne)}/t</td></tr>`).join("")}</tbody></table>
        <h3 style="margin-top:14px">Τεχνοοικονομικές Συστάσεις</h3>
        ${state.seed_analysis.recommendations.map((text) => `<div class="fact"><span>${text}</span><strong class="money">ενεργό</strong></div>`).join("")}
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
      if (q.includes("γη") || q.includes("land") || q.includes("map")) return "Ανοίξτε τη Δήλωση Γης και επιλέξτε σχεδίαση Google Maps για νέο όριο ή Google Earth KML για υπάρχον αρχείο αγροτεμαχίου. Τα επιλέξιμα εκτάρια ενημερώνονται πριν τον υπολογισμό πληρωμής.";
      if (q.includes("δικαιολογη") || q.includes("document") || q.includes("upload")) return "Ανοίξτε την Υποβολή, επιλέξτε τύπο δικαιολογητικού και υποβάλετε το αρχείο. Θα καταγραφεί ως υποβληθέν και θα ενημερωθούν ο έλεγχος και η οικονομική κάλυψη.";
      if (q.includes("πληρω") || q.includes("ενισχυ") || q.includes("payment") || q.includes("subsidy")) return `Η τρέχουσα καταβλητέα ενίσχυση είναι ${money(state.subsidy_claim.debt_offset.disbursable_eur)} πριν από νέες δεσμεύσεις. Η ακαθάριστη πληρωμή κρίσης είναι ${money(state.crisis_management.gross_payment_eur)}.`;
      if (q.includes("κρισ") || q.includes("συμβαν") || q.includes("crisis") || q.includes("incident")) return "Χρησιμοποιήστε τη Διαχείριση Κρίσεων για υποβολή τεκμηρίων συμβάντος, αίτημα επιτόπιου ελέγχου και σύγκριση σεναρίων αποζημίωσης.";
      if (q.includes("καιρ") || q.includes("weather")) return `Ο τρέχων κίνδυνος αγρού είναι ${state.weather_conditions.current.risk}, με βροχόπτωση ${state.weather_conditions.current.rainfall_7d_mm} mm τις τελευταίες 7 ημέρες.`;
      if (q.includes("αποδοση") || q.includes("yield") || q.includes("crop forecast")) return `Ανοίξτε την Πρόβλεψη Καλλιέργειας για να συγκρίνετε αποδόσεις. Το καλύτερο καθαρό περιθώριο είναι ${state.crop_forecast.best_option.label} με ${money(state.crop_forecast.best_option.net_margin_eur)}.`;
      if (q.includes("σπορ") || q.includes("seed")) return "Η ανάλυση σπόρου συγκρίνει δηλωμένη χρήση σπόρου, αναμενόμενη παραγωγή, δηλωμένους τόνους, επαληθευμένους τόνους και απόκλιση για κάθε ιδιόκτητο αγροτεμάχιο.";
      if (q.includes("κρατησ") || q.includes("πωλη") || q.includes("deduction") || q.includes("sold")) return `Οι πρώτες πωληθείσες μονάδες έχουν καθαρή αξία ${money(state.financial_analysis.first_sale_deductions.net_product_after_deductions_eur)} μετά από φόρο και τέλη αγοράς.`;
      if (q.includes("οικονομ") || q.includes("φορο") || q.includes("finance") || q.includes("tax")) return "Η οικονομική ανάλυση συμφωνεί έσοδα πρώτης πώλησης, φορολογική έκθεση, συμψηφισμό οφειλής, ενίσχυση, αποζημίωση και υποβληθέντα τιμολόγια.";
      return "Μπορώ να βοηθήσω με δήλωση γης, υποβολή δικαιολογητικών, ευρήματα ελέγχου, οικονομική ανάλυση, διαχείριση κρίσεων και προβλέψεις πληρωμών.";
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
        {label: "Πρόβλεψη", value: Number(selected.forecast_yield_tonnes)},
        {label: "Μέγιστο", value: Number(selected.max_yield_tonnes)},
      ], ["#286f9e", "#2d7650"]);
      drawBars("crop-finance-chart", [
        {label: "Κόστη", value: Number(selected.total_cost_eur)},
        {label: "Εισόδημα", value: Number(selected.gross_income_eur)},
        {label: "Ενίσχυση", value: Number(selected.subsidy_eur)},
        {label: "Περιθώριο", value: Math.max(Number(selected.net_margin_eur), 0)},
      ], ["#ad7a25", "#286f9e", "#2d7650", "#6656a6"]);
      drawBars("crop-subsidy-chart", state.crop_forecast.options.slice(0, 10).map((row) => ({label: row.label, value: Number(row.subsidy_eur)})), ["#2d7650", "#286f9e", "#ad7a25", "#6656a6"]);
      drawBars("finance-yield-chart", [
        {label: "Προϊόν", value: Number(selected.gross_income_eur)},
        {label: "Υποπροϊόντα", value: Number(selected.byproduct_income_eur)},
        {label: "Ενίσχυση", value: Number(selected.subsidy_eur)},
      ], ["#286f9e", "#ad7a25", "#2d7650"]);
      drawBars("industry-rates-chart", [
        {label: "Προϊόν", value: Number(selected.market_price_eur_per_tonne)},
        ...selected.industry_rates.byproducts.map((row) => ({label: row.name, value: Number(row.market_price_eur_per_tonne)})),
      ], ["#286f9e", "#ad7a25", "#2d7650", "#6656a6"]);
      drawBars("finance-market-chart", [
        {label: "Μέγ. αξία", value: Number(selected.market_cap_eur)},
        {label: "Ακαθάριστο", value: Number(selected.gross_income_eur)},
        {label: "Καθ. περιθώριο", value: Math.max(Number(selected.net_margin_eur), 0)},
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
      ctx.fillText("εμπιστοσύνη ελέγχου", cx, 146);
      ctx.textAlign = "left";
    }

    function setLanguage(language) {
      currentLanguage = language;
      localStorage.setItem("agroledger-language", language);
      document.documentElement.lang = language;
      document.title = language === "el" ? "Πύλη Αγροτικών Ενισχύσεων AgroLedger" : "AgroLedger Agricultural Support Portal";
      document.getElementById("language-el").classList.toggle("active", language === "el");
      document.getElementById("language-en").classList.toggle("active", language === "en");
      applyLanguage();
      if (state) {
        requestAnimationFrame(drawCharts);
      }
    }

    function applyLanguage() {
      const textMap = currentLanguage === "en" ? greekToEnglish : englishToGreek;
      const placeholderMap = currentLanguage === "en" ? placeholderTranslations : reversePlaceholderTranslations;
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || ["SCRIPT", "STYLE"].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
          return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
      });
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach((node) => {
        const original = node.nodeValue;
        const trimmed = original.trim();
        if (textMap[trimmed]) {
          node.nodeValue = original.replace(trimmed, textMap[trimmed]);
        }
      });
      document.querySelectorAll("[placeholder]").forEach((element) => {
        const translated = placeholderMap[element.getAttribute("placeholder")];
        if (translated) element.setAttribute("placeholder", translated);
      });
      document.querySelectorAll("[title]").forEach((element) => {
        const translated = textMap[element.getAttribute("title")];
        if (translated) element.setAttribute("title", translated);
      });
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
