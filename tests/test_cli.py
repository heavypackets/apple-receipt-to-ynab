import sys
from decimal import Decimal
from pathlib import Path

from apple_receipt_to_ynab import cli
from apple_receipt_to_ynab.credentials import resolve_secret
from apple_receipt_to_ynab.models import SubscriptionLine
from apple_receipt_to_ynab.service import ProcessResult


def test_resolve_secret_prefers_cli_value(monkeypatch) -> None:
    monkeypatch.setenv("YNAB_API_TOKEN", "env-token")
    value = resolve_secret("cli-token", "YNAB_API_TOKEN", {"YNAB_API_TOKEN": "dotenv-token"})
    assert value == "cli-token"


def test_resolve_secret_prefers_environment_over_dotenv(monkeypatch) -> None:
    monkeypatch.setenv("YNAB_API_TOKEN", "env-token")
    value = resolve_secret(None, "YNAB_API_TOKEN", {"YNAB_API_TOKEN": "dotenv-token"})
    assert value == "env-token"


def test_resolve_secret_uses_dotenv_fallback(monkeypatch) -> None:
    monkeypatch.delenv("YNAB_API_TOKEN", raising=False)
    value = resolve_secret(None, "YNAB_API_TOKEN", {"YNAB_API_TOKEN": "dotenv-token"})
    assert value == "dotenv-token"


def test_print_dry_run_subscriptions(capsys) -> None:
    cli._print_dry_run_subscriptions(
        (
            SubscriptionLine(description="Apple Music", base_amount=Decimal("10.99")),
            SubscriptionLine(description="iCloud+", base_amount=Decimal("2.99")),
        )
    )
    output = capsys.readouterr().out
    assert "Parsed subscriptions:" in output
    assert "1. Apple Music | 10.99" in output
    assert "2. iCloud+ | 2.99" in output


def test_main_prints_parsed_subscriptions_in_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    config_path = tmp_path / "mappings.yml"
    receipt_path.write_text("", encoding="utf-8")
    config_path.write_text("version: 1\n", encoding="utf-8")

    def _fake_process_receipt(**_: object) -> ProcessResult:
        return ProcessResult(
            status="DRY_RUN",
            message="Dry run completed. No transaction posted.",
            receipt_id="ABC123",
            import_id="apple:importid",
            parent_amount_milliunits=-13980,
            parsed_subscriptions=(
                SubscriptionLine(description="Apple Music", base_amount=Decimal("10.99")),
                SubscriptionLine(description="iCloud+", base_amount=Decimal("2.99")),
            ),
            transaction_id=None,
        )

    monkeypatch.setattr(cli, "process_receipt", _fake_process_receipt)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apple-receipt-to-ynab",
            str(receipt_path),
            "--config",
            str(config_path),
            "--ynab-api-token",
            "token",
            "--ynab-budget-id",
            "budget",
            "--dry-run",
        ],
    )

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Parsed subscriptions:" in output
    assert "1. Apple Music | 10.99" in output
    assert "2. iCloud+ | 2.99" in output
    assert "DRY_RUN: receipt=ABC123" in output
