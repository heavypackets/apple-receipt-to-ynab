from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

import httpx

from apple_receipt_to_ynab.models import SplitLine

YNAB_BASE_URL = "https://api.ynab.com/v1"


class YnabApiError(RuntimeError):
    pass


class YnabClient:
    def __init__(self, api_token: str, base_url: str = YNAB_BASE_URL) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def create_transaction(self, budget_id: str, transaction: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        response = self._client.post(f"/budgets/{budget_id}/transactions", json={"transaction": transaction})
        if response.status_code in (200, 201):
            return "created", response.json()
        if response.status_code == 409:
            return "duplicate-noop", _safe_json(response)
        raise YnabApiError(_format_error(response))


def build_import_id(receipt_id: str, receipt_date: date, grand_total_milliunits: int) -> str:
    seed = f"{receipt_id}|{receipt_date.isoformat()}|{grand_total_milliunits}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:24]
    return f"apple:{digest}"


def build_parent_transaction(
    account_id: str,
    receipt_id: str,
    receipt_date: date,
    split_lines: list[SplitLine],
    grand_total_milliunits: int,
    flag_color: str | None = None,
) -> dict[str, Any]:
    if not split_lines:
        raise ValueError("Cannot build YNAB transaction without split lines.")

    sign = -1 if grand_total_milliunits >= 0 else 1
    import_id = build_import_id(receipt_id=receipt_id, receipt_date=receipt_date, grand_total_milliunits=grand_total_milliunits)
    transaction: dict[str, Any] = {
        "account_id": account_id,
        "date": receipt_date.isoformat(),
        "cleared": "cleared",
        "approved": False,
        "import_id": import_id,
    }
    if flag_color is not None:
        transaction["flag_color"] = flag_color

    if len(split_lines) == 1:
        line = split_lines[0]
        transaction.update(
            {
                "amount": sign * abs(line.total_milliunits),
                "payee_id": line.ynab_payee_id,
                "payee_name": line.ynab_payee_name,
                "memo": f"Apple receipt {receipt_id}",
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
                "memo": "",
                "payee_id": line.ynab_payee_id,
                "payee_name": line.ynab_payee_name,
                "category_id": line.ynab_category_id,
            }
        )

    transaction.update(
        {
            "amount": sum(item["amount"] for item in subtransactions),
            "payee_name": "Apple",
            "memo": f"Apple receipt {receipt_id}",
            "category_id": None,
            "subtransactions": subtransactions,
        }
    )
    return transaction


def _format_error(response: httpx.Response) -> str:
    payload = _safe_json(response)
    return f"YNAB API {response.status_code}: {payload if payload else response.text}"


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        return {"raw": response.text}
    if isinstance(value, dict):
        return value
    return {"raw": value}
