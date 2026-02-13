from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from apple_receipt_to_ynab.models import (
    FallbackMapping,
    MappingConfig,
    MappingDefaults,
    MappingRule,
    MatchSpec,
)

ALLOWED_MATCH_TYPES = {"exact", "contains", "regex"}


class ConfigError(ValueError):
    pass


def load_mapping_config(path: Path) -> MappingConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping.")

    version = _required_int(raw, "version")
    if version != 1:
        raise ConfigError(f"Unsupported mapping config version: {version}. Expected 1.")

    defaults_raw = _required_mapping(raw, "defaults")
    defaults = MappingDefaults(
        ynab_account_id=_required_str(defaults_raw, "ynab_account_id"),
        default_payee_name=_optional_str(defaults_raw, "default_payee_name"),
        fallback_category_id=_optional_str(defaults_raw, "fallback_category_id"),
        default_currency=_optional_str(defaults_raw, "currency") or "USD",
    )

    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ConfigError("Config must include a non-empty rules list.")
    rules = [_parse_rule(item) for item in rules_raw]

    fallback = None
    fallback_raw = raw.get("fallback")
    if fallback_raw is not None:
        if not isinstance(fallback_raw, dict):
            raise ConfigError("fallback must be a mapping if provided.")
        fallback = FallbackMapping(
            enabled=bool(fallback_raw.get("enabled", True)),
            ynab_category_id=_optional_str(fallback_raw, "ynab_category_id"),
            ynab_payee_id=_optional_str(fallback_raw, "ynab_payee_id"),
            ynab_payee_name=_optional_str(fallback_raw, "ynab_payee_name"),
            memo_template=_optional_str(fallback_raw, "memo_template"),
        )

    return MappingConfig(version=version, defaults=defaults, rules=rules, fallback=fallback)


def _parse_rule(raw: Any) -> MappingRule:
    if not isinstance(raw, dict):
        raise ConfigError("Each rule entry must be a mapping.")
    match_raw = _required_mapping(raw, "match")
    match_type = _required_str(match_raw, "type")
    if match_type not in ALLOWED_MATCH_TYPES:
        raise ConfigError(f"Unsupported match type: {match_type}")
    match = MatchSpec(type=match_type, value=_required_str(match_raw, "value"))

    return MappingRule(
        id=_required_str(raw, "id"),
        enabled=bool(raw.get("enabled", True)),
        match=match,
        ynab_category_id=_required_str(raw, "ynab_category_id"),
        ynab_payee_id=_optional_str(raw, "ynab_payee_id"),
        ynab_payee_name=_optional_str(raw, "ynab_payee_name"),
        memo_template=_optional_str(raw, "memo_template"),
    )


def _required_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"'{key}' must be a mapping.")
    return value


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{key}' must be a non-empty string.")
    return value.strip()


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{key}' must be a non-empty string when set.")
    return value.strip()


def _required_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int):
        raise ConfigError(f"'{key}' must be an integer.")
    return value
