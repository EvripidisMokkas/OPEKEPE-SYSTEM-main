"""Deterministic subsidy eligibility and payment calculation reference engine."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

CENT = Decimal("0.01")


@dataclass(frozen=True)
class ParcelFacts:
    """Facts required to calculate a parcel subsidy line."""

    parcel_hectares: Decimal
    production_type: str
    declared_yield_tonnes: Decimal | None = None
    verified_yield_tonnes: Decimal | None = None
    organic: bool = False
    soil_cover: bool = False
    public_land_conflict: bool = False
    crop_label_confidence: Decimal | None = None


@dataclass(frozen=True)
class SubsidyDecision:
    """Explainable payment decision for one parcel and production type."""

    rule_version: str
    production_type: str
    eligible_hectares: Decimal
    rate_eur_per_ha: Decimal
    gross_amount_eur: Decimal
    reductions_eur: Decimal
    final_amount_eur: Decimal
    hold_reasons: tuple[str, ...]


def money(value: Decimal) -> Decimal:
    """Round a decimal value to cents."""

    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def load_rules(path: str | Path) -> dict[str, Any]:
    """Load a JSON rules configuration file."""

    with Path(path).open("r", encoding="utf-8") as rules_file:
        return json.load(rules_file)


def decimal_from_rule(value: Any) -> Decimal:
    """Convert numeric JSON values to Decimal without binary float artifacts."""

    return Decimal(str(value))


def calculate_subsidy(facts: ParcelFacts, rules: dict[str, Any]) -> SubsidyDecision:
    """Calculate a transparent per-parcel subsidy decision."""

    base_support = rules["base_income_support"]
    production_rates = base_support.get("production_type_rates_eur_per_ha", {})
    base_rate = decimal_from_rule(
        production_rates.get(facts.production_type, base_support["default_rate_eur_per_ha"])
    )

    eco_bonus = Decimal("0")
    eco_rules = rules.get("eco_scheme_bonus", {})
    if facts.organic:
        eco_bonus += decimal_from_rule(eco_rules.get("organic_bonus_eur_per_ha", 0))
    if facts.soil_cover:
        eco_bonus += decimal_from_rule(eco_rules.get("soil_cover_bonus_eur_per_ha", 0))

    rate = base_rate + eco_bonus
    gross_amount = money(facts.parcel_hectares * rate)
    hold_reasons = list(evaluate_holds(facts, rules))
    reductions = gross_amount if hold_reasons else Decimal("0.00")
    final_amount = money(gross_amount - reductions)

    return SubsidyDecision(
        rule_version=str(rules["rule_version"]),
        production_type=facts.production_type,
        eligible_hectares=facts.parcel_hectares,
        rate_eur_per_ha=rate,
        gross_amount_eur=gross_amount,
        reductions_eur=money(reductions),
        final_amount_eur=final_amount,
        hold_reasons=tuple(hold_reasons),
    )


def evaluate_holds(facts: ParcelFacts, rules: dict[str, Any]) -> tuple[str, ...]:
    """Return payment hold reasons based on configured controls."""

    holds: list[str] = []
    risk_rules = rules.get("risk_holds", {})

    if facts.public_land_conflict and risk_rules.get("public_land_conflict", False):
        holds.append("public_land_conflict")

    confidence_threshold = risk_rules.get("crop_label_confidence_below")
    if confidence_threshold is not None and facts.crop_label_confidence is not None:
        if facts.crop_label_confidence < decimal_from_rule(confidence_threshold):
            holds.append("low_crop_label_confidence")

    if facts.declared_yield_tonnes is not None and facts.verified_yield_tonnes is not None:
        if facts.declared_yield_tonnes > 0:
            variance = abs(facts.declared_yield_tonnes - facts.verified_yield_tonnes) / facts.declared_yield_tonnes
            variance_limit = decimal_from_rule(risk_rules.get("yield_variance_above_ratio", 1))
            if variance > variance_limit:
                holds.append("yield_variance_exceeds_tolerance")

    return tuple(holds)


def decision_to_dict(decision: SubsidyDecision) -> dict[str, Any]:
    """Serialize a subsidy decision for API or CLI output."""

    return {
        "rule_version": decision.rule_version,
        "production_type": decision.production_type,
        "eligible_hectares": str(decision.eligible_hectares),
        "rate_eur_per_ha": str(decision.rate_eur_per_ha),
        "gross_amount_eur": str(decision.gross_amount_eur),
        "reductions_eur": str(decision.reductions_eur),
        "final_amount_eur": str(decision.final_amount_eur),
        "hold_reasons": list(decision.hold_reasons),
    }


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(description="Calculate a reference agricultural subsidy line item.")
    parser.add_argument("--rules", required=True, help="Path to a JSON rules file.")
    parser.add_argument("--parcel-hectares", required=True, type=Decimal, help="Eligible parcel area in hectares.")
    parser.add_argument("--production-type", required=True, help="Production type code, for example olives.")
    parser.add_argument("--declared-yield-tonnes", type=Decimal, default=None)
    parser.add_argument("--verified-yield-tonnes", type=Decimal, default=None)
    parser.add_argument("--organic", action="store_true")
    parser.add_argument("--soil-cover", action="store_true")
    parser.add_argument("--public-land-conflict", action="store_true")
    parser.add_argument("--crop-label-confidence", type=Decimal, default=None)
    return parser


def main() -> None:
    """Run the command-line subsidy calculator."""

    args = build_parser().parse_args()
    facts = ParcelFacts(
        parcel_hectares=args.parcel_hectares,
        production_type=args.production_type,
        declared_yield_tonnes=args.declared_yield_tonnes,
        verified_yield_tonnes=args.verified_yield_tonnes,
        organic=args.organic,
        soil_cover=args.soil_cover,
        public_land_conflict=args.public_land_conflict,
        crop_label_confidence=args.crop_label_confidence,
    )
    decision = calculate_subsidy(facts, load_rules(args.rules))
    print(json.dumps(decision_to_dict(decision), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
