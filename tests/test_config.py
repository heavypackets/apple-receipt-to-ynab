from pathlib import Path

import pytest

from apple_receipt_to_ynab.config import (
    DEFAULT_APP_LOG_PATH,
    DEFAULT_EMAIL_MAX_AGE_DAYS,
    DEFAULT_EMAIL_MAX_RESULTS,
    DEFAULT_EMAIL_SERVICE_ACCOUNT_KEY_PATH,
    DEFAULT_EMAIL_SENDER_FILTER,
    DEFAULT_EMAIL_SUBJECT_FILTER,
    DEFAULT_YNAB_API_URL,
    DEFAULT_YNAB_LOOKBACK_DAYS,
    ConfigError,
    load_config,
)


def test_load_config_parses_nested_config_and_normalizes_fallback_flag_color(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
  api_url: "https://ynab.example/v1"
app:
  log_path: "logs/run.log"
mappings:
  defaults:
    ynab_account_id: "acct"
    ynab_flag_color: "Green"
  rules:
    - id: r1
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
  fallback:
    enabled: true
    ynab_category_id: "cat-fallback"
    ynab_payee_name: "Apple"
    ynab_flag_color: "Yellow"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.version == 1
    assert cfg.ynab.api_token == "token"
    assert cfg.ynab.budget_id == "budget"
    assert cfg.ynab.api_url == "https://ynab.example/v1"
    assert cfg.ynab.lookback_days == DEFAULT_YNAB_LOOKBACK_DAYS
    assert cfg.app.mode == "local"
    assert cfg.app.log_path == Path("logs/run.log")
    assert cfg.email.subject_filter == DEFAULT_EMAIL_SUBJECT_FILTER
    assert cfg.email.sender_filter == DEFAULT_EMAIL_SENDER_FILTER
    assert cfg.email.max_age_days == DEFAULT_EMAIL_MAX_AGE_DAYS
    assert cfg.email.max_results == DEFAULT_EMAIL_MAX_RESULTS
    assert cfg.mappings.defaults.ynab_flag_color == "green"
    assert cfg.mappings.fallback is not None
    assert cfg.mappings.fallback.ynab_flag_color == "yellow"


def test_load_config_defaults_api_url_and_log_file_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.ynab.api_url == DEFAULT_YNAB_API_URL
    assert cfg.ynab.lookback_days == DEFAULT_YNAB_LOOKBACK_DAYS
    assert cfg.app.log_path == DEFAULT_APP_LOG_PATH


def test_load_config_parses_email_mode_and_relative_service_account_path(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    key_path = tmp_path / "secrets" / "gmail-sa.json"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
  lookback_days: 45
app:
  mode: "email"
email:
  subject_filter: "My Custom Subject"
  sender_filter: "sender@example.com"
  max_age_days: 14
  service_account_key_path: "./secrets/gmail-sa.json"
  delegated_user_email: "robot@example.com"
  max_results: 50
  query_extra: "in:anywhere"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.ynab.lookback_days == 45
    assert cfg.app.mode == "email"
    assert cfg.email.subject_filter == "My Custom Subject"
    assert cfg.email.sender_filter == "sender@example.com"
    assert cfg.email.max_age_days == 14
    assert cfg.email.service_account_key_path == key_path
    assert cfg.email.delegated_user_email == "robot@example.com"
    assert cfg.email.max_results == 50
    assert cfg.email.query_extra == "in:anywhere"


def test_load_config_rejects_email_mode_without_email_mapping(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
app:
  mode: "email"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="'email' section is required"):
        load_config(path)


def test_load_config_rejects_invalid_yaml_with_friendly_message(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      match:
        type: exact
        value: "Apple Music
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Invalid config.yaml: YAML syntax is invalid"):
        load_config(path)


def test_load_config_defaults_email_mode_service_account_path_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
app:
  mode: "email"
email:
  delegated_user_email: "robot@example.com"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.email.service_account_key_path == DEFAULT_EMAIL_SERVICE_ACCOUNT_KEY_PATH
    assert cfg.email.delegated_user_email == "robot@example.com"


def test_load_config_rejects_invalid_lookback_days(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
  lookback_days: 0
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="lookback_days"):
        load_config(path)


def test_load_config_rejects_missing_budget_id(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="budget_id"):
        load_config(path)


def test_load_config_rejects_invalid_fallback_flag_color(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
  fallback:
    enabled: true
    ynab_category_id: "cat-fallback"
    ynab_payee_name: "Apple"
    ynab_flag_color: "pink"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="ynab_flag_color"):
        load_config(path)


def test_load_config_rejects_invalid_defaults_flag_color(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
mappings:
  defaults:
    ynab_account_id: "acct"
    ynab_flag_color: "pink"
  rules:
    - id: r1
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="ynab_flag_color"):
        load_config(path)


def test_load_config_rejects_missing_rule_payee_name(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="ynab_payee_name"):
        load_config(path)


def test_load_config_rejects_missing_fallback_payee_when_enabled(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
  fallback:
    enabled: true
    ynab_category_id: "cat-fallback"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="ynab_payee_name"):
        load_config(path)


def test_load_config_allows_missing_fallback_payee_when_disabled(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
ynab:
  api_token: "token"
  budget_id: "budget"
mappings:
  defaults:
    ynab_account_id: "acct"
  rules:
    - id: r1
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat"
      ynab_payee_name: "Apple Music"
  fallback:
    enabled: false
    ynab_category_id: "cat-fallback"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.mappings.fallback is not None
    assert cfg.mappings.fallback.enabled is False
    assert cfg.mappings.fallback.ynab_payee_name is None
