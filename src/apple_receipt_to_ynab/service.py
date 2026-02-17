from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apple_receipt_to_ynab.config import load_config
from apple_receipt_to_ynab.logger import append_log_block
from apple_receipt_to_ynab.matcher import match_subscriptions
from apple_receipt_to_ynab.models import MappingConfig, MatchedSubscription, ParsedReceipt, SplitLine, SubscriptionLine
from apple_receipt_to_ynab.parser import parse_receipt_file
from apple_receipt_to_ynab.tax import build_split_lines
from apple_receipt_to_ynab.utils import dollars_to_milliunits, milliunits_to_dollars, now_local_iso
from apple_receipt_to_ynab.ynab import YnabApiError, build_parent_transaction


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


def process_receipt(
    receipt_path: Path,
    config_path: Path,
    dry_run: bool,
) -> ProcessResult:
    log_path: Path | None = None
    try:
        runtime_config = load_config(config_path)
        config = runtime_config.mappings
        log_path = runtime_config.app.log_path

        receipt = parse_receipt_file(receipt_path, default_currency=config.defaults.default_currency)
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
        if not dry_run:
            client = YnabClient(
                api_token=runtime_config.ynab.api_token,
                base_url=runtime_config.ynab.api_url,
            )
            try:
                result_status, api_payload = client.create_transaction(
                    budget_id=runtime_config.ynab.budget_id,
                    transaction=transaction,
                )
                status = result_status
                transaction_id = _extract_transaction_id(api_payload)
                message = f"Posted transaction {transaction_id}."
            finally:
                client.close()

        append_log_block(
            log_path,
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
        )
    except Exception as exc:
        append_log_block(
            log_path,
            [
                f"[{now_local_iso()}] RUN START",
                f"Receipt File: {receipt_path}",
                f"Result: FAILED {exc}",
                "RUN END",
                "",
            ],
        )
        raise


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


def _resolve_ynab_flag_color(config: MappingConfig, matched: list[MatchedSubscription]) -> str | None:
    if (
        config.fallback
        and config.fallback.ynab_flag_color
        and any(item.mapping_rule_id == "fallback" for item in matched)
    ):
        return config.fallback.ynab_flag_color
    return config.defaults.ynab_flag_color
