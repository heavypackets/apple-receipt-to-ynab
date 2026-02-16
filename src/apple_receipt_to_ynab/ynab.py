from __future__ import annotations

from datetime import date
from typing import Any

from apple_receipt_to_ynab.models import SplitLine


class YnabApiError(RuntimeError):
    pass

def build_parent_transaction(
    account_id: str,
    receipt_id: str,
    receipt_date: date,
    split_lines: list[SplitLine],
    grand_total_milliunits: int,
    ynab_flag_color: str | None = None,
) -> dict[str, Any]:
    if not split_lines:
        raise ValueError("Cannot build YNAB transaction without split lines.")

    sign = -1 if grand_total_milliunits >= 0 else 1
    transaction: dict[str, Any] = {
        "account_id": account_id,
        "date": receipt_date.isoformat(),
        "cleared": "cleared",
        "approved": False,
    }
    if ynab_flag_color is not None:
        transaction["flag_color"] = ynab_flag_color

    if len(split_lines) == 1:
        line = split_lines[0]
        transaction.update(
            {
                "amount": sign * abs(line.total_milliunits),
                "payee_id": line.ynab_payee_id,
                "payee_name": line.ynab_payee_name,
                "memo": f"Receipt: {receipt_id}",
                "category_id": line.ynab_category_id,
            }
        )
        return transaction

    subtransactions = []
    for line in split_lines:
        line_total = abs(line.total_milliunits)
        sub_amount = sign * line_total
        subtransactions.append(
            {
                "amount": sub_amount,
                "payee_id": line.ynab_payee_id,
                "payee_name": line.ynab_payee_name,
                "category_id": line.ynab_category_id,
            }
        )

    transaction.update(
        {
            "amount": sum(item["amount"] for item in subtransactions),
            "payee_name": "Apple",
            "memo": f"Receipt: {receipt_id}",
            "category_id": None,
            "subtransactions": subtransactions,
        }
    )
    return transaction
