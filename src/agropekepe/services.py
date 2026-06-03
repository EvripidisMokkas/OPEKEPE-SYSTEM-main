"""Application service layer for the AgroLedger MVP."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from agropekepe.crisis import calculate_compensation
from agropekepe.eligibility import ParcelFacts, SubsidyDecision, calculate_subsidy, money
from agropekepe.finance import DebtOffsetDecision, TaxDecision, calculate_debt_offset, calculate_first_sale_tax
from agropekepe.geo import centroid, polygon_area_hectares
from agropekepe.models import (
    AnnualFarmerLedger,
    CompensationDecision,
    CrisisEvent,
    CropSeason,
    DebtAccount,
    Farmer,
    FirstSaleRecord,
    Parcel,
    RemoteSensingObservation,
)
from agropekepe.repository import AgroRepository


@dataclass(frozen=True)
class SubsidyClaimDecision:
    """Multi-line annual subsidy claim decision."""

    farmer_id: str
    claim_year: int
    line_items: tuple[SubsidyDecision, ...]
    gross_amount_eur: Decimal
    reductions_eur: Decimal
    final_amount_eur: Decimal
    debt_offset: DebtOffsetDecision
    risk_flags: tuple[str, ...]


class AgroLedgerService:
    """Coordinates farmer, land, production, finance, support, and crisis records."""

    def __init__(self, repository: AgroRepository, rules: dict[str, Any]) -> None:
        self.repository = repository
        self.rules = rules

    def register_farmer(
        self, tax_identifier: str, legal_name: str, farmer_type: str = "individual", active_farmer: bool = True
    ) -> Farmer:
        """Register a beneficiary in the agricultural ledger."""

        if farmer_type not in {"individual", "company", "cooperative"}:
            raise ValueError("farmer_type must be individual, company, or cooperative")
        return self.repository.add_farmer(
            Farmer(
                tax_identifier=tax_identifier,
                legal_name=legal_name,
                farmer_type=farmer_type,
                active_farmer=active_farmer,
            )
        )

    def register_parcel(
        self,
        farmer_id: str,
        cadastral_reference: str,
        right_type: str,
        geometry_geojson: dict[str, Any],
        declared_area_ha: Decimal | None = None,
        public_land_conflict: bool = False,
        protected_area_conflict: bool = False,
    ) -> Parcel:
        """Register land and calculate measurement facts from GeoJSON geometry."""

        if right_type not in {"owned", "leased", "communal", "other"}:
            raise ValueError("right_type must be owned, leased, communal, or other")
        measured_area = money(polygon_area_hectares(geometry_geojson))
        declared_area = declared_area_ha if declared_area_ha is not None else measured_area
        eligible_area = Decimal("0") if public_land_conflict else min(declared_area, measured_area)
        lat, lon = centroid(geometry_geojson)
        return self.repository.add_parcel(
            Parcel(
                farmer_id=farmer_id,
                cadastral_reference=cadastral_reference,
                right_type=right_type,
                declared_area_ha=declared_area,
                measured_area_ha=measured_area,
                eligible_area_ha=eligible_area,
                centroid_lat=lat,
                centroid_lon=lon,
                geometry_geojson=geometry_geojson,
                public_land_conflict=public_land_conflict,
                protected_area_conflict=protected_area_conflict,
            )
        )

    def enroll_production(
        self,
        parcel_id: str,
        farmer_id: str,
        claim_year: int,
        production_type: str,
        labelled_area_ha: Decimal,
        organic: bool = False,
        soil_cover: bool = False,
        irrigation_status: str = "unknown",
        declared_yield_tonnes: Decimal | None = None,
        verified_yield_tonnes: Decimal | None = None,
        crop_label_confidence: Decimal | None = None,
    ) -> CropSeason:
        """Label parcel hectares with an annual production type."""

        parcel = self.repository.get_parcel(parcel_id)
        if labelled_area_ha > parcel.eligible_area_ha:
            raise ValueError("labelled_area_ha cannot exceed parcel eligible area")
        if irrigation_status not in {"rainfed", "irrigated", "mixed", "unknown"}:
            raise ValueError("irrigation_status must be rainfed, irrigated, mixed, or unknown")
        return self.repository.add_crop_season(
            CropSeason(
                parcel_id=parcel_id,
                farmer_id=farmer_id,
                claim_year=claim_year,
                production_type=production_type,
                labelled_area_ha=labelled_area_ha,
                organic=organic,
                soil_cover=soil_cover,
                irrigation_status=irrigation_status,
                declared_yield_tonnes=declared_yield_tonnes,
                verified_yield_tonnes=verified_yield_tonnes,
                crop_label_confidence=crop_label_confidence,
            )
        )

    def record_remote_sensing(
        self,
        parcel_id: str,
        claim_year: int,
        provider: str,
        observation_type: str,
        confidence: Decimal,
        result: dict[str, Any],
        evidence_uri: str | None = None,
    ) -> RemoteSensingObservation:
        """Attach satellite, map, weather, or inspection evidence to a parcel."""

        if confidence < 0 or confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
        return self.repository.add_observation(
            RemoteSensingObservation(
                parcel_id=parcel_id,
                claim_year=claim_year,
                provider=provider,
                observation_type=observation_type,
                confidence=confidence,
                result=result,
                evidence_uri=evidence_uri,
            )
        )

    def record_first_sale(
        self,
        crop_season_id: str,
        invoice_number: str,
        buyer_tax_identifier: str,
        sale_date: str,
        product_type: str,
        quantity_tonnes: Decimal,
        unit_price_eur: Decimal,
        tax_rate: Decimal,
        mydata_mark: str | None = None,
    ) -> tuple[FirstSaleRecord, TaxDecision]:
        """Record and tax the first sale before downstream transformation."""

        first_sale = self.repository.add_first_sale(
            FirstSaleRecord(
                crop_season_id=crop_season_id,
                invoice_number=invoice_number,
                buyer_tax_identifier=buyer_tax_identifier,
                sale_date=sale_date,
                product_type=product_type,
                quantity_tonnes=quantity_tonnes,
                unit_price_eur=unit_price_eur,
                tax_rate=tax_rate,
                mydata_mark=mydata_mark,
            )
        )
        return first_sale, calculate_first_sale_tax(first_sale)

    def record_debt(self, farmer_id: str, debt_type: str, outstanding_eur: Decimal, status: str = "open") -> DebtAccount:
        """Record debt for annual payment offset analysis."""

        return self.repository.add_debt(
            DebtAccount(farmer_id=farmer_id, debt_type=debt_type, outstanding_eur=outstanding_eur, status=status)
        )

    def calculate_annual_subsidy_claim(self, farmer_id: str, claim_year: int) -> SubsidyClaimDecision:
        """Calculate all annual parcel/crop subsidy line items and debt offsets."""

        line_items: list[SubsidyDecision] = []
        risk_flags: set[str] = set()
        for crop_season in self.repository.list_crop_seasons(farmer_id=farmer_id, claim_year=claim_year):
            parcel = self.repository.get_parcel(crop_season.parcel_id)
            observations = self.repository.list_observations(parcel.parcel_id, claim_year)
            observed_confidence = self._best_crop_confidence(observations)
            confidence = crop_season.crop_label_confidence if crop_season.crop_label_confidence is not None else observed_confidence
            decision = calculate_subsidy(
                ParcelFacts(
                    parcel_hectares=min(parcel.eligible_area_ha, crop_season.labelled_area_ha),
                    production_type=crop_season.production_type,
                    declared_yield_tonnes=crop_season.declared_yield_tonnes,
                    verified_yield_tonnes=crop_season.verified_yield_tonnes,
                    organic=crop_season.organic,
                    soil_cover=crop_season.soil_cover,
                    public_land_conflict=parcel.public_land_conflict,
                    crop_label_confidence=confidence,
                ),
                self.rules,
            )
            line_items.append(decision)
            risk_flags.update(decision.hold_reasons)

        gross = money(sum((decision.gross_amount_eur for decision in line_items), Decimal("0")))
        reductions = money(sum((decision.reductions_eur for decision in line_items), Decimal("0")))
        final = money(sum((decision.final_amount_eur for decision in line_items), Decimal("0")))
        offset_ratio = Decimal(str(self.rules.get("debt_management", {}).get("subsidy_offset_ratio", "0")))
        debt_offset = calculate_debt_offset(final, self.repository.list_debts(farmer_id), offset_ratio)
        return SubsidyClaimDecision(
            farmer_id=farmer_id,
            claim_year=claim_year,
            line_items=tuple(line_items),
            gross_amount_eur=gross,
            reductions_eur=reductions,
            final_amount_eur=final,
            debt_offset=debt_offset,
            risk_flags=tuple(sorted(risk_flags)),
        )

    def declare_crisis_event(
        self,
        event_type: str,
        name: str,
        claim_year: int,
        event_start: str,
        affected_bbox: tuple[Decimal, Decimal, Decimal, Decimal],
        event_end: str | None = None,
    ) -> CrisisEvent:
        """Declare a geofenced crisis event for compensation workflows."""

        min_lat, min_lon, max_lat, max_lon = affected_bbox
        return self.repository.add_crisis_event(
            CrisisEvent(
                event_type=event_type,
                name=name,
                claim_year=claim_year,
                event_start=event_start,
                affected_min_lat=min_lat,
                affected_min_lon=min_lon,
                affected_max_lat=max_lat,
                affected_max_lon=max_lon,
                policy_rule_version=str(self.rules["rule_version"]),
                event_end=event_end,
            )
        )

    def calculate_crisis_compensation(
        self, crisis_event_id: str, crop_season_id: str, damage_percent: Decimal
    ) -> CompensationDecision:
        """Calculate compensation for a crop season affected by a crisis."""

        crisis_event = self.repository.get_crisis_event(crisis_event_id)
        crop_season = self.repository.get_crop_season(crop_season_id)
        parcel = self.repository.get_parcel(crop_season.parcel_id)
        observations = self.repository.list_observations(parcel.parcel_id, crisis_event.claim_year)
        return calculate_compensation(crisis_event, parcel, crop_season, damage_percent, self.rules, observations)

    def annual_farmer_ledger(self, farmer_id: str, claim_year: int) -> AnnualFarmerLedger:
        """Build the annual ledger view requested for per-capita public administration."""

        crop_seasons = self.repository.list_crop_seasons(farmer_id=farmer_id, claim_year=claim_year)
        declared = sum((crop.declared_yield_tonnes or Decimal("0") for crop in crop_seasons), Decimal("0"))
        verified = sum((crop.verified_yield_tonnes or Decimal("0") for crop in crop_seasons), Decimal("0"))
        sales = [sale for crop in crop_seasons for sale in self.repository.list_first_sales_for_crop(crop.crop_season_id)]
        sale_taxes = [calculate_first_sale_tax(sale) for sale in sales]
        subsidy = self.calculate_annual_subsidy_claim(farmer_id, claim_year)
        open_debt = sum((debt.outstanding_eur for debt in self.repository.list_debts(farmer_id) if debt.status == "open"), Decimal("0"))
        risk_flags = set(subsidy.risk_flags)
        if verified and declared and verified < declared * Decimal("0.8"):
            risk_flags.add("declared_production_above_verified_baseline")
        return AnnualFarmerLedger(
            farmer_id=farmer_id,
            claim_year=claim_year,
            declared_production_tonnes=declared,
            verified_production_tonnes=verified,
            first_sale_revenue_eur=money(sum((tax.gross_amount_eur for tax in sale_taxes), Decimal("0"))),
            first_sale_tax_eur=money(sum((tax.tax_amount_eur for tax in sale_taxes), Decimal("0"))),
            subsidy_gross_eur=subsidy.gross_amount_eur,
            subsidy_final_eur=subsidy.final_amount_eur,
            compensation_final_eur=Decimal("0.00"),
            open_debt_eur=money(open_debt),
            net_public_support_eur=money(subsidy.debt_offset.disbursable_eur),
            risk_flags=tuple(sorted(risk_flags)),
        )

    def _best_crop_confidence(self, observations: list[RemoteSensingObservation]) -> Decimal | None:
        crop_observations = [observation.confidence for observation in observations if observation.observation_type == "crop_classification"]
        if not crop_observations:
            return None
        return max(crop_observations)
