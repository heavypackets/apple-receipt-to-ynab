from datetime import date

from apple_receipt_to_ynab.models import SplitLine
from apple_receipt_to_ynab.ynab import build_parent_transaction


def test_build_parent_transaction_single_line_has_no_subtransactions() -> None:
    line = SplitLine(
        source_description="Apple Music",
        base_milliunits=10990,
        tax_milliunits=880,
        total_milliunits=11870,
        ynab_category_id="cat-1",
        ynab_payee_id=None,
        ynab_payee_name="Apple Music",
        mapping_rule_id="apple_music",
    )
    tx = build_parent_transaction(
        account_id="acct-1",
        receipt_id="R-1",
        receipt_date=date(2026, 2, 16),
        split_lines=[line],
        grand_total_milliunits=11870,
    )

    assert tx["amount"] == -11870
    assert tx["category_id"] == "cat-1"
    assert tx["payee_name"] == "Apple Music"
    assert tx["memo"] == "Receipt: R-1"
    assert "import_id" not in tx
    assert "subtransactions" not in tx


def test_build_parent_transaction_multiple_lines_uses_subtransactions() -> None:
    lines = [
        SplitLine(
            source_description="A",
            base_milliunits=1000,
            tax_milliunits=100,
            total_milliunits=1100,
            ynab_category_id="cat-a",
            ynab_payee_id=None,
            ynab_payee_name="Payee A",
            mapping_rule_id="a",
        ),
        SplitLine(
            source_description="B",
            base_milliunits=2000,
            tax_milliunits=200,
            total_milliunits=2200,
            ynab_category_id="cat-b",
            ynab_payee_id=None,
            ynab_payee_name="Payee B",
            mapping_rule_id="b",
        ),
    ]
    tx = build_parent_transaction(
        account_id="acct-1",
        receipt_id="R-2",
        receipt_date=date(2026, 2, 16),
        split_lines=lines,
        grand_total_milliunits=3300,
    )

    assert tx["amount"] == -3300
    assert tx["category_id"] is None
    assert tx["payee_name"] == "Apple"
    assert len(tx["subtransactions"]) == 2
    assert "import_id" not in tx
    assert "memo" not in tx["subtransactions"][0]
    assert "memo" not in tx["subtransactions"][1]


def test_build_parent_transaction_includes_flag_color_when_set() -> None:
    line = SplitLine(
        source_description="Unknown",
        base_milliunits=1000,
        tax_milliunits=100,
        total_milliunits=1100,
        ynab_category_id="cat-u",
        ynab_payee_id=None,
        ynab_payee_name="Apple",
        mapping_rule_id="fallback",
    )
    tx = build_parent_transaction(
        account_id="acct-1",
        receipt_id="R-3",
        receipt_date=date(2026, 2, 16),
        split_lines=[line],
        grand_total_milliunits=1100,
        ynab_flag_color="yellow",
    )

    assert tx["flag_color"] == "yellow"


def test_build_parent_transaction_multi_line_includes_flag_color_when_set() -> None:
    lines = [
        SplitLine(
            source_description="A",
            base_milliunits=1000,
            tax_milliunits=100,
            total_milliunits=1100,
            ynab_category_id="cat-a",
            ynab_payee_id=None,
            ynab_payee_name="Payee A",
            mapping_rule_id="a",
        ),
        SplitLine(
            source_description="B",
            base_milliunits=2000,
            tax_milliunits=200,
            total_milliunits=2200,
            ynab_category_id="cat-b",
            ynab_payee_id=None,
            ynab_payee_name="Payee B",
            mapping_rule_id="b",
        ),
    ]

    tx = build_parent_transaction(
        account_id="acct-1",
        receipt_id="R-5",
        receipt_date=date(2026, 2, 16),
        split_lines=lines,
        grand_total_milliunits=3300,
        ynab_flag_color="blue",
    )

    assert tx["flag_color"] == "blue"


def test_build_parent_transaction_single_line_does_not_fallback_payee_name() -> None:
    line = SplitLine(
        source_description="Unknown",
        base_milliunits=1000,
        tax_milliunits=100,
        total_milliunits=1100,
        ynab_category_id="cat-u",
        ynab_payee_id=None,
        ynab_payee_name=None,  # type: ignore[arg-type]
        mapping_rule_id="fallback",
    )
    tx = build_parent_transaction(
        account_id="acct-1",
        receipt_id="R-4",
        receipt_date=date(2026, 2, 16),
        split_lines=[line],
        grand_total_milliunits=1100,
    )

    assert tx["payee_name"] is None
