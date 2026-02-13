from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from apple_receipt_to_ynab.config import ConfigError
from apple_receipt_to_ynab.matcher import MappingMatchError
from apple_receipt_to_ynab.parser import ReceiptParseError
from apple_receipt_to_ynab.service import ValidationError, process_receipt
from apple_receipt_to_ynab.tax import TaxAllocationError
from apple_receipt_to_ynab.ynab import YnabApiError


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    api_token = args.ynab_api_token or os.getenv("YNAB_API_TOKEN")
    if not api_token:
        parser.error("YNAB API token is required via --ynab-api-token or YNAB_API_TOKEN.")

    budget_id = args.ynab_budget_id or os.getenv("YNAB_BUDGET_ID")
    if not budget_id:
        parser.error("YNAB budget id is required via --ynab-budget-id or YNAB_BUDGET_ID.")

    try:
        result = process_receipt(
            pdf_path=args.pdf_path,
            config_path=args.config,
            log_path=args.log,
            ynab_budget_id=budget_id,
            ynab_api_token=api_token,
            dry_run=args.dry_run,
        )
    except (ConfigError, ReceiptParseError, MappingMatchError, TaxAllocationError, ValidationError, YnabApiError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"{result.status}: receipt={result.receipt_id} import_id={result.import_id} "
        f"amount_milliunits={result.parent_amount_milliunits} {result.message}"
    )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apple-receipt-to-ynab",
        description="Parse Apple subscription receipt PDFs and write YNAB split transactions.",
    )
    parser.add_argument("pdf_path", type=Path, help="Path to local Apple receipt PDF.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/mappings.yaml"),
        help="Path to YAML mapping config.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("logs/apple_receipt_to_ynab.log"),
        help="Append-only text log path.",
    )
    parser.add_argument("--ynab-api-token", type=str, default=None, help="YNAB API token. Optional if YNAB_API_TOKEN is set.")
    parser.add_argument("--ynab-budget-id", type=str, default=None, help="YNAB budget id. Optional if YNAB_BUDGET_ID is set.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and compute splits, but do not call YNAB API.")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
