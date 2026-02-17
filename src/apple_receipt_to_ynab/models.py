from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

MatchType = Literal["exact", "contains", "regex"]
AppMode = Literal["local", "email"]


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
    ynab_flag_color: str | None = None
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
class YnabConfig:
    api_token: str
    budget_id: str
    api_url: str
    lookback_days: int


@dataclass(frozen=True)
class AppConfig:
    mode: AppMode = "local"
    log_path: Path | None = None


@dataclass(frozen=True)
class EmailConfig:
    subject_filter: str = "Your receipt from Apple."
    sender_filter: str = "no_reply@email.apple.com"
    max_age_days: int = 7
    service_account_key_path: Path | None = None
    delegated_user_email: str | None = None
    max_results: int = 10
    query_extra: str | None = None


@dataclass(frozen=True)
class RuntimeConfig:
    version: int
    ynab: YnabConfig
    app: AppConfig
    email: EmailConfig
    mappings: MappingConfig


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
