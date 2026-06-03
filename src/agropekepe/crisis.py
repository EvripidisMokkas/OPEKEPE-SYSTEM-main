"""Crisis event and compensation calculations."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from agropekepe.eligibility import decimal_from_rule, money
from agropekepe.geo import point_in_bbox
from agropekepe.models import CompensationDecision, CrisisEvent, CropSeason, Parcel, RemoteSensingObservation


def calculate_compensation(
    crisis_event: CrisisEvent,
    parcel: Parcel,
    crop_season: CropSeason,
    damage_percent: Decimal,
    rules: dict[str, Any],
    observations: list[RemoteSensingObservation] | None = None,
    previous_compensation_eur: Decimal = Decimal("0"),
) -> CompensationDecision:
    """Calculate crisis compensation for an affected parcel and crop season."""

    observations = observations or []
    crisis_rules = rules.get("crisis_compensation", {})
    rate = decimal_from_rule(crisis_rules.get("default_rate_eur_per_ha", 0))
    annual_cap = decimal_from_rule(crisis_rules.get("annual_cap_eur_per_farmer", 0))
    maximum_damage_percent = decimal_from_rule(crisis_rules.get("maximum_damage_percent", 100))

    hold_reasons: list[str] = []
    if not point_in_bbox(
        parcel.centroid_lat,
        parcel.centroid_lon,
        crisis_event.affected_min_lat,
        crisis_event.affected_min_lon,
        crisis_event.affected_max_lat,
        crisis_event.affected_max_lon,
    ):
        hold_reasons.append("parcel_outside_crisis_geofence")

    if damage_percent <= 0:
        hold_reasons.append("damage_percent_must_be_positive")
    if damage_percent > maximum_damage_percent:
        hold_reasons.append("damage_percent_above_policy_maximum")

    relevant_observations = [
        observation
        for observation in observations
        if observation.observation_type in {crisis_event.event_type, "drought", "flood", "burn", "weather_alert"}
    ]
    if not relevant_observations:
        hold_reasons.append("missing_remote_or_weather_evidence")

    affected_area = min(parcel.eligible_area_ha, crop_season.labelled_area_ha)
    calculated = money(affected_area * rate * (damage_percent / Decimal("100")))
    remaining_cap = max(annual_cap - previous_compensation_eur, Decimal("0")) if annual_cap > 0 else calculated
    final = Decimal("0.00") if hold_reasons else min(calculated, remaining_cap)

    return CompensationDecision(
        crisis_event_id=crisis_event.crisis_event_id,
        farmer_id=crop_season.farmer_id,
        parcel_id=parcel.parcel_id,
        production_type=crop_season.production_type,
        affected_area_ha=affected_area,
        damage_percent=damage_percent,
        calculated_amount_eur=calculated,
        final_amount_eur=money(final),
        hold_reasons=tuple(hold_reasons),
        evidence={
            "crisis_event_type": crisis_event.event_type,
            "observation_ids": [observation.observation_id for observation in relevant_observations],
            "policy_rule_version": crisis_event.policy_rule_version,
        },
    )
