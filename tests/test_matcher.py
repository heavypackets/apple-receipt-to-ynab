from decimal import Decimal

from apple_receipt_to_ynab.matcher import match_subscriptions
from apple_receipt_to_ynab.models import (
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
                friendly_name="Contains",
                ynab_category_id="c1",
            ),
            MappingRule(
                id="exact_rule",
                enabled=True,
                match=MatchSpec(type="exact", value="Apple Music"),
                friendly_name="Exact",
                ynab_category_id="c2",
            ),
            MappingRule(
                id="regex_rule",
                enabled=True,
                match=MatchSpec(type="regex", value=r"(?i)apple\s+music"),
                friendly_name="Regex",
                ynab_category_id="c3",
            ),
        ],
        fallback=None,
    )

    matched = match_subscriptions([SubscriptionLine(description="Apple Music", base_amount=Decimal("9.99"))], config)
    assert matched[0].friendly_name == "Exact"
    assert matched[0].mapping_rule_id == "exact_rule"

