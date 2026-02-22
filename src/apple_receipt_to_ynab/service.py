from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from apple_receipt_to_ynab.config import load_config
from apple_receipt_to_ynab.gmail_client import GmailMessage, fetch_gmail_messages
from apple_receipt_to_ynab.logger import append_log_event
from apple_receipt_to_ynab.matcher import match_subscriptions
from apple_receipt_to_ynab.models import MappingConfig, MatchedSubscription, ParsedReceipt, RuntimeConfig, SplitLine, SubscriptionLine
from apple_receipt_to_ynab.parser import parse_receipt_bytes, parse_receipt_file
from apple_receipt_to_ynab.tax import build_split_lines
from apple_receipt_to_ynab.utils import dollars_to_milliunits, milliunits_to_dollars, now_local_iso
from apple_receipt_to_ynab.ynab import YnabApiError, build_parent_transaction

TransactionKey = tuple[str, str, int, str]
YNAB_REQUEST_TIMEOUT_SECONDS = 10
YNAB_MAX_RETRIES = 2
YNAB_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


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
    log_to_stdout: bool = False,
) -> ProcessResult:
    log_path: Path | None = None
    source_label = str(receipt_path) if receipt_path is not None else "email://batch"
    try:
        runtime_config = load_config(config_path)
        log_path = None if log_to_stdout else runtime_config.app.log_path

        if runtime_config.app.mode == "email":
            return _process_gmail_batch(runtime_config=runtime_config, dry_run=dry_run, log_to_stdout=log_to_stdout)

        if receipt_path is None:
            raise ValidationError("receipt_path is required when app.mode is 'local'.")
        return _process_local_file_receipt(
            receipt_path=receipt_path,
            runtime_config=runtime_config,
            dry_run=dry_run,
            log_to_stdout=log_to_stdout,
        )
    except Exception as exc:
        append_log_event(
            log_path,
            {
                "timestamp": now_local_iso(),
                "event_name": "receipt_run_failed",
                "source_label": source_label,
                "status": "failed",
                "error_message": str(exc),
            },
        )
        raise


def _process_local_file_receipt(
    receipt_path: Path, runtime_config: RuntimeConfig, dry_run: bool, log_to_stdout: bool
) -> ProcessResult:
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
        log_to_stdout=log_to_stdout,
    )


def _process_gmail_batch(runtime_config: RuntimeConfig, dry_run: bool, log_to_stdout: bool) -> ProcessResult:
    config = runtime_config.mappings
    log_path = None if log_to_stdout else runtime_config.app.log_path
    gmail_messages = fetch_gmail_messages(runtime_config.email)
    if not gmail_messages:
        append_log_event(
            log_path,
            {
                "timestamp": now_local_iso(),
                "event_name": "gmail_batch_noop",
                "source_label": "email://batch",
                "mode": "dry_run" if dry_run else "live_post",
                "status": "noop",
                "message": "No Gmail messages matched configured filter.",
            },
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
            log_to_stdout=log_to_stdout,
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
    log_to_stdout: bool = False,
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

    append_log_event(
        None if log_to_stdout else runtime_config.app.log_path,
        _build_log_event(
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


def _build_log_event(
    receipt: ParsedReceipt,
    split_lines: list[SplitLine],
    ynab_budget_id: str,
    ynab_account_id: str,
    status: str,
    message: str,
    transaction_id: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for line in split_lines:
        item: dict[str, Any] = {
            "source_description": line.source_description,
            "base_amount": str(milliunits_to_dollars(line.base_milliunits)),
            "tax_amount": str(milliunits_to_dollars(line.tax_milliunits)),
            "total_amount": str(milliunits_to_dollars(line.total_milliunits)),
            "ynab_category_id": line.ynab_category_id,
            "mapping_rule_id": line.mapping_rule_id,
        }
        if line.ynab_payee_id is not None:
            item["ynab_payee_id"] = line.ynab_payee_id
        if line.ynab_payee_name is not None:
            item["ynab_payee_name"] = line.ynab_payee_name
        items.append(item)

    base_total = sum(line.base_milliunits for line in split_lines)
    tax_total = sum(line.tax_milliunits for line in split_lines)
    grand_total = sum(line.total_milliunits for line in split_lines)
    event: dict[str, Any] = {
        "timestamp": now_local_iso(),
        "event_name": "receipt_processed",
        "mode": "dry_run" if dry_run else "live_post",
        "source_label": str(receipt.source_pdf),
        "status": status.lower(),
        "message": message,
        "receipt": {
            "receipt_id": receipt.receipt_id,
            "receipt_date": receipt.receipt_date.isoformat(),
            "currency": receipt.currency,
        },
        "items": items,
        "totals": {
            "base_amount": str(milliunits_to_dollars(base_total)),
            "tax_amount": str(milliunits_to_dollars(tax_total)),
            "grand_total_amount": str(milliunits_to_dollars(grand_total)),
            "reconciled": grand_total == dollars_to_milliunits(receipt.grand_total),
        },
        "ynab": {
            "budget_id": ynab_budget_id,
            "account_id": ynab_account_id,
        },
    }
    if transaction_id is not None:
        event["transaction_id"] = transaction_id
    return event


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
    api_exception = getattr(ynab, "ApiException", None)
    try:
        response = _run_ynab_api_call_with_retries(
            operation_name="create_transaction",
            call=lambda: _create_ynab_transaction_request(
                ynab_module=ynab,
                configuration=configuration,
                ynab_budget_id=ynab_budget_id,
                wrapper=wrapper,
            ),
            api_exception=api_exception,
        )
    except Exception as exc:
        raise _build_ynab_api_error("create_transaction", exc, api_exception) from exc

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
    api_exception = getattr(ynab, "ApiException", None)
    try:
        response = _run_ynab_api_call_with_retries(
            operation_name="list_transactions",
            call=lambda: _list_ynab_transactions_request(
                ynab_module=ynab,
                configuration=configuration,
                ynab_budget_id=ynab_budget_id,
                account_id=account_id,
                since_date=since_date,
            ),
            api_exception=api_exception,
        )
    except Exception as exc:
        raise _build_ynab_api_error("list_transactions", exc, api_exception) from exc

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


def _create_ynab_transaction_request(
    ynab_module: Any,
    configuration: Any,
    ynab_budget_id: str,
    wrapper: Any,
) -> Any:
    with ynab_module.ApiClient(configuration) as api_client:
        api = ynab_module.TransactionsApi(api_client)
        return api.create_transaction(
            ynab_budget_id,
            wrapper,
            _request_timeout=YNAB_REQUEST_TIMEOUT_SECONDS,
        )


def _list_ynab_transactions_request(
    ynab_module: Any,
    configuration: Any,
    ynab_budget_id: str,
    account_id: str,
    since_date: date,
) -> Any:
    with ynab_module.ApiClient(configuration) as api_client:
        api = ynab_module.TransactionsApi(api_client)
        return api.get_transactions_by_account(
            budget_id=ynab_budget_id,
            account_id=account_id,
            since_date=since_date,
            _request_timeout=YNAB_REQUEST_TIMEOUT_SECONDS,
        )


def _run_ynab_api_call_with_retries(
    operation_name: str,
    call: Any,
    api_exception: type[BaseException] | None,
) -> Any:
    for attempt in range(YNAB_MAX_RETRIES + 1):
        try:
            return call()
        except Exception as exc:
            if not _is_retryable_ynab_exception(exc, api_exception) or attempt >= YNAB_MAX_RETRIES:
                raise
            time.sleep(0.25 * (2**attempt))
    raise RuntimeError(f"Unexpected retry loop exit for {operation_name}.")


def _is_retryable_ynab_exception(
    exc: Exception,
    api_exception: type[BaseException] | None,
) -> bool:
    if _is_connectivity_exception(exc):
        return True
    if api_exception is None or not isinstance(exc, api_exception):
        return False

    status = getattr(exc, "status", None)
    if isinstance(status, int) and status in YNAB_RETRYABLE_STATUS_CODES:
        return True
    return _is_connectivity_exception(getattr(exc, "reason", None))


def _is_connectivity_exception(exc: object) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout)):
        return True
    try:
        from urllib3 import exceptions as urllib3_exceptions  # type: ignore
    except Exception:
        return False
    return isinstance(
        exc,
        (
            urllib3_exceptions.ConnectTimeoutError,
            urllib3_exceptions.MaxRetryError,
            urllib3_exceptions.NewConnectionError,
            urllib3_exceptions.ProtocolError,
            urllib3_exceptions.ReadTimeoutError,
        ),
    )


def _build_ynab_api_error(
    operation_name: str,
    exc: Exception,
    api_exception: type[BaseException] | None,
) -> YnabApiError:
    if _is_connectivity_exception(exc):
        if operation_name == "create_transaction":
            return YnabApiError(
                "Could not connect to the YNAB API while creating the transaction. "
                "We could not confirm whether YNAB saved the transaction. "
                "Please check YNAB before retrying."
            )
        return YnabApiError(
            "Could not connect to the YNAB API while loading existing transactions. No actions were taken."
        )

    if api_exception is not None and isinstance(exc, api_exception):
        reason = getattr(exc, "reason", None)
        if _is_connectivity_exception(reason):
            if operation_name == "create_transaction":
                return YnabApiError(
                    "Could not connect to the YNAB API while creating the transaction. "
                    "We could not confirm whether YNAB saved the transaction. "
                    "Please check YNAB before retrying."
                )
            return YnabApiError(
                "Could not connect to the YNAB API while loading existing transactions. No actions were taken."
            )
        status = getattr(exc, "status", None)
        status_text = str(status) if status is not None else "unknown"
        error_body = getattr(exc, "body", None) or reason or str(exc)
        if operation_name == "create_transaction":
            return YnabApiError(
                f"YNAB API request failed (status {status_text}): {error_body}. No transaction was created."
            )
        return YnabApiError(
            f"YNAB API request failed (status {status_text}): {error_body}. No actions were taken."
        )

    if operation_name == "create_transaction":
        return YnabApiError(
            f"Could not create the YNAB transaction: {exc}. No transaction was created."
        )
    return YnabApiError(
        f"Could not load transactions from YNAB: {exc}. No actions were taken."
    )
