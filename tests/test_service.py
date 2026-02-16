from datetime import date
from decimal import Decimal
from pathlib import Path

import apple_receipt_to_ynab.service as service
import pytest
from apple_receipt_to_ynab.models import (
    FallbackMapping,
    MatchedSubscription,
    MappingConfig,
    MappingDefaults,
    ParsedReceipt,
    SplitLine,
    SubscriptionLine,
)
from apple_receipt_to_ynab.service import _resolve_ynab_flag_color, process_receipt
from apple_receipt_to_ynab.ynab import YnabApiError


def test_resolve_ynab_flag_color_returns_color_when_fallback_was_used() -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="acct"),
        rules=[],
        fallback=FallbackMapping(enabled=True, ynab_category_id="cat", ynab_flag_color="yellow"),
    )
    matched = [
        MatchedSubscription(
            source_description="Unknown App",
            base_amount=Decimal("1.00"),
            ynab_category_id="cat",
            ynab_payee_id=None,
            ynab_payee_name="Apple",
            mapping_rule_id="fallback",
        )
    ]

    assert _resolve_ynab_flag_color(config, matched) == "yellow"


def test_resolve_ynab_flag_color_ignores_mapped_only_transactions() -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="acct"),
        rules=[],
        fallback=FallbackMapping(enabled=True, ynab_category_id="cat", ynab_flag_color="yellow"),
    )
    matched = [
        MatchedSubscription(
            source_description="Apple Music",
            base_amount=Decimal("1.00"),
            ynab_category_id="cat",
            ynab_payee_id=None,
            ynab_payee_name="Apple Music",
            mapping_rule_id="apple_music",
        )
    ]

    assert _resolve_ynab_flag_color(config, matched) is None


def test_process_receipt_posts_once_when_not_dry_run(tmp_path: Path, monkeypatch) -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="acct-1"),
        rules=[],
        fallback=None,
    )
    parsed = ParsedReceipt(
        source_pdf=tmp_path / "receipt.eml",
        receipt_id="RID-1",
        receipt_date=date(2026, 2, 16),
        currency="USD",
        subscriptions=[SubscriptionLine(description="Apple Music", base_amount=Decimal("10.00"))],
        tax_total=Decimal("0.80"),
        grand_total=Decimal("10.80"),
        raw_text="",
    )
    matched = [
        MatchedSubscription(
            source_description="Apple Music",
            base_amount=Decimal("10.00"),
            ynab_category_id="cat-1",
            ynab_payee_id=None,
            ynab_payee_name="Apple Music",
            mapping_rule_id="apple_music",
        )
    ]
    split_lines = [
        SplitLine(
            source_description="Apple Music",
            base_milliunits=10000,
            tax_milliunits=800,
            total_milliunits=10800,
            ynab_category_id="cat-1",
            ynab_payee_id=None,
            ynab_payee_name="Apple Music",
            mapping_rule_id="apple_music",
        )
    ]
    transactions: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            self.api_token = api_token

        def create_transaction(self, budget_id: str, transaction: dict[str, object]) -> tuple[str, dict[str, object]]:
            transactions.append(dict(transaction))
            return "created", {"data": {"transaction": {"id": "tx-1"}}}

        def close(self) -> None:
            return None

    monkeypatch.setattr(service, "load_mapping_config", lambda _path: config)
    monkeypatch.setattr(service, "parse_receipt_file", lambda _path, default_currency: parsed)
    monkeypatch.setattr(service, "match_subscriptions", lambda _subs, _cfg: matched)
    monkeypatch.setattr(service, "build_split_lines", lambda _matched, _tax: split_lines)
    monkeypatch.setattr(service, "YnabClient", FakeClient)
    monkeypatch.setattr(service, "append_log_block", lambda *_args, **_kwargs: None)
    result = process_receipt(
        receipt_path=tmp_path / "receipt.eml",
        config_path=tmp_path / "mappings.yml",
        log_path=tmp_path / "run.log",
        ynab_budget_id="budget-1",
        ynab_api_token="token-1",
        dry_run=False,
    )

    assert result.status == "created"
    assert result.transaction_id == "tx-1"
    assert len(transactions) == 1
    assert "import_id" not in transactions[0]


def test_process_receipt_409_raises_ynab_api_error(tmp_path: Path, monkeypatch) -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="acct-1"),
        rules=[],
        fallback=None,
    )
    parsed = ParsedReceipt(
        source_pdf=tmp_path / "receipt.eml",
        receipt_id="RID-1",
        receipt_date=date(2026, 2, 16),
        currency="USD",
        subscriptions=[SubscriptionLine(description="Apple Music", base_amount=Decimal("10.00"))],
        tax_total=Decimal("0.80"),
        grand_total=Decimal("10.80"),
        raw_text="",
    )
    matched = [
        MatchedSubscription(
            source_description="Apple Music",
            base_amount=Decimal("10.00"),
            ynab_category_id="cat-1",
            ynab_payee_id=None,
            ynab_payee_name="Apple Music",
            mapping_rule_id="apple_music",
        )
    ]
    split_lines = [
        SplitLine(
            source_description="Apple Music",
            base_milliunits=10000,
            tax_milliunits=800,
            total_milliunits=10800,
            ynab_category_id="cat-1",
            ynab_payee_id=None,
            ynab_payee_name="Apple Music",
            mapping_rule_id="apple_music",
        )
    ]
    call_count = {"value": 0}

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            self.api_token = api_token

        def create_transaction(self, budget_id: str, transaction: dict[str, object]) -> tuple[str, dict[str, object]]:
            call_count["value"] += 1
            raise YnabApiError("YNAB API 409: duplicate")

        def close(self) -> None:
            return None

    monkeypatch.setattr(service, "load_mapping_config", lambda _path: config)
    monkeypatch.setattr(service, "parse_receipt_file", lambda _path, default_currency: parsed)
    monkeypatch.setattr(service, "match_subscriptions", lambda _subs, _cfg: matched)
    monkeypatch.setattr(service, "build_split_lines", lambda _matched, _tax: split_lines)
    monkeypatch.setattr(service, "YnabClient", FakeClient)
    monkeypatch.setattr(service, "append_log_block", lambda *_args, **_kwargs: None)

    with pytest.raises(YnabApiError, match="409"):
        process_receipt(
            receipt_path=tmp_path / "receipt.eml",
            config_path=tmp_path / "mappings.yml",
            log_path=tmp_path / "run.log",
            ynab_budget_id="budget-1",
            ynab_api_token="token-1",
            dry_run=False,
        )

    assert call_count["value"] == 1
