import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from apple_receipt_to_ynab import cli
from apple_receipt_to_ynab.matcher import UnmappedSubscriptionError
from apple_receipt_to_ynab.models import SubscriptionLine
from apple_receipt_to_ynab.service import ProcessResult


def _prepare_default_config(monkeypatch, tmp_path: Path, mode: str = "local") -> Path:
    home = tmp_path / "home"
    config_path = home / ".asy" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _write_base_config(config_path, mode=mode)
    monkeypatch.setenv("HOME", str(home))
    return config_path


def _write_base_config(path: Path, mode: str = "local") -> None:
    email_block = """
email:
  subject_filter: "Your receipt from Apple."
  sender_filter: "no_reply@email.apple.com"
  max_age_days: 7
  service_account_key_path: "./gmail-sa.json"
  delegated_user_email: "robot@example.com"
  max_results: 10
""" if mode == "email" else ""
    path.write_text(
        f"""
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
  lookback_days: 7
app:
  mode: "{mode}"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: rule1
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
{email_block}
""".strip(),
        encoding="utf-8",
    )


def test_main_errors_when_default_config_is_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    receipt_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["app-store-ynab", str(receipt_path)])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert ".asy/config.yaml" in stderr


def test_main_returns_exit_code_2_for_unmapped_subscription(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    config_path = _prepare_default_config(monkeypatch, tmp_path, mode="local")
    receipt_path.write_text("", encoding="utf-8")

    def _raise_unmapped(**_: object) -> ProcessResult:
        raise UnmappedSubscriptionError("No mapping rule for: Unknown Subscription")

    monkeypatch.setattr(cli, "process_receipt", _raise_unmapped)
    monkeypatch.setattr(sys, "argv", ["app-store-ynab", str(receipt_path)])

    exit_code = cli.main()
    stderr = capsys.readouterr().err

    assert exit_code == 2
    assert "exit code 2" in stderr
    assert "Unknown Subscription" in stderr


def test_main_prints_success_summary_only_for_non_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    config_path = _prepare_default_config(monkeypatch, tmp_path, mode="local")
    receipt_path.write_text("", encoding="utf-8")

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
    monkeypatch.setattr(sys, "argv", ["app-store-ynab", str(receipt_path)])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    payload = json.loads(output.strip())
    assert payload["event_name"] == "cli_process_result"
    assert payload["status"] == "created"
    assert payload["receipt_id"] == "ABC123"
    assert payload["parent_amount_milliunits"] == -13980
    assert payload["message"] == "Posted transaction tx-1."
    assert payload["transaction_id"] == "tx-1"


def test_main_dry_run_has_no_cli_specific_subscription_output(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    config_path = _prepare_default_config(monkeypatch, tmp_path, mode="local")
    receipt_path.write_text("", encoding="utf-8")

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
    monkeypatch.setattr(sys, "argv", ["app-store-ynab", str(receipt_path), "--dry-run"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Parsed subscriptions:" not in output


def test_main_errors_when_local_mode_missing_receipt_path(tmp_path: Path, monkeypatch, capsys) -> None:
    _prepare_default_config(monkeypatch, tmp_path, mode="local")
    monkeypatch.setattr(sys, "argv", ["app-store-ynab"])

    exit_code = cli.main()

    assert exit_code == 1
    assert "app.mode is 'local'" in capsys.readouterr().err


def test_main_errors_when_email_mode_receipt_path_is_provided(tmp_path: Path, monkeypatch, capsys) -> None:
    receipt_path = tmp_path / "receipt.eml"
    _prepare_default_config(monkeypatch, tmp_path, mode="email")
    receipt_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["app-store-ynab", str(receipt_path)])

    exit_code = cli.main()

    assert exit_code == 1
    assert "Do not provide 'receipt_path' when app.mode is 'email'" in capsys.readouterr().err


def test_main_uses_explicit_config_argument(tmp_path: Path, monkeypatch) -> None:
    explicit_config = tmp_path / "custom" / "my-config.yaml"
    receipt_path = tmp_path / "receipt.eml"
    explicit_config.parent.mkdir(parents=True, exist_ok=True)
    _write_base_config(explicit_config, mode="local")
    receipt_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["app-store-ynab", "--config", str(explicit_config), str(receipt_path), "--dry-run"],
    )
    monkeypatch.setattr(cli, "process_receipt", lambda **_: ProcessResult("DRY_RUN", "ok", "rid", 0, ()))

    exit_code = cli.main()

    assert exit_code == 0
