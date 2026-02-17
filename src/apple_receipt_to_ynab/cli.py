from __future__ import annotations

import argparse
import sys
from pathlib import Path

from apple_receipt_to_ynab.config import ConfigError
from apple_receipt_to_ynab.matcher import MappingMatchError, UnmappedSubscriptionError
from apple_receipt_to_ynab.parser import ReceiptParseError
from apple_receipt_to_ynab.service import ValidationError, process_receipt
from apple_receipt_to_ynab.tax import TaxAllocationError
from apple_receipt_to_ynab.ynab import YnabApiError


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    config_path = Path.cwd() / "config.yaml"
    if not config_path.exists():
        parser.error(f"Configuration file not found at '{config_path}'. Create config.yaml in the working directory.")

    try:
        result = process_receipt(
            receipt_path=args.receipt_path,
            config_path=config_path,
            dry_run=args.dry_run,
        )
    except UnmappedSubscriptionError as exc:
        print(f"Error (exit code 2): {exc}", file=sys.stderr)
        return 2
    except (ConfigError, ReceiptParseError, MappingMatchError, TaxAllocationError, ValidationError, YnabApiError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not args.dry_run:
        print(
            f"{result.status}: receipt={result.receipt_id} "
            f"amount_milliunits={result.parent_amount_milliunits} {result.message}"
        )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app-store-ynab",
        description="Parse Apple subscription receipt email files (.eml) and write YNAB transactions using config.yaml.",
    )
    parser.add_argument("receipt_path", type=Path, help="Path to local Apple receipt email file (.eml).")
    parser.add_argument("--dry-run", action="store_true", help="Parse and compute splits, but do not call YNAB API.")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
