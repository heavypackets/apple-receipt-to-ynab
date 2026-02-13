# apple-receipt-to-ynab

Local CLI tool that parses Apple App Store subscription receipt PDFs, maps each subscription line to friendly names via YAML rules, proportionally allocates receipt tax across lines, and creates one split transaction in YNAB.

## What it does

- Reads a local receipt PDF.
- Extracts subscription lines, tax total, and grand total.
- Matches each subscription with `config/mappings.yaml`.
- Splits tax proportionally across subscription lines using largest-remainder reconciliation.
- Creates one parent transaction with split subtransactions in YNAB.
- Appends a plain text log entry for each run.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configure

1. Copy and edit `config/mappings.yaml`.
1. Provide `ynab_account_id`, category IDs, and payees.
1. Set environment variables:

```bash
export YNAB_API_TOKEN="your-token"
export YNAB_BUDGET_ID="your-budget-id"
```

## Run

Dry run:

```bash
apple-receipt-to-ynab /path/to/apple_receipt.pdf --dry-run
```

Write to YNAB:

```bash
apple-receipt-to-ynab /path/to/apple_receipt.pdf
```

Optional overrides:

```bash
apple-receipt-to-ynab /path/to/apple_receipt.pdf \
  --config config/mappings.yaml \
  --log logs/apple_receipt_to_ynab.log
```

## Notes

- Parent YNAB transaction amount is the sum of split line amounts.
- Split lines include per-line payee and category.
- This parser uses heuristics; if your Apple PDF format differs, update parser patterns in `src/apple_receipt_to_ynab/parser.py`.
