from decimal import Decimal
from email import policy
from email.message import EmailMessage
from pathlib import Path

from apple_receipt_to_ynab.parser import parse_receipt_eml


def test_parse_alt_format_single_item(tmp_path: Path) -> None:
    html = """
<html><body>
  <div>DATE</div><div>Feb 11, 2026</div>
  <div>ORDER ID</div><div>ALT-ORDER-001</div>
  <div>DOCUMENT NO.</div><div>DOC-000009876543</div>

  <table>
    <tr>
      <td class="item-cell">
        <span class="title">Business Insights Hub</span><br/>
        <span class="addon-duration">Business Insights Hub (Monthly)</span><br/>
        <span class="renewal">Renews Mar 11, 2026</span>
      </td>
      <td class="price-cell"><span>$14.99</span></td>
    </tr>
  </table>

  <table>
    <tr><td>Subtotal</td><td>$14.99</td></tr>
    <tr><td>Tax</td><td>$1.05</td></tr>
    <tr><td>TOTAL</td><td>$16.04</td></tr>
  </table>
  <div id="footer_section"></div>
</body></html>
""".strip()
    path = _write_test_eml(tmp_path / "alt-single.eml", html)
    parsed = parse_receipt_eml(path)

    assert parsed.receipt_id == "ALT-ORDER-001"
    assert parsed.receipt_date.isoformat() == "2026-02-11"
    assert parsed.tax_total == Decimal("1.05")
    assert parsed.grand_total == Decimal("16.04")
    assert [item.description for item in parsed.subscriptions] == [
        "Business Insights Hub - Business Insights Hub (Monthly)"
    ]
    assert [item.base_amount for item in parsed.subscriptions] == [Decimal("14.99")]


def test_parse_alt_format_multiple_items_ignores_mobile_duplicate_rows(tmp_path: Path) -> None:
    html = """
<html><body>
  <div>DATE</div><div>Jan 13, 2026</div>
  <div>ORDER ID</div><div>ALT-ORDER-002</div>

  <table>
    <tr>
      <td class="item-cell">
        <span class="title">Focus Timer</span><br/>
        <span class="artist">Example Labs</span><br/>
        <span class="type">iOS App</span><br/>
        <span class="device">hp-cell</span>
      </td>
      <td class="price-cell"><span>$2.99</span></td>
    </tr>
    <tr>
      <td class="item-cell aapl-mobile-cell">
        <span class="title">Focus Timer</span><br/>
        <span class="artist">Example Labs</span><br/>
        <span class="type">iOS App</span><br/>
        <span class="device">hp-cell</span>
      </td>
      <td class="price-cell"><span>$2.99</span></td>
    </tr>
    <tr>
      <td class="item-cell">
        <span class="title">Prompt Board</span><br/>
        <span class="addon-duration">Prompt Board Plus (7 Days)</span><br/>
        <span class="renewal">Renews Jan 18, 2026</span>
      </td>
      <td class="price-cell"><span>$0.99</span></td>
    </tr>
    <tr>
      <td class="item-cell">
        <span class="title">Prompt Board</span><br/>
        <span class="addon-duration">Prompt Board Plus (7 Days)</span><br/>
        <span class="renewal">Renews Jan 25, 2026</span>
      </td>
      <td class="price-cell"><span>$0.99</span></td>
    </tr>
  </table>

  <table>
    <tr><td>Subtotal</td><td>$4.97</td></tr>
    <tr><td>Tax</td><td>$0.35</td></tr>
    <tr><td>TOTAL</td><td>$5.32</td></tr>
  </table>
</body></html>
""".strip()
    path = _write_test_eml(tmp_path / "alt-multi.eml", html)
    parsed = parse_receipt_eml(path)

    assert parsed.receipt_id == "ALT-ORDER-002"
    assert parsed.receipt_date.isoformat() == "2026-01-13"
    assert parsed.tax_total == Decimal("0.35")
    assert parsed.grand_total == Decimal("5.32")
    assert [item.description for item in parsed.subscriptions] == [
        "Focus Timer",
        "Prompt Board - Prompt Board Plus (7 Days)",
        "Prompt Board - Prompt Board Plus (7 Days)",
    ]
    assert [item.base_amount for item in parsed.subscriptions] == [
        Decimal("2.99"),
        Decimal("0.99"),
        Decimal("0.99"),
    ]


def _write_test_eml(path: Path, html: str) -> Path:
    message = EmailMessage()
    message["From"] = "no_reply@email.apple.com"
    message["To"] = "user@example.com"
    message["Subject"] = "Your receipt from Apple."
    message.set_content("Fallback plain text")
    message.add_alternative(html, subtype="html", cte="quoted-printable")
    path.write_bytes(message.as_bytes(policy=policy.SMTP))
    return path
