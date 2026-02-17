import sys
from decimal import Decimal
from pathlib import Path

import pytest

from apple_receipt_to_ynab import cli
from apple_receipt_to_ynab.matcher import UnmappedSubscriptionError
from apple_receipt_to_ynab.models import SubscriptionLine
from apple_receipt_to_ynab.service import ProcessResult


def test_main_requires_config_yaml_in_working_directory(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    receipt_path.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["apple-receipt-to-ynab", str(receipt_path)])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert "config.yaml" in stderr


def test_main_returns_exit_code_2_for_unmapped_subscription(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    config_path = tmp_path / "config.yaml"
    receipt_path.write_text("", encoding="utf-8")
    config_path.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def _raise_unmapped(**_: object) -> ProcessResult:
        raise UnmappedSubscriptionError("No mapping rule for: Unknown Subscription")

    monkeypatch.setattr(cli, "process_receipt", _raise_unmapped)
    monkeypatch.setattr(sys, "argv", ["apple-receipt-to-ynab", str(receipt_path)])

    exit_code = cli.main()
    stderr = capsys.readouterr().err

    assert exit_code == 2
    assert "exit code 2" in stderr
    assert "Unknown Subscription" in stderr


def test_main_prints_success_summary_only_for_non_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    config_path = tmp_path / "config.yaml"
    receipt_path.write_text("", encoding="utf-8")
    config_path.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def _fake_process_receipt(**_: object) -> ProcessResult:
        return ProcessResult(
            status="created",
            message="Posted transaction tx-1.",
            receipt_id="ABC123",
            parent_amount_milliunits=-13980,
            parsed_subscriptions=(
                SubscriptionLine(description="Apple Music", base_amount=Decimal("10.99")),
            ),
            transaction_id="tx-1",
        )

    monkeypatch.setattr(cli, "process_receipt", _fake_process_receipt)
    monkeypatch.setattr(sys, "argv", ["apple-receipt-to-ynab", str(receipt_path)])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "created: receipt=ABC123 amount_milliunits=-13980 Posted transaction tx-1." in output


def test_main_dry_run_has_no_cli_specific_subscription_output(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    config_path = tmp_path / "config.yaml"
    receipt_path.write_text("", encoding="utf-8")
    config_path.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def _fake_process_receipt(**_: object) -> ProcessResult:
        return ProcessResult(
            status="DRY_RUN",
            message="Dry run completed. No transaction posted.",
            receipt_id="ABC123",
            parent_amount_milliunits=-13980,
            parsed_subscriptions=(
                SubscriptionLine(description="Apple Music", base_amount=Decimal("10.99")),
                SubscriptionLine(description="iCloud+", base_amount=Decimal("2.99")),
            ),
            transaction_id=None,
        )

    monkeypatch.setattr(cli, "process_receipt", _fake_process_receipt)
    monkeypatch.setattr(sys, "argv", ["apple-receipt-to-ynab", str(receipt_path), "--dry-run"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Parsed subscriptions:" not in output
