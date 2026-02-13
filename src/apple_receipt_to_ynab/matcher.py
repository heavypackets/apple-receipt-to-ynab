from __future__ import annotations

import re

from apple_receipt_to_ynab.models import MappingConfig, MatchedSubscription, SubscriptionLine
from apple_receipt_to_ynab.utils import clean_text

MATCH_ORDER = ("exact", "contains", "regex")


class MappingMatchError(ValueError):
    pass


def match_subscriptions(
    subscriptions: list[SubscriptionLine], config: MappingConfig
) -> list[MatchedSubscription]:
    matched: list[MatchedSubscription] = []
    unmatched: list[str] = []

    for sub in subscriptions:
        rule = _find_rule(clean_text(sub.description), config)
        if rule is None:
            if config.fallback and config.fallback.enabled:
                category_id = config.fallback.ynab_category_id or config.defaults.fallback_category_id
                if not category_id:
                    raise MappingMatchError(
                        "Fallback configured without ynab_category_id and no defaults.fallback_category_id."
                    )
                matched.append(
                    MatchedSubscription(
                        source_description=sub.description,
                        base_amount=sub.base_amount,
                        ynab_category_id=category_id,
                        ynab_payee_id=config.fallback.ynab_payee_id,
                        ynab_payee_name=config.fallback.ynab_payee_name
                        or config.defaults.default_payee_name,
                        memo=_render_memo(config.fallback.memo_template, sub.description),
                        mapping_rule_id="fallback",
                    )
                )
                continue
            unmatched.append(sub.description)
            continue

        matched.append(
            MatchedSubscription(
                source_description=sub.description,
                base_amount=sub.base_amount,
                ynab_category_id=rule.ynab_category_id,
                ynab_payee_id=rule.ynab_payee_id,
                ynab_payee_name=rule.ynab_payee_name or config.defaults.default_payee_name,
                memo=_render_memo(rule.memo_template, sub.description),
                mapping_rule_id=rule.id,
            )
        )

    if unmatched:
        joined = "; ".join(unmatched)
        raise MappingMatchError(f"No mapping rule for: {joined}")

    return matched


def _find_rule(description: str, config: MappingConfig):
    normalized = description.strip()
    for match_type in MATCH_ORDER:
        for rule in config.rules:
            if not rule.enabled or rule.match.type != match_type:
                continue
            pattern = rule.match.value
            if match_type == "exact" and normalized == pattern:
                return rule
            if match_type == "contains" and pattern in normalized:
                return rule
            if match_type == "regex" and re.search(pattern, normalized):
                return rule
    return None


def _render_memo(template: str | None, raw_description: str) -> str | None:
    if template is None:
        return None
    return template.format(raw_description=raw_description)
