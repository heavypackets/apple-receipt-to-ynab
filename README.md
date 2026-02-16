# apple-receipt-to-ynab

Local CLI tool that parses Apple App Store subscription receipt emails (`.eml`), maps each subscription line to YNAB category/payee rules in YAML, proportionally allocates receipt tax across lines, and creates one split transaction in YNAB.

## What it does

- Reads a local receipt file (`.eml` preferred, `.pdf` also supported).
- Extracts subscription lines, tax total, and grand total.
- Matches each subscription with `mappings.yaml` or `mappings.yml` in the working directory by default (or a path passed with `--config`).
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

1. Copy the example mapping file to your working directory:

```bash
cp examples/mappings.yaml ./mappings.yaml
```

1. Edit `mappings.yaml` (or rename to `mappings.yml`) for your categories, payees, and account IDs.
1. Provide `ynab_account_id`, category IDs, and payees.
1. Set environment variables:

```bash
export YNAB_API_TOKEN="your-token"
export YNAB_BUDGET_ID="your-budget-id"
```

You can also place these values in a `.env` file in the directory where you run the command:

```bash
YNAB_API_TOKEN=your-token
YNAB_BUDGET_ID=your-budget-id
```

Credential precedence is:
1. CLI flags (`--ynab-api-token`, `--ynab-budget-id`)
1. Exported environment variables
1. `.env` file in the current working directory

## Find YNAB IDs

Copy/paste these commands to find the IDs needed for `mappings.yaml`/`mappings.yml`.

List budgets (name + id):

```bash
curl -s -H "Authorization: Bearer $YNAB_API_TOKEN" \
  https://api.ynab.com/v1/budgets \
| jq -r '.data.budgets[] | [.name, .id] | @tsv'
```

List accounts in your selected budget (name + id):

```bash
curl -s -H "Authorization: Bearer $YNAB_API_TOKEN" \
  "https://api.ynab.com/v1/budgets/$YNAB_BUDGET_ID/accounts" \
| jq -r '.data.accounts[] | [.name, .id] | @tsv'
```

List categories in your selected budget (group + category + id):

```bash
curl -s -H "Authorization: Bearer $YNAB_API_TOKEN" \
  "https://api.ynab.com/v1/budgets/$YNAB_BUDGET_ID/categories" \
| jq -r '.data.category_groups[] | .name as $g | .categories[] | [$g, .name, .id] | @tsv'
```

If you do not have `jq` installed on macOS:

```bash
brew install jq
```

## Run

Dry run:

```bash
apple-receipt-to-ynab /path/to/apple_receipt.eml --dry-run
```

Write to YNAB:

```bash
apple-receipt-to-ynab /path/to/apple_receipt.eml
```

Optional overrides:

```bash
apple-receipt-to-ynab /path/to/apple_receipt.eml \
  --config /path/to/custom-mappings.yaml \
  --log logs/apple_receipt_to_ynab.log
```

## Notes

- Parent YNAB transaction amount is the sum of split line amounts.
- Split lines include per-line payee and category.
- For `.eml` imports, the parser reads MIME parts directly and parses the HTML receipt body (supports both `subscription-lockup__container` and `item-cell`/`price-cell` Apple receipt templates) after quoted-printable decoding.
- If you print emails to PDF, the parser strips common wrapper noise (for example `From:`, `Subject:`, `Page X of Y`, and trailing print footer text), but native `.eml` is more reliable.
- This parser uses heuristics and template-aware rules; if Apple changes email markup, update `src/apple_receipt_to_ynab/parser.py`.
