from __future__ import annotations

import argparse
import sys
from pathlib import Path

from apple_receipt_to_ynab.config import ConfigError
from apple_receipt_to_ynab.credentials import resolve_secret
from apple_receipt_to_ynab.dotenv import load_dotenv
from apple_receipt_to_ynab.matcher import MappingMatchError
from apple_receipt_to_ynab.models import SubscriptionLine
from apple_receipt_to_ynab.parser import ReceiptParseError
from apple_receipt_to_ynab.paths import resolve_mapping_config_path
from apple_receipt_to_ynab.service import ValidationError, process_receipt
from apple_receipt_to_ynab.tax import TaxAllocationError
from apple_receipt_to_ynab.ynab import YnabApiError


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    config_path = resolve_mapping_config_path(args.config, Path.cwd())

    dotenv_values = load_dotenv(Path.cwd() / ".env")

    api_token = resolve_secret(args.ynab_api_token, "YNAB_API_TOKEN", dotenv_values)
    if not api_token:
        parser.error(
            "YNAB API token is required via --ynab-api-token, YNAB_API_TOKEN, or .env in the working directory."
        )

    budget_id = resolve_secret(args.ynab_budget_id, "YNAB_BUDGET_ID", dotenv_values)
    if not budget_id:
        parser.error(
            "YNAB budget id is required via --ynab-budget-id, YNAB_BUDGET_ID, or .env in the working directory."
        )
    if not config_path.exists():
        parser.error(
            f"Mapping config not found at '{config_path}'. "
            "Provide --config, or create mappings.yml or mappings.yaml in the working directory."
        )

    try:
        result = process_receipt(
            receipt_path=args.receipt_path,
            config_path=config_path,
            log_path=args.log,
            ynab_budget_id=budget_id,
            ynab_api_token=api_token,
            dry_run=args.dry_run,
            reimport=args.reimport,
        )
    except (ConfigError, ReceiptParseError, MappingMatchError, TaxAllocationError, ValidationError, YnabApiError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run_subscriptions(result.parsed_subscriptions)

    print(
        f"{result.status}: receipt={result.receipt_id} import_id={result.import_id} "
        f"amount_milliunits={result.parent_amount_milliunits} {result.message}"
    )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apple-receipt-to-ynab",
        description="Parse Apple subscription receipt email files (.eml) and write YNAB transactions.",
    )
    parser.add_argument("receipt_path", type=Path, help="Path to local Apple receipt email file (.eml).")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to YAML mapping config. Default: auto-detect mappings.yml or mappings.yaml in working directory.",
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
    parser.add_argument(
        "--reimport",
        action="store_true",
        help="If YNAB returns duplicate import_id (409), retry with randomized receipt_id#NN suffix values to force a new import_id.",
    )
    return parser


def _print_dry_run_subscriptions(subscriptions: tuple[SubscriptionLine, ...]) -> None:
    print("Parsed subscriptions:")
    for idx, item in enumerate(subscriptions, start=1):
        print(f"{idx}. {item.description} | {item.base_amount:.2f}")


if __name__ == "__main__":
    raise SystemExit(main())
