from decimal import Decimal

from apple_receipt_to_ynab.parser import parse_receipt_text


def test_parse_receipt_text_ignores_email_wrapper_and_footer_noise() -> None:
    raw_text = """
From: Example Sender <sender@example.com>
Date: Jan 1, 2020
Subject: Fwd: Apple receipt
Page 1 of 2
Random preface charge 999.99

Apple Services Receipt
Order ID: MKT-ABC123
02/11/2026
Team Notes Pro $10.99
Cloud Storage Basic $2.99
Tax $1.12
Total $15.10

Page 2 of 2
Printed by Gmail 123.45
"""
    parsed = parse_receipt_text(raw_text, source_name="wrapped.txt", default_currency="USD")

    assert parsed.receipt_id == "MKT-ABC123"
    assert parsed.receipt_date.isoformat() == "2026-02-11"
    assert parsed.tax_total == Decimal("1.12")
    assert parsed.grand_total == Decimal("15.10")
    assert [item.description for item in parsed.subscriptions] == ["Team Notes Pro", "Cloud Storage Basic"]


def test_parse_receipt_text_parses_simple_receipt() -> None:
    raw_text = """
Order ID: MKT-SIMPLE1
2026-02-12
Starter Productivity Bundle $19.95
Tax $1.60
Total $21.55
"""
    parsed = parse_receipt_text(raw_text, source_name="simple.txt", default_currency="USD")

    assert parsed.receipt_id == "MKT-SIMPLE1"
    assert parsed.receipt_date.isoformat() == "2026-02-12"
    assert parsed.tax_total == Decimal("1.60")
    assert parsed.grand_total == Decimal("21.55")
    assert [item.description for item in parsed.subscriptions] == ["Starter Productivity Bundle"]
