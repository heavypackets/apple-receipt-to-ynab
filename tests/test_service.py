import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import apple_receipt_to_ynab.service as service
import pytest
from apple_receipt_to_ynab.gmail_client import GmailMessage
from apple_receipt_to_ynab.models import (
    AppConfig,
    EmailConfig,
    FallbackMapping,
    MappingConfig,
    MappingDefaults,
    MatchedSubscription,
    ParsedReceipt,
    RuntimeConfig,
    SplitLine,
    SubscriptionLine,
    YnabConfig,
)
from apple_receipt_to_ynab.service import _resolve_ynab_flag_color, process_receipt
from apple_receipt_to_ynab.ynab import YnabApiError


def _build_runtime_config(log_path: Path | None = None, defaults_flag_color: str | None = None) -> RuntimeConfig:
    mappings = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="acct-1", ynab_flag_color=defaults_flag_color),
        rules=[],
        fallback=None,
    )
    return RuntimeConfig(
        version=1,
        ynab=YnabConfig(
            api_token="token-1",
            budget_id="budget-1",
            api_url="https://ynab.test/v1",
            lookback_days=7,
        ),
        app=AppConfig(mode="local", log_path=log_path),
        email=EmailConfig(),
        mappings=mappings,
    )


def _build_parsed_receipt(tmp_path: Path) -> ParsedReceipt:
    return ParsedReceipt(
        source_pdf=tmp_path / "receipt.eml",
        receipt_id="RID-1",
        receipt_date=date(2026, 2, 16),
        currency="USD",
        subscriptions=[SubscriptionLine(description="Apple Music", base_amount=Decimal("10.00"))],
        tax_total=Decimal("0.80"),
        grand_total=Decimal("10.80"),
        raw_text="",
    )


def _build_matched() -> list[MatchedSubscription]:
    return [
        MatchedSubscription(
            source_description="Apple Music",
            base_amount=Decimal("10.00"),
            ynab_category_id="cat-1",
            ynab_payee_id=None,
            ynab_payee_name="Apple Music",
            mapping_rule_id="apple_music",
        )
    ]


def _build_split_lines() -> list[SplitLine]:
    return [
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


def test_resolve_ynab_flag_color_returns_color_when_fallback_was_used() -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="acct", ynab_flag_color="blue"),
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
        defaults=MappingDefaults(ynab_account_id="acct", ynab_flag_color="blue"),
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

    assert _resolve_ynab_flag_color(config, matched) == "blue"


def test_resolve_ynab_flag_color_uses_default_when_fallback_used_without_fallback_color() -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="acct", ynab_flag_color="blue"),
        rules=[],
        fallback=FallbackMapping(enabled=True, ynab_category_id="cat"),
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

    assert _resolve_ynab_flag_color(config, matched) == "blue"


def test_process_receipt_posts_once_when_not_dry_run(tmp_path: Path, monkeypatch) -> None:
    parsed = _build_parsed_receipt(tmp_path)
    matched = _build_matched()
    split_lines = _build_split_lines()
    runtime_config = _build_runtime_config(log_path=tmp_path / "run.log")
    post_calls: list[dict[str, object]] = []

    monkeypatch.setattr(service, "load_config", lambda _path: runtime_config)
    monkeypatch.setattr(service, "parse_receipt_file", lambda _path, default_currency: parsed)
    monkeypatch.setattr(service, "match_subscriptions", lambda _subs, _cfg: matched)
    monkeypatch.setattr(service, "build_split_lines", lambda _matched, _tax: split_lines)
    monkeypatch.setattr(service, "_list_ynab_transactions_by_account", lambda **_: [])

    def _fake_post(
        ynab_budget_id: str,
        ynab_api_token: str,
        ynab_api_url: str,
        transaction: dict[str, object],
    ) -> str:
        post_calls.append(
            {
                "budget_id": ynab_budget_id,
                "api_token": ynab_api_token,
                "api_url": ynab_api_url,
                "transaction": dict(transaction),
            }
        )
        return "tx-1"

    monkeypatch.setattr(service, "_post_ynab_transaction", _fake_post)
    monkeypatch.setattr(service, "append_log_event", lambda *_args, **_kwargs: None)
    result = process_receipt(
        receipt_path=tmp_path / "receipt.eml",
        config_path=tmp_path / "config.yaml",
        dry_run=False,
    )

    assert result.status == "created"
    assert result.transaction_id == "tx-1"
    assert len(post_calls) == 1
    assert post_calls[0]["budget_id"] == "budget-1"
    assert post_calls[0]["api_token"] == "token-1"
    assert post_calls[0]["api_url"] == "https://ynab.test/v1"
    assert "import_id" not in post_calls[0]["transaction"]
    assert post_calls[0]["transaction"]["memo"] == "Receipt: RID-1"


def test_process_receipt_409_raises_ynab_api_error(tmp_path: Path, monkeypatch) -> None:
    parsed = _build_parsed_receipt(tmp_path)
    matched = _build_matched()
    split_lines = _build_split_lines()
    runtime_config = _build_runtime_config(log_path=tmp_path / "run.log")
    call_count = {"value": 0}

    monkeypatch.setattr(service, "load_config", lambda _path: runtime_config)
    monkeypatch.setattr(service, "parse_receipt_file", lambda _path, default_currency: parsed)
    monkeypatch.setattr(service, "match_subscriptions", lambda _subs, _cfg: matched)
    monkeypatch.setattr(service, "build_split_lines", lambda _matched, _tax: split_lines)
    monkeypatch.setattr(service, "_list_ynab_transactions_by_account", lambda **_: [])

    def _raise_409(
        ynab_budget_id: str,
        ynab_api_token: str,
        ynab_api_url: str,
        transaction: dict[str, object],
    ) -> str:
        call_count["value"] += 1
        raise YnabApiError("YNAB API 409: duplicate")

    monkeypatch.setattr(service, "_post_ynab_transaction", _raise_409)
    monkeypatch.setattr(service, "append_log_event", lambda *_args, **_kwargs: None)

    with pytest.raises(YnabApiError, match="409"):
        process_receipt(
            receipt_path=tmp_path / "receipt.eml",
            config_path=tmp_path / "config.yaml",
            dry_run=False,
        )

    assert call_count["value"] == 1


def test_process_receipt_dry_run_logs_to_stdout_when_log_path_missing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    parsed = _build_parsed_receipt(tmp_path)
    matched = _build_matched()
    split_lines = _build_split_lines()
    runtime_config = _build_runtime_config(log_path=None)

    monkeypatch.setattr(service, "load_config", lambda _path: runtime_config)
    monkeypatch.setattr(service, "parse_receipt_file", lambda _path, default_currency: parsed)
    monkeypatch.setattr(service, "match_subscriptions", lambda _subs, _cfg: matched)
    monkeypatch.setattr(service, "build_split_lines", lambda _matched, _tax: split_lines)

    result = process_receipt(
        receipt_path=tmp_path / "receipt.eml",
        config_path=tmp_path / "config.yaml",
        dry_run=True,
    )

    output = capsys.readouterr().out
    assert result.status == "DRY_RUN"
    event = json.loads(output.strip())
    assert event["mode"] == "dry_run"
    assert event["status"] == "dry_run"
    assert event["message"] == "Dry run completed. No transaction posted."


def test_process_receipt_dry_run_writes_file_and_echoes_to_stdout(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    parsed = _build_parsed_receipt(tmp_path)
    matched = _build_matched()
    split_lines = _build_split_lines()
    log_path = tmp_path / "run.log"
    runtime_config = _build_runtime_config(log_path=log_path)

    monkeypatch.setattr(service, "load_config", lambda _path: runtime_config)
    monkeypatch.setattr(service, "parse_receipt_file", lambda _path, default_currency: parsed)
    monkeypatch.setattr(service, "match_subscriptions", lambda _subs, _cfg: matched)
    monkeypatch.setattr(service, "build_split_lines", lambda _matched, _tax: split_lines)

    process_receipt(
        receipt_path=tmp_path / "receipt.eml",
        config_path=tmp_path / "config.yaml",
        dry_run=True,
    )

    output = capsys.readouterr().out
    log_text = log_path.read_text(encoding="utf-8")
    output_event = json.loads(output.strip())
    file_event = json.loads(log_text.strip())
    assert output_event["mode"] == "dry_run"
    assert output_event["event_name"] == "receipt_processed"
    assert file_event == output_event


def test_process_receipt_skips_duplicate_using_ynab_lookup(tmp_path: Path, monkeypatch) -> None:
    parsed = _build_parsed_receipt(tmp_path)
    matched = _build_matched()
    split_lines = _build_split_lines()
    runtime_config = _build_runtime_config(log_path=tmp_path / "run.log")

    monkeypatch.setattr(service, "load_config", lambda _path: runtime_config)
    monkeypatch.setattr(service, "parse_receipt_file", lambda _path, default_currency: parsed)
    monkeypatch.setattr(service, "match_subscriptions", lambda _subs, _cfg: matched)
    monkeypatch.setattr(service, "build_split_lines", lambda _matched, _tax: split_lines)
    monkeypatch.setattr(
        service,
        "_list_ynab_transactions_by_account",
        lambda **_: [
            {
                "id": "existing-tx-1",
                "account_id": "acct-1",
                "date": "2026-02-16",
                "amount": -10800,
                "memo": "Receipt: RID-1",
            }
        ],
    )
    monkeypatch.setattr(service, "append_log_event", lambda *_args, **_kwargs: None)

    post_calls = {"value": 0}

    def _fake_post(**_: object) -> str:
        post_calls["value"] += 1
        return "tx-should-not-post"

    monkeypatch.setattr(service, "_post_ynab_transaction", _fake_post)

    result = process_receipt(
        receipt_path=tmp_path / "receipt.eml",
        config_path=tmp_path / "config.yaml",
        dry_run=False,
    )

    assert result.status == "duplicate"
    assert result.transaction_id == "existing-tx-1"
    assert post_calls["value"] == 0


def test_process_receipt_gmail_mode_processes_batch(tmp_path: Path, monkeypatch) -> None:
    parsed = _build_parsed_receipt(tmp_path)
    matched = _build_matched()
    split_lines = _build_split_lines()
    runtime_config = _build_runtime_config(log_path=tmp_path / "run.log")
    runtime_config = RuntimeConfig(
        version=runtime_config.version,
        ynab=runtime_config.ynab,
        app=AppConfig(mode="email", log_path=runtime_config.app.log_path),
        email=EmailConfig(
            service_account_key_path=tmp_path / "gmail-sa.json",
            delegated_user_email="robot@example.com",
        ),
        mappings=runtime_config.mappings,
    )

    monkeypatch.setattr(service, "load_config", lambda _path: runtime_config)
    monkeypatch.setattr(
        service,
        "fetch_gmail_messages",
        lambda _cfg: [GmailMessage(message_id="mid-1", raw_bytes=b"raw"), GmailMessage(message_id="mid-2", raw_bytes=b"raw2")],
    )
    monkeypatch.setattr(service, "_parse_gmail_message", lambda _msg, default_currency: parsed)
    monkeypatch.setattr(service, "match_subscriptions", lambda _subs, _cfg: matched)
    monkeypatch.setattr(service, "build_split_lines", lambda _matched, _tax: split_lines)
    monkeypatch.setattr(service, "_list_ynab_transactions_by_account", lambda **_: [])
    monkeypatch.setattr(service, "append_log_event", lambda *_args, **_kwargs: None)

    post_calls = {"value": 0}

    def _fake_post(**_: object) -> str:
        post_calls["value"] += 1
        return f"tx-{post_calls['value']}"

    monkeypatch.setattr(service, "_post_ynab_transaction", _fake_post)

    result = process_receipt(
        receipt_path=None,
        config_path=tmp_path / "config.yaml",
        dry_run=False,
    )

    assert result.receipt_id == "GMAIL-BATCH"
    assert result.processed_count == 2
    assert result.created_count == 1
    assert result.duplicate_count == 1
    assert post_calls["value"] == 1
