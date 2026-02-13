from email import policy
from email.message import EmailMessage
from pathlib import Path
from decimal import Decimal

from apple_receipt_to_ynab.parser import parse_receipt_eml, parse_receipt_file


def test_parse_receipt_eml_extracts_subscription_tables_and_totals(tmp_path: Path) -> None:
    html = """
<html>
  <body>
    <div id="body_section">
      <p>January 24, 2026</p>
      <div><p>Order ID:</p><p>MSD3QH3HFQ</p></div>
      <div><p>Document:</p><p>726081618935</p></div>

      <table class="subscription-lockup__container">
        <tr>
          <td><p>Taimi LGBTQ+ Dating &amp; Chat App</p><p>Taimi Gold (Monthly)</p><p>Renews February 17, 2026</p></td>
          <td><p>$29.99</p></td>
        </tr>
      </table>

      <table class="subscription-lockup__container">
        <tr>
          <td><p>Telegram Messenger</p><p>Telegram Premium (Monthly)</p><p>Renews February 24, 2026</p></td>
          <td><p>$4.99</p></td>
        </tr>
      </table>

      <div class="payment-information">
        <h2>Billing and Payment</h2>
        <p>Subtotal</p><p>$34.98</p>
        <p>Tax</p><p>$2.45</p>
        <p>MasterCard •••• 6047 (Apple Pay)</p><p>$37.43</p>
      </div>
    </div>
    <div id="footer_section"></div>
  </body>
</html>
""".strip()

    path = _write_test_eml(tmp_path / "apple-receipt.eml", html=html)
    parsed = parse_receipt_eml(path)

    assert parsed.receipt_id == "MSD3QH3HFQ"
    assert parsed.receipt_date.isoformat() == "2026-01-24"
    assert parsed.tax_total == Decimal("2.45")
    assert parsed.grand_total == Decimal("37.43")
    assert [item.description for item in parsed.subscriptions] == [
        "Taimi LGBTQ+ Dating & Chat App - Taimi Gold (Monthly)",
        "Telegram Messenger - Telegram Premium (Monthly)",
    ]
    assert [item.base_amount for item in parsed.subscriptions] == [
        Decimal("29.99"),
        Decimal("4.99"),
    ]


def test_parse_receipt_file_dispatches_to_eml(tmp_path: Path) -> None:
    html = """
<html><body>
  <p>January 24, 2026</p>
  <p>Order ID:</p><p>ABC123</p>
  <table class="subscription-lockup__container"><tr><td><p>App</p></td><td><p>$1.99</p></td></tr></table>
  <div class="payment-information"><p>Tax</p><p>$0.10</p><p>Card</p><p>$2.09</p></div>
  <div id="footer_section"></div>
</body></html>
""".strip()

    path = _write_test_eml(tmp_path / "receipt.eml", html=html)
    parsed = parse_receipt_file(path)
    assert parsed.receipt_id == "ABC123"
    assert parsed.grand_total == Decimal("2.09")


def test_parse_receipt_eml_handles_quoted_printable_wrapped_lines(tmp_path: Path) -> None:
    long_plan = "Extremely Long Subscription Plan Name " * 8
    html = f"""
<html><body>
  <p>January 24, 2026</p>
  <p>Order ID:</p><p>WRAP123</p>
  <table class="subscription-lockup__container">
    <tr><td><p>Long App</p><p>{long_plan}</p></td><td><p>$9.99</p></td></tr>
  </table>
  <div class="payment-information"><p>Subtotal</p><p>$9.99</p><p>Tax</p><p>$0.80</p><p>Card</p><p>$10.79</p></div>
  <div id="footer_section"></div>
</body></html>
""".strip()
    path = _write_test_eml(tmp_path / "wrapped.eml", html=html)

    parsed = parse_receipt_eml(path)

    assert parsed.receipt_id == "WRAP123"
    assert parsed.tax_total == Decimal("0.80")
    assert parsed.grand_total == Decimal("10.79")
    assert len(parsed.subscriptions) == 1
    assert parsed.subscriptions[0].description.startswith("Long App - Extremely Long Subscription Plan Name")


def _write_test_eml(path: Path, html: str) -> Path:
    message = EmailMessage()
    message["From"] = "no_reply@email.apple.com"
    message["To"] = "user@example.com"
    message["Subject"] = "Your receipt from Apple."
    message.set_content("Fallback plain text")
    message.add_alternative(html, subtype="html", cte="quoted-printable")
    path.write_bytes(message.as_bytes(policy=policy.SMTP))
    return path
