from datetime import date
from decimal import Decimal
from pathlib import Path

import apple_receipt_to_ynab.service as service
from apple_receipt_to_ynab.models import (
    FallbackMapping,
    MatchedSubscription,
    MappingConfig,
    MappingDefaults,
    ParsedReceipt,
    SplitLine,
    SubscriptionLine,
)
from apple_receipt_to_ynab.service import _generate_reimport_receipt_id, _resolve_flag_color, process_receipt
from apple_receipt_to_ynab.ynab import build_import_id


def test_resolve_flag_color_returns_color_when_fallback_was_used() -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="acct"),
        rules=[],
        fallback=FallbackMapping(enabled=True, ynab_category_id="cat", flag_color="yellow"),
    )
    matched = [
        MatchedSubscription(
            source_description="Unknown App",
            base_amount=Decimal("1.00"),
            ynab_category_id="cat",
            ynab_payee_id=None,
            ynab_payee_name="Apple",
            memo=None,
            mapping_rule_id="fallback",
        )
    ]

    assert _resolve_flag_color(config, matched) == "yellow"


def test_resolve_flag_color_ignores_mapped_only_transactions() -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="acct"),
        rules=[],
        fallback=FallbackMapping(enabled=True, ynab_category_id="cat", flag_color="yellow"),
    )
    matched = [
        MatchedSubscription(
            source_description="Apple Music",
            base_amount=Decimal("1.00"),
            ynab_category_id="cat",
            ynab_payee_id=None,
            ynab_payee_name="Apple Music",
            memo=None,
            mapping_rule_id="apple_music",
        )
    ]

    assert _resolve_flag_color(config, matched) is None


def test_generate_reimport_receipt_id_uses_pound_and_two_digits(monkeypatch) -> None:
    monkeypatch.setattr(service.random, "randint", lambda _a, _b: 7)
    value = _generate_reimport_receipt_id("MSD3TZ09X1", attempted_ids=set())
    assert value == "MSD3TZ09X1#07"


def test_process_receipt_retries_duplicate_when_reimport_enabled(tmp_path: Path, monkeypatch) -> None:
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
            memo=None,
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
            memo=None,
            mapping_rule_id="apple_music",
        )
    ]
    transactions: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            self.api_token = api_token

        def create_transaction(self, budget_id: str, transaction: dict[str, object]) -> tuple[str, dict[str, object]]:
            transactions.append(dict(transaction))
            if len(transactions) == 1:
                return "duplicate-noop", {}
            return "created", {"data": {"transaction": {"id": "tx-1"}}}

        def close(self) -> None:
            return None

    monkeypatch.setattr(service, "load_mapping_config", lambda _path: config)
    monkeypatch.setattr(service, "parse_receipt_file", lambda _path, default_currency: parsed)
    monkeypatch.setattr(service, "match_subscriptions", lambda _subs, _cfg: matched)
    monkeypatch.setattr(service, "build_split_lines", lambda _matched, _tax: split_lines)
    monkeypatch.setattr(service, "YnabClient", FakeClient)
    monkeypatch.setattr(service, "append_log_block", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service.random, "randint", lambda _a, _b: 7)

    result = process_receipt(
        receipt_path=tmp_path / "receipt.eml",
        config_path=tmp_path / "mappings.yml",
        log_path=tmp_path / "run.log",
        ynab_budget_id="budget-1",
        ynab_api_token="token-1",
        dry_run=False,
        reimport=True,
    )

    assert result.status == "created"
    assert result.transaction_id == "tx-1"
    assert len(transactions) == 2
    assert transactions[0]["import_id"] != transactions[1]["import_id"]
    assert transactions[1]["import_id"] == build_import_id("RID-1#07", date(2026, 2, 16), 10800)
    assert result.import_id == transactions[1]["import_id"]


def test_process_receipt_duplicate_without_reimport_stays_noop(tmp_path: Path, monkeypatch) -> None:
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
            memo=None,
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
            memo=None,
            mapping_rule_id="apple_music",
        )
    ]
    call_count = {"value": 0}

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            self.api_token = api_token

        def create_transaction(self, budget_id: str, transaction: dict[str, object]) -> tuple[str, dict[str, object]]:
            call_count["value"] += 1
            return "duplicate-noop", {}

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
        reimport=False,
    )

    assert call_count["value"] == 1
    assert result.status == "duplicate-noop"
