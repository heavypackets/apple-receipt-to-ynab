from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from apple_receipt_to_ynab.models import (
    AppConfig,
    EmailConfig,
    FallbackMapping,
    MappingConfig,
    MappingDefaults,
    MappingRule,
    MatchSpec,
    RuntimeConfig,
    YnabConfig,
)

ALLOWED_MATCH_TYPES = {"exact", "contains", "regex"}
ALLOWED_FLAG_COLORS = {"red", "orange", "yellow", "green", "blue", "purple"}
ALLOWED_APP_MODES = {"local", "email"}
DEFAULT_YNAB_API_URL = "https://api.ynab.com/v1"
DEFAULT_YNAB_LOOKBACK_DAYS = 7
DEFAULT_EMAIL_SUBJECT_FILTER = "Your receipt from Apple."
DEFAULT_EMAIL_SENDER_FILTER = "no_reply@email.apple.com"
DEFAULT_EMAIL_MAX_AGE_DAYS = 7
DEFAULT_EMAIL_MAX_RESULTS = 10


class ConfigError(ValueError):
    pass


def load_config(path: Path) -> RuntimeConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping.")

    version = _required_int(raw, "version")
    if version != 1:
        raise ConfigError(f"Unsupported config version: {version}. Expected 1.")

    ynab_raw = _required_mapping(raw, "ynab")
    ynab = YnabConfig(
        api_token=_required_str(ynab_raw, "api_token"),
        budget_id=_required_str(ynab_raw, "budget_id"),
        api_url=_optional_str(ynab_raw, "api_url") or DEFAULT_YNAB_API_URL,
        lookback_days=_optional_positive_int(ynab_raw, "lookback_days")
        or DEFAULT_YNAB_LOOKBACK_DAYS,
    )

    app_raw = raw.get("app", {})
    if not isinstance(app_raw, dict):
        raise ConfigError("'app' must be a mapping if provided.")
    app_mode = (_optional_str(app_raw, "mode") or "local").lower()
    if app_mode not in ALLOWED_APP_MODES:
        allowed = ", ".join(sorted(ALLOWED_APP_MODES))
        raise ConfigError(f"'app.mode' must be one of: {allowed}.")
    log_path = _optional_str(app_raw, "log_path")
    app = AppConfig(mode=app_mode, log_path=Path(log_path) if log_path else None)

    email = _parse_email(path=path, raw=raw.get("email"), app_mode=app_mode)

    mappings_raw = _required_mapping(raw, "mappings")
    mappings = _parse_mappings(version=version, raw=mappings_raw)

    return RuntimeConfig(version=version, ynab=ynab, app=app, email=email, mappings=mappings)


def _parse_email(path: Path, raw: Any, app_mode: str) -> EmailConfig:
    if raw is None:
        if app_mode == "email":
            raise ConfigError("'email' is required when 'app.mode' is 'email'.")
        return EmailConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'email' must be a mapping if provided.")

    subject_filter = _optional_str(raw, "subject_filter") or DEFAULT_EMAIL_SUBJECT_FILTER
    sender_filter = _optional_str(raw, "sender_filter") or DEFAULT_EMAIL_SENDER_FILTER
    max_age_days = _optional_positive_int(raw, "max_age_days") or DEFAULT_EMAIL_MAX_AGE_DAYS
    if app_mode == "email":
        key_path_raw = _required_str(raw, "service_account_key_path")
        delegated_user_email = _required_str(raw, "delegated_user_email")
    else:
        key_path_raw = _optional_str(raw, "service_account_key_path")
        delegated_user_email = _optional_str(raw, "delegated_user_email")

    key_path: Path | None = None
    if key_path_raw is not None:
        key_path = Path(key_path_raw)
        if not key_path.is_absolute():
            key_path = path.parent / key_path

    return EmailConfig(
        subject_filter=subject_filter,
        sender_filter=sender_filter,
        max_age_days=max_age_days,
        service_account_key_path=key_path,
        delegated_user_email=delegated_user_email,
        max_results=_optional_positive_int(raw, "max_results") or DEFAULT_EMAIL_MAX_RESULTS,
        query_extra=_optional_str(raw, "query_extra"),
    )


def _parse_mappings(version: int, raw: dict[str, Any]) -> MappingConfig:
    defaults_raw = _required_mapping(raw, "defaults")
    defaults = MappingDefaults(
        ynab_account_id=_required_str(defaults_raw, "ynab_account_id"),
        ynab_category_id=_optional_str(defaults_raw, "ynab_category_id"),
        ynab_flag_color=_optional_flag_color(defaults_raw, "ynab_flag_color"),
        default_currency=_optional_str(defaults_raw, "currency") or "USD",
    )

    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ConfigError("mappings.rules must be a non-empty list.")
    rules = [_parse_rule(item) for item in rules_raw]

    fallback = None
    fallback_raw = raw.get("fallback")
    if fallback_raw is not None:
        if not isinstance(fallback_raw, dict):
            raise ConfigError("mappings.fallback must be a mapping if provided.")
        fallback_enabled = bool(fallback_raw.get("enabled", True))
        fallback_payee_name = (
            _required_str(fallback_raw, "ynab_payee_name")
            if fallback_enabled
            else _optional_str(fallback_raw, "ynab_payee_name")
        )
        fallback = FallbackMapping(
            enabled=fallback_enabled,
            ynab_category_id=_optional_str(fallback_raw, "ynab_category_id"),
            ynab_payee_id=_optional_str(fallback_raw, "ynab_payee_id"),
            ynab_payee_name=fallback_payee_name,
            ynab_flag_color=_optional_flag_color(fallback_raw, "ynab_flag_color"),
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
        ynab_payee_name=_required_str(raw, "ynab_payee_name"),
        ynab_payee_id=_optional_str(raw, "ynab_payee_id"),
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


def _optional_positive_int(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"'{key}' must be a positive integer when set.")
    return value


def _optional_flag_color(raw: dict[str, Any], key: str) -> str | None:
    value = _optional_str(raw, key)
    if value is None:
        return None
    normalized = value.lower()
    if normalized not in ALLOWED_FLAG_COLORS:
        allowed = ", ".join(sorted(ALLOWED_FLAG_COLORS))
        raise ConfigError(f"'{key}' must be one of: {allowed}.")
    return normalized
