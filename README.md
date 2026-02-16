# apple-receipt-to-ynab

Local CLI tool that parses Apple App Store subscription receipt emails (`.eml`), maps each subscription line to YNAB category/payee rules in YAML, proportionally allocates receipt tax across lines, and creates one YNAB transaction (single-line or split).

## What it does

- Reads a local receipt email file (`.eml`).
- Extracts subscription lines, tax total, and grand total.
- Matches each subscription with `mappings.yaml` or `mappings.yml` in the working directory by default (or a path passed with `--config`).
- Splits tax proportionally across subscription lines using largest-remainder reconciliation.
- Creates one regular transaction when there is one subscription, or one split transaction when there are multiple subscriptions.
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
1. Every `rules[]` entry must include a valid `ynab_payee_name`.
1. If `fallback.enabled` is `true` (or omitted), `fallback.ynab_payee_name` is required.
1. Optional: set `fallback.ynab_flag_color` to flag transactions that include unmapped subscriptions resolved by fallback.
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
  --log logs/apple_receipt_to_ynab.log \
  --reimport
```

## Notes

- A single subscription receipt produces a non-split YNAB transaction.
- Single-subscription transaction `payee_name` is always taken from mapping and does not fallback to `Apple`.
- A multi-subscription receipt produces a split YNAB transaction.
- For multi-subscription receipts, only the parent transaction has a memo (`Apple receipt <receipt_id>`).
- If fallback is used for any subscription and `fallback.ynab_flag_color` is set, the YNAB transaction is flagged (valid colors: `red`, `orange`, `yellow`, `green`, `blue`, `purple`).
- `--reimport` allows reposting a duplicate receipt by retrying with randomized `receipt_id#NN` variants to generate a new `import_id` after a YNAB 409 duplicate response.
- The parser reads MIME parts directly and parses the HTML receipt body (supports both `subscription-lockup__container` and `item-cell`/`price-cell` Apple receipt templates) after quoted-printable decoding.
- This parser uses heuristics and template-aware rules; if Apple changes email markup, update `src/apple_receipt_to_ynab/parser.py`.
