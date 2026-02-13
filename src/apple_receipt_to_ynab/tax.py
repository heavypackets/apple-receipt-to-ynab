from __future__ import annotations

from decimal import Decimal

from apple_receipt_to_ynab.models import MatchedSubscription, SplitLine
from apple_receipt_to_ynab.utils import dollars_to_milliunits


class TaxAllocationError(ValueError):
    pass


def build_split_lines(subscriptions: list[MatchedSubscription], tax_total: Decimal) -> list[SplitLine]:
    if not subscriptions:
        raise TaxAllocationError("No subscriptions found for split generation.")

    base_milliunits = [dollars_to_milliunits(sub.base_amount) for sub in subscriptions]
    tax_milliunits = dollars_to_milliunits(tax_total)
    allocated_tax = allocate_proportional_milliunits(base_milliunits, tax_milliunits)

    split_lines: list[SplitLine] = []
    for sub, base, tax in zip(subscriptions, base_milliunits, allocated_tax):
        split_lines.append(
            SplitLine(
                friendly_name=sub.friendly_name,
                source_description=sub.source_description,
                base_milliunits=base,
                tax_milliunits=tax,
                total_milliunits=base + tax,
                ynab_category_id=sub.ynab_category_id,
                ynab_payee_id=sub.ynab_payee_id,
                ynab_payee_name=sub.ynab_payee_name,
                memo=sub.memo,
                mapping_rule_id=sub.mapping_rule_id,
            )
        )
    return split_lines


def allocate_proportional_milliunits(base_amounts: list[int], tax_total: int) -> list[int]:
    if not base_amounts:
        raise TaxAllocationError("Cannot allocate tax across zero line items.")
    if any(base < 0 for base in base_amounts):
        raise TaxAllocationError("Base amounts must be non-negative milliunits.")

    total_base = sum(base_amounts)
    if total_base == 0:
        if tax_total == 0:
            return [0] * len(base_amounts)
        raise TaxAllocationError("Cannot allocate non-zero tax when total base is zero.")

    sign = 1 if tax_total >= 0 else -1
    remaining = abs(tax_total)

    floor_allocations: list[int] = []
    remainders: list[tuple[int, int]] = []
    for idx, base in enumerate(base_amounts):
        numerator = remaining * base
        floor_value = numerator // total_base
        floor_allocations.append(floor_value)
        remainders.append((numerator % total_base, idx))

    remainder_units = remaining - sum(floor_allocations)
    for _, idx in sorted(remainders, key=lambda item: item[0], reverse=True)[:remainder_units]:
        floor_allocations[idx] += 1

    return [value * sign for value in floor_allocations]
