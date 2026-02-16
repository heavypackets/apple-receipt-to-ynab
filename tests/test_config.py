from pathlib import Path

import pytest

from apple_receipt_to_ynab.config import ConfigError, load_mapping_config


def test_load_mapping_config_parses_fallback_flag_color(tmp_path: Path) -> None:
    path = tmp_path / "mappings.yaml"
    path.write_text(
        """
version: 1
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
  ynab_flag_color: "Yellow"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_mapping_config(path)

    assert cfg.fallback is not None
    assert cfg.fallback.ynab_flag_color == "yellow"


def test_load_mapping_config_rejects_invalid_fallback_flag_color(tmp_path: Path) -> None:
    path = tmp_path / "mappings.yaml"
    path.write_text(
        """
version: 1
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
        load_mapping_config(path)


def test_load_mapping_config_rejects_missing_rule_payee_name(tmp_path: Path) -> None:
    path = tmp_path / "mappings.yaml"
    path.write_text(
        """
version: 1
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
        load_mapping_config(path)


def test_load_mapping_config_rejects_missing_fallback_payee_when_enabled(tmp_path: Path) -> None:
    path = tmp_path / "mappings.yaml"
    path.write_text(
        """
version: 1
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
        load_mapping_config(path)


def test_load_mapping_config_allows_missing_fallback_payee_when_disabled(tmp_path: Path) -> None:
    path = tmp_path / "mappings.yaml"
    path.write_text(
        """
version: 1
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

    cfg = load_mapping_config(path)
    assert cfg.fallback is not None
    assert cfg.fallback.enabled is False
    assert cfg.fallback.ynab_payee_name is None
