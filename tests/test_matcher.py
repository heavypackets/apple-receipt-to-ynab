from decimal import Decimal

import pytest

from apple_receipt_to_ynab.matcher import UnmappedSubscriptionError, match_subscriptions
from apple_receipt_to_ynab.models import (
    FallbackMapping,
    MappingConfig,
    MappingDefaults,
    MappingRule,
    MatchSpec,
    SubscriptionLine,
)


def test_match_precedence_exact_then_contains_then_regex() -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="a1"),
        rules=[
            MappingRule(
                id="contains_rule",
                enabled=True,
                match=MatchSpec(type="contains", value="Apple"),
                ynab_category_id="c1",
                ynab_payee_name="Contains",
            ),
            MappingRule(
                id="exact_rule",
                enabled=True,
                match=MatchSpec(type="exact", value="Apple Music"),
                ynab_category_id="c2",
                ynab_payee_name="Exact",
            ),
            MappingRule(
                id="regex_rule",
                enabled=True,
                match=MatchSpec(type="regex", value=r"(?i)apple\s+music"),
                ynab_category_id="c3",
                ynab_payee_name="Regex",
            ),
        ],
        fallback=None,
    )

    matched = match_subscriptions([SubscriptionLine(description="Apple Music", base_amount=Decimal("9.99"))], config)
    assert matched[0].ynab_payee_name == "Exact"
    assert matched[0].mapping_rule_id == "exact_rule"


def test_match_uses_fallback_payee_name_without_defaults() -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(
            ynab_account_id="a1",
            ynab_category_id="fallback-cat",
        ),
        rules=[],
        fallback=FallbackMapping(
            enabled=True,
            ynab_category_id=None,
            ynab_payee_id=None,
            ynab_payee_name="Fallback Payee",
        ),
    )

    matched = match_subscriptions(
        [SubscriptionLine(description="Unknown Subscription", base_amount=Decimal("4.99"))],
        config,
    )
    assert matched[0].ynab_payee_name == "Fallback Payee"
    assert matched[0].ynab_category_id == "fallback-cat"
    assert matched[0].mapping_rule_id == "fallback"


def test_match_raises_unmapped_error_when_no_rule_and_fallback_disabled() -> None:
    config = MappingConfig(
        version=1,
        defaults=MappingDefaults(ynab_account_id="a1"),
        rules=[],
        fallback=None,
    )

    with pytest.raises(UnmappedSubscriptionError, match="No mapping rule for: Unknown Subscription"):
        match_subscriptions(
            [SubscriptionLine(description="Unknown Subscription", base_amount=Decimal("4.99"))],
            config,
        )
