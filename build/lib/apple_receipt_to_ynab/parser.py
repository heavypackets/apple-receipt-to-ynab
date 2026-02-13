from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pypdf import PdfReader

from apple_receipt_to_ynab.models import ParsedReceipt, SubscriptionLine
from apple_receipt_to_ynab.utils import clean_text

AMOUNT_PATTERN = re.compile(r"(?P<amount>[-+]?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})|[-+]?\$?\d+\.\d{2})")
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


class ReceiptParseError(ValueError):
    pass


def parse_receipt_pdf(path: Path, default_currency: str = "USD") -> ParsedReceipt:
    if not path.exists():
        raise ReceiptParseError(f"PDF not found: {path}")

    text = _extract_pdf_text(path)
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    if not lines:
        raise ReceiptParseError("PDF text extraction produced no usable lines.")

    receipt_id = _extract_receipt_id(lines, path)
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
        source_pdf=path,
        receipt_id=receipt_id,
        receipt_date=receipt_date,
        currency=currency,
        subscriptions=subscriptions,
        tax_total=tax_total,
        grand_total=grand_total,
        raw_text=text,
    )


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages_text = []
    for page in reader.pages:
        pages_text.append(page.extract_text() or "")
    return "\n".join(pages_text)


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
        if "$" in line:
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
