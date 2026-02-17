from pathlib import Path

import pytest

from apple_receipt_to_ynab.config import DEFAULT_YNAB_API_URL, ConfigError, load_config


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
    assert cfg.app.log_path == Path("logs/run.log")
    assert cfg.mappings.defaults.ynab_flag_color == "green"
    assert cfg.mappings.fallback is not None
    assert cfg.mappings.fallback.ynab_flag_color == "yellow"


def test_load_config_defaults_api_url_and_stdout_logging_when_missing(tmp_path: Path) -> None:
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
    assert cfg.app.log_path is None


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
