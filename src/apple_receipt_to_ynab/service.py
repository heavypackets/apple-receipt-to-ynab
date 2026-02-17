from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from apple_receipt_to_ynab.config import load_config
from apple_receipt_to_ynab.gmail_client import GmailMessage, fetch_gmail_messages
from apple_receipt_to_ynab.logger import append_log_block
from apple_receipt_to_ynab.matcher import match_subscriptions
from apple_receipt_to_ynab.models import MappingConfig, MatchedSubscription, ParsedReceipt, RuntimeConfig, SplitLine, SubscriptionLine
from apple_receipt_to_ynab.parser import parse_receipt_bytes, parse_receipt_file
from apple_receipt_to_ynab.tax import build_split_lines
from apple_receipt_to_ynab.utils import dollars_to_milliunits, milliunits_to_dollars, now_local_iso
from apple_receipt_to_ynab.ynab import YnabApiError, build_parent_transaction

TransactionKey = tuple[str, str, int, str]


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    status: str
    message: str
    receipt_id: str
    parent_amount_milliunits: int
    parsed_subscriptions: tuple[SubscriptionLine, ...]
    transaction_id: str | None = None
    processed_count: int = 1
    created_count: int = 0
    duplicate_count: int = 0
    failed_count: int = 0


def process_receipt(
    receipt_path: Path | None,
    config_path: Path,
    dry_run: bool,
) -> ProcessResult:
    log_path: Path | None = None
    source_label = str(receipt_path) if receipt_path is not None else "email://batch"
    try:
        runtime_config = load_config(config_path)
        log_path = runtime_config.app.log_path

        if runtime_config.app.mode == "email":
            return _process_gmail_batch(runtime_config=runtime_config, dry_run=dry_run)

        if receipt_path is None:
            raise ValidationError("receipt_path is required when app.mode is 'local'.")
        return _process_local_file_receipt(
            receipt_path=receipt_path,
            runtime_config=runtime_config,
            dry_run=dry_run,
        )
    except Exception as exc:
        append_log_block(
            log_path,
            [
                f"[{now_local_iso()}] RUN START",
                f"Receipt File: {source_label}",
                f"Result: FAILED {exc}",
                "RUN END",
                "",
            ],
        )
        raise


def _process_local_file_receipt(receipt_path: Path, runtime_config: RuntimeConfig, dry_run: bool) -> ProcessResult:
    config = runtime_config.mappings
    receipt = parse_receipt_file(receipt_path, default_currency=config.defaults.default_currency)

    existing_transactions = _load_existing_transaction_index(
        runtime_config=runtime_config,
        account_id=config.defaults.ynab_account_id,
        dry_run=dry_run,
    )
    return _process_parsed_receipt(
        receipt=receipt,
        runtime_config=runtime_config,
        dry_run=dry_run,
        existing_transactions=existing_transactions,
    )


def _process_gmail_batch(runtime_config: RuntimeConfig, dry_run: bool) -> ProcessResult:
    config = runtime_config.mappings
    gmail_messages = fetch_gmail_messages(runtime_config.email)
    if not gmail_messages:
        append_log_block(
            runtime_config.app.log_path,
            [
                f"[{now_local_iso()}] RUN START",
                "Receipt File: email://batch",
                "Mode: DRY_RUN (no YNAB API call)" if dry_run else "Mode: LIVE_POST",
                "Result: noop No Gmail messages matched configured filter.",
                "RUN END",
                "",
            ],
            echo_stdout=dry_run,
        )
        return ProcessResult(
            status="noop",
            message="No Gmail messages matched configured filter.",
            receipt_id="GMAIL-BATCH",
            parent_amount_milliunits=0,
            parsed_subscriptions=(),
            processed_count=0,
            created_count=0,
            duplicate_count=0,
            failed_count=0,
        )

    existing_transactions = _load_existing_transaction_index(
        runtime_config=runtime_config,
        account_id=config.defaults.ynab_account_id,
        dry_run=dry_run,
    )
    processed_count = 0
    created_count = 0
    duplicate_count = 0
    for message in gmail_messages:
        parsed = _parse_gmail_message(message, default_currency=config.defaults.default_currency)
        result = _process_parsed_receipt(
            receipt=parsed,
            runtime_config=runtime_config,
            dry_run=dry_run,
            existing_transactions=existing_transactions,
        )
        processed_count += 1
        if result.status == "created":
            created_count += 1
        elif result.status == "duplicate":
            duplicate_count += 1

    status = "DRY_RUN" if dry_run else "created"
    message = (
        f"Processed {processed_count} Gmail receipts. "
        f"Created={created_count} duplicate_skipped={duplicate_count}."
    )
    return ProcessResult(
        status=status,
        message=message,
        receipt_id="GMAIL-BATCH",
        parent_amount_milliunits=0,
        parsed_subscriptions=(),
        processed_count=processed_count,
        created_count=created_count,
        duplicate_count=duplicate_count,
        failed_count=0,
    )


def _parse_gmail_message(message: GmailMessage, default_currency: str) -> ParsedReceipt:
    source_name = Path(f"gmail-{message.message_id}.eml")
    return parse_receipt_bytes(
        raw_bytes=message.raw_bytes,
        source_name=source_name,
        default_currency=default_currency,
    )


def _process_parsed_receipt(
    receipt: ParsedReceipt,
    runtime_config: RuntimeConfig,
    dry_run: bool,
    existing_transactions: dict[TransactionKey, str | None] | None,
) -> ProcessResult:
    config = runtime_config.mappings
    matched = match_subscriptions(receipt.subscriptions, config)
    split_lines = build_split_lines(matched, receipt.tax_total)
    grand_total_milliunits = dollars_to_milliunits(receipt.grand_total)

    transaction = build_parent_transaction(
        account_id=config.defaults.ynab_account_id,
        receipt_id=receipt.receipt_id,
        receipt_date=receipt.receipt_date,
        split_lines=split_lines,
        grand_total_milliunits=grand_total_milliunits,
        ynab_flag_color=_resolve_ynab_flag_color(config, matched),
    )
    _validate_totals(receipt, split_lines, transaction["amount"])

    status = "DRY_RUN"
    message = "Dry run completed. No transaction posted."
    transaction_id = None
    created_count = 0
    duplicate_count = 0
    if not dry_run:
        key = _build_transaction_key_from_payload(transaction)
        if existing_transactions is not None and key in existing_transactions:
            status = "duplicate"
            transaction_id = existing_transactions[key]
            duplicate_count = 1
            if transaction_id:
                message = f"Duplicate transaction already exists in YNAB ({transaction_id}). Skipped create."
            else:
                message = "Duplicate transaction already exists in YNAB. Skipped create."
        else:
            transaction_id = _post_ynab_transaction(
                ynab_budget_id=runtime_config.ynab.budget_id,
                ynab_api_token=runtime_config.ynab.api_token,
                ynab_api_url=runtime_config.ynab.api_url,
                transaction=transaction,
            )
            status = "created"
            created_count = 1
            message = f"Posted transaction {transaction_id}."
            if existing_transactions is not None:
                existing_transactions[key] = transaction_id

    append_log_block(
        runtime_config.app.log_path,
        _build_log_lines(
            receipt=receipt,
            split_lines=split_lines,
            ynab_budget_id=runtime_config.ynab.budget_id,
            ynab_account_id=config.defaults.ynab_account_id,
            status=status,
            message=message,
            transaction_id=transaction_id,
            dry_run=dry_run,
        ),
        echo_stdout=dry_run,
    )

    return ProcessResult(
        status=status,
        message=message,
        receipt_id=receipt.receipt_id,
        parent_amount_milliunits=transaction["amount"],
        parsed_subscriptions=tuple(receipt.subscriptions),
        transaction_id=transaction_id,
        processed_count=1,
        created_count=created_count,
        duplicate_count=duplicate_count,
        failed_count=0,
    )


def _validate_totals(receipt: ParsedReceipt, split_lines: list[SplitLine], parent_amount_milliunits: int) -> None:
    split_total_milliunits = sum(line.total_milliunits for line in split_lines)
    expected_grand_total_milliunits = dollars_to_milliunits(receipt.grand_total)

    if split_total_milliunits != expected_grand_total_milliunits:
        raise ValidationError(
            f"Split totals do not match receipt grand total. Split={split_total_milliunits}, "
            f"Receipt={expected_grand_total_milliunits}."
        )

    expected_parent_amount = (
        -abs(split_total_milliunits)
        if expected_grand_total_milliunits >= 0
        else abs(split_total_milliunits)
    )
    if parent_amount_milliunits != expected_parent_amount:
        raise ValidationError(
            f"Parent transaction amount mismatch. Parent={parent_amount_milliunits}, "
            f"Expected={expected_parent_amount}."
        )


def _build_log_lines(
    receipt: ParsedReceipt,
    split_lines: list[SplitLine],
    ynab_budget_id: str,
    ynab_account_id: str,
    status: str,
    message: str,
    transaction_id: str | None,
    dry_run: bool,
) -> list[str]:
    lines = [f"[{now_local_iso()}] RUN START", f"Receipt File: {receipt.source_pdf}"]
    lines.append("Mode: DRY_RUN (no YNAB API call)" if dry_run else "Mode: LIVE_POST")
    lines.append(
        "Receipt: "
        f"id={receipt.receipt_id} date={receipt.receipt_date.isoformat()} currency={receipt.currency}"
    )
    lines.append("Items:")
    for line in split_lines:
        label = line.ynab_payee_name or line.ynab_payee_id or line.source_description
        lines.append(
            "- "
            f"{label} | "
            f"source={line.source_description} | "
            f"base={milliunits_to_dollars(line.base_milliunits)} | "
            f"tax={milliunits_to_dollars(line.tax_milliunits)} | "
            f"total={milliunits_to_dollars(line.total_milliunits)} | "
            f"category={line.ynab_category_id} | "
            f"payee={line.ynab_payee_id or line.ynab_payee_name or 'none'}"
        )

    base_total = sum(line.base_milliunits for line in split_lines)
    tax_total = sum(line.tax_milliunits for line in split_lines)
    grand_total = sum(line.total_milliunits for line in split_lines)
    lines.append(
        "Totals: "
        f"base={milliunits_to_dollars(base_total)} "
        f"tax={milliunits_to_dollars(tax_total)} "
        f"grand={milliunits_to_dollars(grand_total)} "
        f"reconciled={'yes' if grand_total == dollars_to_milliunits(receipt.grand_total) else 'no'}"
    )
    lines.append(f"YNAB: budget={ynab_budget_id} account={ynab_account_id}")
    if transaction_id:
        lines.append(f"Result: {status} transaction_id={transaction_id}")
    else:
        lines.append(f"Result: {status} {message}")
    lines.append("RUN END")
    lines.append("")
    return lines


def _extract_transaction_id(payload: object) -> str | None:
    data = getattr(payload, "data", None)
    transaction = getattr(data, "transaction", None)
    value = getattr(transaction, "id", None)
    if isinstance(value, str):
        return value

    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict):
        transaction = data.get("transaction")
        if isinstance(transaction, dict):
            value = transaction.get("id")
            if isinstance(value, str):
                return value
    return None


def _post_ynab_transaction(
    ynab_budget_id: str,
    ynab_api_token: str,
    ynab_api_url: str,
    transaction: dict[str, Any],
) -> str | None:
    try:
        import ynab
    except ModuleNotFoundError as exc:
        raise YnabApiError("The 'ynab' package is required. Install dependencies with `pip install -e .`.") from exc

    subtransactions_raw = transaction.get("subtransactions")
    subtransactions = None
    if isinstance(subtransactions_raw, list):
        subtransactions = [
            ynab.SaveSubTransaction(
                amount=int(item["amount"]),
                payee_id=item.get("payee_id"),
                payee_name=item.get("payee_name"),
                category_id=item.get("category_id"),
            )
            for item in subtransactions_raw
            if isinstance(item, dict)
        ]

    parent_payload = {key: value for key, value in transaction.items() if key != "subtransactions"}
    if subtransactions is not None:
        parent_payload["subtransactions"] = subtransactions
    wrapper = ynab.PostTransactionsWrapper(transaction=ynab.NewTransaction(**parent_payload))

    configuration = ynab.Configuration(access_token=ynab_api_token)
    configuration.host = ynab_api_url.rstrip("/")
    try:
        with ynab.ApiClient(configuration) as api_client:
            api = ynab.TransactionsApi(api_client)
            response = api.create_transaction(ynab_budget_id, wrapper)
    except Exception as exc:
        api_exception = getattr(ynab, "ApiException", None)
        if api_exception is not None and isinstance(exc, api_exception):
            status = getattr(exc, "status", "unknown")
            error_body = getattr(exc, "body", None) or getattr(exc, "reason", None) or str(exc)
            raise YnabApiError(f"YNAB API {status}: {error_body}") from exc
        raise

    return _extract_transaction_id(response)


def _load_existing_transaction_index(
    runtime_config: RuntimeConfig,
    account_id: str,
    dry_run: bool,
) -> dict[TransactionKey, str | None] | None:
    if dry_run:
        return None

    since_date = date.today() - timedelta(days=runtime_config.ynab.lookback_days)
    transactions = _list_ynab_transactions_by_account(
        ynab_budget_id=runtime_config.ynab.budget_id,
        ynab_api_token=runtime_config.ynab.api_token,
        ynab_api_url=runtime_config.ynab.api_url,
        account_id=account_id,
        since_date=since_date,
    )
    index: dict[TransactionKey, str | None] = {}
    for item in transactions:
        key = _build_transaction_key_from_ynab(item)
        if key is None:
            continue
        index[key] = _extract_ynab_transaction_id(item)
    return index


def _list_ynab_transactions_by_account(
    ynab_budget_id: str,
    ynab_api_token: str,
    ynab_api_url: str,
    account_id: str,
    since_date: date,
) -> list[Any]:
    try:
        import ynab
    except ModuleNotFoundError as exc:
        raise YnabApiError("The 'ynab' package is required. Install dependencies with `pip install -e .`.") from exc

    configuration = ynab.Configuration(access_token=ynab_api_token)
    configuration.host = ynab_api_url.rstrip("/")
    try:
        with ynab.ApiClient(configuration) as api_client:
            api = ynab.TransactionsApi(api_client)
            response = api.get_transactions_by_account(
                budget_id=ynab_budget_id,
                account_id=account_id,
                since_date=since_date,
            )
    except Exception as exc:
        api_exception = getattr(ynab, "ApiException", None)
        if api_exception is not None and isinstance(exc, api_exception):
            status = getattr(exc, "status", "unknown")
            error_body = getattr(exc, "body", None) or getattr(exc, "reason", None) or str(exc)
            raise YnabApiError(f"YNAB API {status}: {error_body}") from exc
        raise

    data = getattr(response, "data", None)
    transactions = getattr(data, "transactions", None)
    if isinstance(transactions, list):
        return transactions

    if isinstance(response, dict):
        data_dict = response.get("data")
        if isinstance(data_dict, dict):
            transactions = data_dict.get("transactions")
            if isinstance(transactions, list):
                return transactions
    return []


def _build_transaction_key_from_payload(transaction: dict[str, Any]) -> TransactionKey:
    account_id = transaction.get("account_id")
    date_iso = transaction.get("date")
    amount = transaction.get("amount")
    memo = transaction.get("memo")
    if not isinstance(account_id, str):
        raise ValidationError("Transaction payload missing account_id for dedupe key.")
    if not isinstance(date_iso, str):
        raise ValidationError("Transaction payload missing date for dedupe key.")
    if not isinstance(amount, int):
        raise ValidationError("Transaction payload missing amount for dedupe key.")
    if not isinstance(memo, str):
        raise ValidationError("Transaction payload missing memo for dedupe key.")
    return (account_id, date_iso, amount, memo)


def _build_transaction_key_from_ynab(transaction: Any) -> TransactionKey | None:
    if isinstance(transaction, dict):
        account_id = transaction.get("account_id")
        amount = transaction.get("amount")
        memo = transaction.get("memo")
        date_value = transaction.get("date")
    else:
        account_id = getattr(transaction, "account_id", None)
        amount = getattr(transaction, "amount", None)
        memo = getattr(transaction, "memo", None)
        date_value = getattr(transaction, "var_date", None) or getattr(transaction, "date", None)

    if not isinstance(account_id, str) or not isinstance(amount, int) or not isinstance(memo, str):
        return None

    if isinstance(date_value, date):
        date_iso = date_value.isoformat()
    elif isinstance(date_value, str):
        date_iso = date_value
    else:
        return None
    return (account_id, date_iso, amount, memo)


def _extract_ynab_transaction_id(transaction: Any) -> str | None:
    if isinstance(transaction, dict):
        tx_id = transaction.get("id")
        return tx_id if isinstance(tx_id, str) else None
    tx_id = getattr(transaction, "id", None)
    return tx_id if isinstance(tx_id, str) else None


def _resolve_ynab_flag_color(config: MappingConfig, matched: list[MatchedSubscription]) -> str | None:
    if (
        config.fallback
        and config.fallback.ynab_flag_color
        and any(item.mapping_rule_id == "fallback" for item in matched)
    ):
        return config.fallback.ynab_flag_color
    return config.defaults.ynab_flag_color
