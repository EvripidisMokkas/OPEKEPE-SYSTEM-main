"""Domain models for the AgroLedger application."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any
from uuid import uuid4


def new_id() -> str:
    """Return a stable string UUID for persisted domain entities."""

    return str(uuid4())


@dataclass(frozen=True)
class Farmer:
    """Verified agricultural beneficiary."""

    tax_identifier: str
    legal_name: str
    farmer_type: str = "individual"
    active_farmer: bool = True
    farmer_id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class Parcel:
    """Versioned agricultural land parcel and rights declaration."""

    farmer_id: str
    cadastral_reference: str
    right_type: str
    declared_area_ha: Decimal
    measured_area_ha: Decimal
    eligible_area_ha: Decimal
    centroid_lat: Decimal
    centroid_lon: Decimal
    geometry_geojson: dict[str, Any]
    public_land_conflict: bool = False
    protected_area_conflict: bool = False
    parcel_id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class CropSeason:
    """Annual production label for a parcel or sub-parcel."""

    parcel_id: str
    farmer_id: str
    claim_year: int
    production_type: str
    labelled_area_ha: Decimal
    organic: bool = False
    soil_cover: bool = False
    irrigation_status: str = "unknown"
    declared_yield_tonnes: Decimal | None = None
    verified_yield_tonnes: Decimal | None = None
    crop_label_confidence: Decimal | None = None
    crop_season_id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class RemoteSensingObservation:
    """Satellite, map, weather, or inspection evidence attached to a parcel."""

    parcel_id: str
    claim_year: int
    provider: str
    observation_type: str
    confidence: Decimal
    result: dict[str, Any]
    evidence_uri: str | None = None
    observation_id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class FirstSaleRecord:
    """First market sale that creates financial and tax reconciliation evidence."""

    crop_season_id: str
    invoice_number: str
    buyer_tax_identifier: str
    sale_date: str
    product_type: str
    quantity_tonnes: Decimal
    unit_price_eur: Decimal
    tax_rate: Decimal
    mydata_mark: str | None = None
    first_sale_id: str = field(default_factory=new_id)

    @property
    def gross_amount_eur(self) -> Decimal:
        """Return gross invoice amount before first-sale tax."""

        return self.quantity_tonnes * self.unit_price_eur

    @property
    def tax_amount_eur(self) -> Decimal:
        """Return tax due on first market sale."""

        return self.gross_amount_eur * self.tax_rate


@dataclass(frozen=True)
class DebtAccount:
    """Debt or recovery account that can legally offset payments."""

    farmer_id: str
    debt_type: str
    outstanding_eur: Decimal
    status: str = "open"
    debt_account_id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class CrisisEvent:
    """Government or authority-declared crisis event."""

    event_type: str
    name: str
    claim_year: int
    event_start: str
    affected_min_lat: Decimal
    affected_min_lon: Decimal
    affected_max_lat: Decimal
    affected_max_lon: Decimal
    policy_rule_version: str
    event_end: str | None = None
    crisis_event_id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class CompensationDecision:
    """Explainable crisis compensation result."""

    crisis_event_id: str
    farmer_id: str
    parcel_id: str
    production_type: str
    affected_area_ha: Decimal
    damage_percent: Decimal
    calculated_amount_eur: Decimal
    final_amount_eur: Decimal
    hold_reasons: tuple[str, ...]
    evidence: dict[str, Any]


@dataclass(frozen=True)
class AnnualFarmerLedger:
    """Aggregated annual farmer position across production, sales, support, taxes, and debt."""

    farmer_id: str
    claim_year: int
    declared_production_tonnes: Decimal
    verified_production_tonnes: Decimal
    first_sale_revenue_eur: Decimal
    first_sale_tax_eur: Decimal
    subsidy_gross_eur: Decimal
    subsidy_final_eur: Decimal
    compensation_final_eur: Decimal
    open_debt_eur: Decimal
    net_public_support_eur: Decimal
    risk_flags: tuple[str, ...]


def dataclass_to_json_dict(value: Any) -> dict[str, Any]:
    """Serialize dataclass values with Decimals converted to strings."""

    def normalize(item: Any) -> Any:
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, tuple):
            return [normalize(element) for element in item]
        if isinstance(item, list):
            return [normalize(element) for element in item]
        if isinstance(item, dict):
            return {key: normalize(element) for key, element in item.items()}
        return item

    return normalize(asdict(value))
