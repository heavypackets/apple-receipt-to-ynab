from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

MatchType = Literal["exact", "contains", "regex"]


@dataclass(frozen=True)
class SubscriptionLine:
    description: str
    base_amount: Decimal


@dataclass(frozen=True)
class ParsedReceipt:
    source_pdf: Path
    receipt_id: str
    receipt_date: date
    currency: str
    subscriptions: list[SubscriptionLine]
    tax_total: Decimal
    grand_total: Decimal
    raw_text: str


@dataclass(frozen=True)
class MatchSpec:
    type: MatchType
    value: str


@dataclass(frozen=True)
class MappingRule:
    id: str
    enabled: bool
    match: MatchSpec
    ynab_category_id: str
    ynab_payee_name: str
    ynab_payee_id: str | None = None


@dataclass(frozen=True)
class MappingDefaults:
    ynab_account_id: str
    ynab_category_id: str | None = None
    default_currency: str = "USD"


@dataclass(frozen=True)
class FallbackMapping:
    enabled: bool
    ynab_category_id: str | None = None
    ynab_payee_id: str | None = None
    ynab_payee_name: str | None = None
    ynab_flag_color: str | None = None


@dataclass(frozen=True)
class MappingConfig:
    version: int
    defaults: MappingDefaults
    rules: list[MappingRule]
    fallback: FallbackMapping | None = None


@dataclass(frozen=True)
class MatchedSubscription:
    source_description: str
    base_amount: Decimal
    ynab_category_id: str
    ynab_payee_id: str | None
    ynab_payee_name: str
    mapping_rule_id: str


@dataclass(frozen=True)
class SplitLine:
    source_description: str
    base_milliunits: int
    tax_milliunits: int
    total_milliunits: int
    ynab_category_id: str
    ynab_payee_id: str | None
    ynab_payee_name: str
    mapping_rule_id: str
