"""Financial, tax, and debt calculations for agricultural records."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from agropekepe.eligibility import money
from agropekepe.models import DebtAccount, FirstSaleRecord


@dataclass(frozen=True)
class TaxDecision:
    """Tax calculation for a first-round agricultural sale."""

    first_sale_id: str
    invoice_number: str
    product_type: str
    gross_amount_eur: Decimal
    tax_rate: Decimal
    tax_amount_eur: Decimal
    net_amount_eur: Decimal


@dataclass(frozen=True)
class DebtOffsetDecision:
    """Legal payment offset decision against outstanding farmer debt."""

    requested_payment_eur: Decimal
    offset_eur: Decimal
    disbursable_eur: Decimal
    debt_account_ids: tuple[str, ...]


def calculate_first_sale_tax(first_sale: FirstSaleRecord) -> TaxDecision:
    """Calculate tax on the first market sale before product transformation."""

    gross = money(first_sale.gross_amount_eur)
    tax = money(first_sale.tax_amount_eur)
    return TaxDecision(
        first_sale_id=first_sale.first_sale_id,
        invoice_number=first_sale.invoice_number,
        product_type=first_sale.product_type,
        gross_amount_eur=gross,
        tax_rate=first_sale.tax_rate,
        tax_amount_eur=tax,
        net_amount_eur=money(gross - tax),
    )


def calculate_debt_offset(payment_eur: Decimal, debts: list[DebtAccount], offset_ratio: Decimal) -> DebtOffsetDecision:
    """Calculate how much of a subsidy or compensation payment can offset debt."""

    eligible_debts = [debt for debt in debts if debt.status in {"open", "offset_pending", "restructured"}]
    total_debt = sum((debt.outstanding_eur for debt in eligible_debts), Decimal("0"))
    maximum_offset = money(payment_eur * offset_ratio)
    offset = min(payment_eur, total_debt, maximum_offset)
    return DebtOffsetDecision(
        requested_payment_eur=money(payment_eur),
        offset_eur=money(offset),
        disbursable_eur=money(payment_eur - offset),
        debt_account_ids=tuple(debt.debt_account_id for debt in eligible_debts if offset > 0),
    )
