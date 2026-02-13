from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import Path

from apple_receipt_to_ynab.models import ParsedReceipt, SubscriptionLine
from apple_receipt_to_ynab.utils import clean_text

AMOUNT_PATTERN = re.compile(r"(?P<amount>[-+]?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})|[-+]?\$?\d+\.\d{2})")
CURRENCY_AMOUNT_PATTERN = re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})")
RECEIPT_ID_PATTERN = re.compile(
    r"(?:Order\s*ID|Document\s*(?:No|Number)|Receipt\s*ID|Invoice\s*ID)\s*[:#]?\s*([A-Z0-9\-]+)",
    re.IGNORECASE,
)
DATE_PATTERNS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%b %d, %Y",
    "%B %d, %Y",
)
IGNORE_LINE_PATTERNS = (
    re.compile(r"\btax\b", re.IGNORECASE),
    re.compile(r"\btotal\b", re.IGNORECASE),
    re.compile(r"\bsubtotal\b", re.IGNORECASE),
    re.compile(r"\border\s*id\b", re.IGNORECASE),
    re.compile(r"\binvoice\b", re.IGNORECASE),
    re.compile(r"\bamount\s*charged\b", re.IGNORECASE),
    re.compile(r"\bbalance\b", re.IGNORECASE),
    re.compile(r"^(from|to|subject|sent|date|cc|bcc)\s*:", re.IGNORECASE),
    re.compile(r"^on .+ wrote:$", re.IGNORECASE),
    re.compile(r"^page\s+\d+\s+of\s+\d+", re.IGNORECASE),
    re.compile(r"\bprinted by\b", re.IGNORECASE),
)
TOTAL_LINE_PATTERNS = (
    re.compile(r"\bgrand\s*total\b", re.IGNORECASE),
    re.compile(r"\bamount\s*charged\b", re.IGNORECASE),
    re.compile(r"\btotal\b", re.IGNORECASE),
)
TAX_LINE_PATTERNS = (
    re.compile(r"\btax\b", re.IGNORECASE),
    re.compile(r"\bvat\b", re.IGNORECASE),
)
DATE_CANDIDATE_PATTERN = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b"
)
DEFAULT_RECEIPT_PREFIX = "PDF-RECEIPT"
LEADING_EMAIL_NOISE_PATTERNS = (
    re.compile(r"^(from|to|subject|sent|date|cc|bcc)\s*:", re.IGNORECASE),
    re.compile(r"^on .+ wrote:$", re.IGNORECASE),
    re.compile(r"^page\s+\d+\s+of\s+\d+", re.IGNORECASE),
    re.compile(r"^sent from my", re.IGNORECASE),
)
SECTION_START_HINT_PATTERNS = (
    RECEIPT_ID_PATTERN,
    re.compile(r"\b(receipt|invoice|document\s*(?:no|number))\b", re.IGNORECASE),
    re.compile(r"\b(apple|app\s*store|itunes)\b", re.IGNORECASE),
)
SECTION_SCAN_WINDOW_LINES = 160
SECTION_TOTAL_FOOTER_BUFFER_LINES = 12
SUBSCRIPTION_TABLE_PATTERN = re.compile(
    r"<table[^>]*class=\"[^\"]*subscription-lockup__container[^\"]*\"[^>]*>(.*?)</table>",
    re.IGNORECASE | re.DOTALL,
)
P_TAG_CONTENT_PATTERN = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
STYLE_SCRIPT_PATTERN = re.compile(r"<(style|script)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>", re.DOTALL)
HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
PAYMENT_INFORMATION_SECTION_PATTERN = re.compile(
    r"<div[^>]*class=\"[^\"]*payment-information[^\"]*\"[^>]*>.*?(?=<div\s+id=\"footer_section\")",
    re.IGNORECASE | re.DOTALL,
)
RECEIPT_ID_LABEL_PATTERN = re.compile(
    r"^(order\s*id|receipt\s*id|invoice\s*id|document\s*(?:no|number)|document)\s*:?$",
    re.IGNORECASE,
)


class ReceiptParseError(ValueError):
    pass


def parse_receipt_file(path: Path, default_currency: str = "USD") -> ParsedReceipt:
    suffix = path.suffix.lower()
    if suffix == ".eml":
        return parse_receipt_eml(path, default_currency=default_currency)
    if suffix == ".pdf":
        return parse_receipt_pdf(path, default_currency=default_currency)
    raise ReceiptParseError(
        f"Unsupported receipt file extension '{suffix}'. Use a .eml (preferred) or .pdf file."
    )


def parse_receipt_eml(path: Path, default_currency: str = "USD") -> ParsedReceipt:
    if not path.exists():
        raise ReceiptParseError(f"EML not found: {path}")

    with path.open("rb") as handle:
        message = BytesParser(policy=policy.default).parse(handle)

    html = _extract_message_part(message, "text/html")
    if html:
        return _parse_receipt_from_html(html=html, source_path=path, default_currency=default_currency)

    plain_text = _extract_message_part(message, "text/plain")
    if plain_text:
        return parse_receipt_text(text=plain_text, source_name=path, default_currency=default_currency)

    raise ReceiptParseError("EML did not contain a readable text/html or text/plain body.")


def parse_receipt_pdf(path: Path, default_currency: str = "USD") -> ParsedReceipt:
    if not path.exists():
        raise ReceiptParseError(f"PDF not found: {path}")

    text = _extract_pdf_text(path)
    return parse_receipt_text(text=text, source_name=path, default_currency=default_currency)


def parse_receipt_text(
    text: str,
    source_name: Path | str = "TEXT-RECEIPT",
    default_currency: str = "USD",
) -> ParsedReceipt:
    source_path = source_name if isinstance(source_name, Path) else Path(str(source_name))
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    if not lines:
        raise ReceiptParseError("PDF text extraction produced no usable lines.")
    lines = _strip_leading_email_noise(lines)
    lines = _focus_receipt_section(lines)

    receipt_id = _extract_receipt_id(lines, source_path)
    receipt_date = _extract_date(lines)
    currency = _extract_currency(lines, default_currency)

    tax_total = _extract_named_amount(lines, TAX_LINE_PATTERNS)
    grand_total = _extract_named_amount(lines, TOTAL_LINE_PATTERNS, exclude_patterns=TAX_LINE_PATTERNS)
    if grand_total is None:
        raise ReceiptParseError("Could not find grand total in receipt text.")
    if tax_total is None:
        raise ReceiptParseError("Could not find tax total in receipt text.")

    subscriptions = _extract_subscription_lines(lines)
    if not subscriptions:
        raise ReceiptParseError(
            "Could not identify subscription line items. Check parser heuristics against your receipt layout."
        )

    return ParsedReceipt(
        source_pdf=source_path,
        receipt_id=receipt_id,
        receipt_date=receipt_date,
        currency=currency,
        subscriptions=subscriptions,
        tax_total=tax_total,
        grand_total=grand_total,
        raw_text=text,
    )


def _parse_receipt_from_html(html: str, source_path: Path, default_currency: str) -> ParsedReceipt:
    body_html = _strip_style_and_script(html)
    html_lines = _build_metadata_lines_from_html(body_html)
    receipt_id = _extract_receipt_id(html_lines, source_path)
    receipt_date = _extract_date(html_lines)

    subscriptions = _extract_subscriptions_from_html(body_html)
    if not subscriptions:
        raise ReceiptParseError(
            "Could not find subscription tables (class subscription-lockup__container) in the EML HTML body."
        )

    tax_total, grand_total = _extract_payment_totals_from_html(body_html)
    if tax_total is None:
        raise ReceiptParseError("Could not find tax amount in Billing and Payment section of EML HTML.")
    if grand_total is None:
        raise ReceiptParseError("Could not find grand total amount in Billing and Payment section of EML HTML.")

    currency = _extract_currency(html_lines, default_currency)

    return ParsedReceipt(
        source_pdf=source_path,
        receipt_id=receipt_id,
        receipt_date=receipt_date,
        currency=currency,
        subscriptions=subscriptions,
        tax_total=tax_total,
        grand_total=grand_total,
        raw_text=html,
    )


def _extract_message_part(message: Message, content_type: str) -> str | None:
    for part in message.walk():
        if part.is_multipart() or part.get_content_type() != content_type:
            continue
        raw = part.get_payload(decode=True)
        if raw is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")
    return None


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise ReceiptParseError(
            "pypdf is required for PDF parsing. Install dependencies with `pip install -e .`."
        ) from exc

    reader = PdfReader(str(path))
    pages_text = []
    for page in reader.pages:
        pages_text.append(page.extract_text() or "")
    return "\n".join(pages_text)


def _build_metadata_lines_from_html(body_html: str) -> list[str]:
    lines: list[str] = []
    text_tokens = _extract_p_text_tokens(body_html)
    lines.extend(text_tokens)

    for idx, token in enumerate(text_tokens[:-1]):
        if RECEIPT_ID_LABEL_PATTERN.match(token):
            lines.append(f"{token} {text_tokens[idx + 1]}")

    # Include an html-to-text fallback for date/id patterns that may not be inside <p> tags.
    fallback_text = _html_to_plain_text(body_html)
    lines.extend([clean_text(line) for line in fallback_text.splitlines() if clean_text(line)])
    return lines


def _extract_subscriptions_from_html(body_html: str) -> list[SubscriptionLine]:
    subscriptions: list[SubscriptionLine] = []
    for table_html in SUBSCRIPTION_TABLE_PATTERN.findall(body_html):
        tokens = _extract_p_text_tokens(table_html)
        if not tokens:
            continue

        amount = _extract_amount_from_tokens(tokens)
        if amount is None:
            continue

        description_tokens = [token for token in tokens if _extract_last_amount(token) is None]
        description = _compose_subscription_description(description_tokens)
        if not description:
            continue

        subscriptions.append(SubscriptionLine(description=description, base_amount=amount))

    return subscriptions


def _extract_payment_totals_from_html(body_html: str) -> tuple[Decimal | None, Decimal | None]:
    section_match = PAYMENT_INFORMATION_SECTION_PATTERN.search(body_html)
    if section_match is None:
        return None, None

    section_tokens = _extract_p_text_tokens(section_match.group(0))
    if not section_tokens:
        return None, None

    tax_total = _find_amount_after_label(section_tokens, labels={"tax"})
    subtotal = _find_amount_after_label(section_tokens, labels={"subtotal"})
    grand_total = _find_amount_after_label(
        section_tokens,
        labels={"total", "order total", "amount charged", "charged"},
    )

    if grand_total is None:
        currency_amounts = [_extract_last_amount(token) for token in section_tokens]
        currency_amounts = [amount for amount in currency_amounts if amount is not None]
        if currency_amounts:
            grand_total = currency_amounts[-1]

    if tax_total is None and subtotal is not None and grand_total is not None:
        tax_total = (grand_total - subtotal).quantize(Decimal("0.01"))

    return tax_total, grand_total


def _extract_p_text_tokens(fragment_html: str) -> list[str]:
    tokens: list[str] = []
    for fragment in P_TAG_CONTENT_PATTERN.findall(fragment_html):
        text = _html_to_plain_text(fragment)
        for line in text.splitlines():
            normalized = clean_text(line)
            if normalized:
                tokens.append(normalized)
    return tokens


def _compose_subscription_description(tokens: list[str]) -> str | None:
    if not tokens:
        return None

    app_name = tokens[0]
    plan_name = None
    for token in tokens[1:]:
        if _is_subscription_metadata_noise(token):
            continue
        plan_name = token
        break

    if plan_name:
        return f"{app_name} - {plan_name}"
    return app_name


def _is_subscription_metadata_noise(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered.startswith("renews "):
        return True
    if lowered in {"hp-cell", "iphone", "ipad", "mac", "watch", "apple tv", "vision"}:
        return True
    return False


def _extract_amount_from_tokens(tokens: list[str]) -> Decimal | None:
    for token in reversed(tokens):
        amount = _extract_last_amount(token)
        if amount is not None:
            return amount
    return None


def _find_amount_after_label(tokens: list[str], labels: set[str]) -> Decimal | None:
    normalized_labels = {label.strip().lower() for label in labels}
    for idx, token in enumerate(tokens):
        lowered = token.strip().lower().rstrip(":")
        if lowered not in normalized_labels:
            continue
        for candidate in tokens[idx + 1 :]:
            amount = _extract_last_amount(candidate)
            if amount is not None:
                return amount
            if candidate.strip().endswith(":"):
                break
    return None


def _strip_style_and_script(html: str) -> str:
    return STYLE_SCRIPT_PATTERN.sub(" ", html)


def _html_to_plain_text(fragment_html: str) -> str:
    value = HTML_COMMENT_PATTERN.sub(" ", fragment_html)
    value = re.sub(r"<\s*br\s*/?\s*>", "\n", value, flags=re.IGNORECASE)
    value = HTML_TAG_PATTERN.sub(" ", value)
    value = html_lib.unescape(value)
    return value


def _extract_receipt_id(lines: list[str], path: Path) -> str:
    for line in lines:
        match = RECEIPT_ID_PATTERN.search(line)
        if match:
            return match.group(1).strip()
    return f"{DEFAULT_RECEIPT_PREFIX}-{path.stem}"


def _extract_date(lines: list[str]) -> date:
    date_candidates: list[str] = []
    for line in lines:
        date_candidates.extend(DATE_CANDIDATE_PATTERN.findall(line))
    for candidate in date_candidates:
        parsed = _parse_date(candidate)
        if parsed is not None:
            return parsed
    raise ReceiptParseError("Could not parse receipt date.")


def _parse_date(value: str) -> date | None:
    cleaned = value.strip()
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _extract_currency(lines: list[str], default_currency: str) -> str:
    for line in lines:
        if "$" in line or CURRENCY_AMOUNT_PATTERN.search(line):
            return "USD"
    return default_currency


def _extract_named_amount(
    lines: list[str],
    patterns: tuple[re.Pattern[str], ...],
    exclude_patterns: tuple[re.Pattern[str], ...] = (),
) -> Decimal | None:
    amounts: list[Decimal] = []
    for line in lines:
        if exclude_patterns and any(pattern.search(line) for pattern in exclude_patterns):
            continue
        if not any(pattern.search(line) for pattern in patterns):
            continue
        amount = _extract_last_amount(line)
        if amount is not None:
            amounts.append(amount)
    if not amounts:
        return None
    return amounts[-1]


def _extract_subscription_lines(lines: list[str]) -> list[SubscriptionLine]:
    subscriptions: list[SubscriptionLine] = []
    for line in lines:
        if any(pattern.search(line) for pattern in IGNORE_LINE_PATTERNS):
            continue
        amount = _extract_last_amount(line)
        if amount is None:
            continue
        description = _strip_last_amount(line)
        description = description.strip(":- ")
        if not description:
            continue
        subscriptions.append(SubscriptionLine(description=description, base_amount=amount))
    return subscriptions


def _extract_last_amount(line: str) -> Decimal | None:
    matches = list(AMOUNT_PATTERN.finditer(line))
    if not matches:
        return None
    return _parse_amount(matches[-1].group("amount"))


def _strip_last_amount(line: str) -> str:
    matches = list(AMOUNT_PATTERN.finditer(line))
    if not matches:
        return line
    return line[: matches[-1].start()]


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = raw.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _strip_leading_email_noise(lines: list[str]) -> list[str]:
    idx = 0
    max_scan = min(len(lines), 80)
    while idx < max_scan:
        line = lines[idx]
        if any(pattern.search(line) for pattern in LEADING_EMAIL_NOISE_PATTERNS):
            idx += 1
            continue
        if line.startswith(">"):
            idx += 1
            continue
        break
    return lines[idx:] if idx else lines


def _focus_receipt_section(lines: list[str]) -> list[str]:
    if len(lines) < 6:
        return lines

    candidate_indexes = [
        idx
        for idx, line in enumerate(lines[:240])
        if any(pattern.search(line) for pattern in SECTION_START_HINT_PATTERNS)
        and not any(pattern.search(line) for pattern in LEADING_EMAIL_NOISE_PATTERNS)
    ]
    for start_idx in candidate_indexes:
        end_idx = min(len(lines), start_idx + SECTION_SCAN_WINDOW_LINES)
        window = lines[start_idx:end_idx]
        if not _window_looks_like_receipt(window):
            continue

        total_line_offsets = [
            offset
            for offset, line in enumerate(window)
            if any(pattern.search(line) for pattern in TOTAL_LINE_PATTERNS)
            and not any(pattern.search(line) for pattern in TAX_LINE_PATTERNS)
            and _extract_last_amount(line) is not None
        ]
        if total_line_offsets:
            focused_end = min(
                len(lines),
                start_idx + total_line_offsets[-1] + SECTION_TOTAL_FOOTER_BUFFER_LINES,
            )
        else:
            focused_end = end_idx
        focused_start = start_idx
        return lines[focused_start:focused_end]

    return lines


def _window_looks_like_receipt(window: list[str]) -> bool:
    if not window:
        return False
    amount_line_count = sum(1 for line in window if _extract_last_amount(line) is not None)
    has_tax = _extract_named_amount(window, TAX_LINE_PATTERNS) is not None
    has_total = (
        _extract_named_amount(window, TOTAL_LINE_PATTERNS, exclude_patterns=TAX_LINE_PATTERNS)
        is not None
    )
    return amount_line_count >= 3 and has_tax and has_total
