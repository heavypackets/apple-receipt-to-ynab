from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apple_receipt_to_ynab.config import ConfigError, load_config
from apple_receipt_to_ynab.gmail_client import GmailApiError
from apple_receipt_to_ynab.matcher import MappingMatchError, UnmappedSubscriptionError
from apple_receipt_to_ynab.parser import ReceiptParseError
from apple_receipt_to_ynab.service import ValidationError, process_receipt
from apple_receipt_to_ynab.tax import TaxAllocationError
from apple_receipt_to_ynab.ynab import YnabApiError


class FriendlyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse exits by design
        self.print_usage(sys.stderr)
        self.exit(2, f"Error: {message}\n")


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    config_path = Path.cwd() / "config.yaml"
    if not config_path.exists():
        parser.error(
            f"Could not find 'config.yaml' at '{config_path}'. "
            "Create a config.yaml file in the current working directory."
        )

    try:
        runtime_config = load_config(config_path)
        if runtime_config.app.mode == "local" and args.receipt_path is None:
            print(
                "Error: Missing required argument 'receipt_path' when app.mode is 'local'.",
                file=sys.stderr,
            )
            return 1
        if runtime_config.app.mode == "email" and args.receipt_path is not None:
            print(
                "Error: Do not provide 'receipt_path' when app.mode is 'email'.",
                file=sys.stderr,
            )
            return 1

        result = process_receipt(
            receipt_path=args.receipt_path,
            config_path=config_path,
            dry_run=args.dry_run,
        )
    except UnmappedSubscriptionError as exc:
        print(f"Error (exit code 2): {exc}", file=sys.stderr)
        return 2
    except (
        ConfigError,
        GmailApiError,
        ReceiptParseError,
        MappingMatchError,
        TaxAllocationError,
        ValidationError,
        YnabApiError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not args.dry_run:
        print(
            json.dumps(
                {
                    "event_name": "cli_process_result",
                    "status": result.status.lower(),
                    "receipt_id": result.receipt_id,
                    "parent_amount_milliunits": result.parent_amount_milliunits,
                    "message": result.message,
                    "transaction_id": result.transaction_id,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = FriendlyArgumentParser(
        prog="app-store-ynab",
        description=(
            "Parse Apple subscription receipts from local .eml files or Gmail API and "
            "write YNAB transactions using config.yaml."
        ),
    )
    parser.add_argument(
        "receipt_path",
        nargs="?",
        type=Path,
        help="Path to local Apple receipt email file (.eml). Required when app.mode=local.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and compute splits, but do not call YNAB API.")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
