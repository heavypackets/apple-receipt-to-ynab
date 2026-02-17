# app-store-ynab

Local CLI tool that parses Apple App Store subscription receipt emails (`.eml`), maps each subscription line to YNAB category/payee rules in YAML, proportionally allocates receipt tax across lines, and creates one YNAB transaction (single-line or split).

## What it does

- Reads a local receipt email file (`.eml`).
- Loads configuration only from `./config.yaml` in the current working directory.
- Extracts subscription lines, tax total, and grand total.
- Matches each subscription against mapping rules in `config.yaml`.
- Splits tax proportionally across subscription lines using largest-remainder reconciliation.
- Creates one regular transaction for one subscription, or one split transaction for multiple subscriptions.
- Logs runs to a file when `app.log_path` is set; otherwise logs to stdout.
- In `--dry-run`, always prints the structured run log to stdout and does not call YNAB.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

## Configure

1. Copy the example config:

```bash
cp example-config.yaml ./config.yaml
```

1. Edit `config.yaml` for your YNAB token/budget/account/category/payee mappings.
1. Every `mappings.rules[]` entry must include a valid `ynab_payee_name`.
1. If `mappings.fallback.enabled` is `true` (or omitted), `mappings.fallback.ynab_payee_name` is required.
1. Optional: set `mappings.defaults.ynab_flag_color` to apply a default flag to created transactions.
1. If `app.log_path` is omitted, logging defaults to stdout.

### `config.yaml` schema

```yaml
version: 1

ynab:
  api_token: "your-token"
  budget_id: "your-budget-id"
  api_url: "https://api.ynab.com/v1" # optional

app:
  log_path: "app_store_ynab.log" # optional; stdout when omitted

mappings:
  defaults:
    ynab_account_id: "your-account-id"
    ynab_category_id: "optional-default-fallback-category-id"
    ynab_flag_color: "blue" # optional default flag color
    currency: "USD"
  rules:
    - id: apple_music
      enabled: true
      match:
        type: exact
        value: "Apple Music"
      ynab_category_id: "cat-id"
      ynab_payee_name: "Apple Music"
  fallback:
    enabled: true
    ynab_category_id: "cat-id"
    ynab_payee_name: "Apple"
    ynab_flag_color: "yellow"
```

## Find YNAB IDs

Set shell variables for convenience when running lookup commands:

```bash
export TOKEN="your-token"
export BUDGET_ID="your-budget-id"
```

List budgets (name + id):

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  https://api.ynab.com/v1/budgets \
| jq -r '.data.budgets[] | [.name, .id] | @tsv'
```

List accounts in your selected budget (name + id):

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.ynab.com/v1/budgets/$BUDGET_ID/accounts" \
| jq -r '.data.accounts[] | [.name, .id] | @tsv'
```

List categories in your selected budget (group + category + id):

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.ynab.com/v1/budgets/$BUDGET_ID/categories" \
| jq -r '.data.category_groups[] | .name as $g | .categories[] | [$g, .name, .id] | @tsv'
```

If you do not have `jq` installed on macOS:

```bash
brew install jq
```

## Run

Dry run:

```bash
app-store-ynab /path/to/apple_receipt.eml --dry-run
```

Write to YNAB:

```bash
app-store-ynab /path/to/apple_receipt.eml
```

## Notes

- The app requires `config.yaml` in the current working directory.
- `ynab.api_url` defaults to `https://api.ynab.com/v1` when omitted.
- Single-subscription transaction `payee_name` is taken from mapping and does not fallback to `Apple`.
- For multi-subscription receipts, only the parent transaction has a memo (`Receipt: <receipt_id>`).
- If `mappings.defaults.ynab_flag_color` is set, created transactions are flagged by default.
- If fallback is used and `mappings.fallback.ynab_flag_color` is set, fallback color overrides the default flag color.
- Transactions are posted without `import_id`, so YNAB treats them as user-entered.
- HTTP 409 responses are treated as normal API errors (same as other non-2xx responses).
- Transaction posting uses the official Python `ynab` SDK.
- If fallback is not enabled and any subscription is unmapped, the CLI exits with code `2`.
- Dry-run logs include `Mode: DRY_RUN (no YNAB API call)` and are printed to stdout.
- The parser reads MIME parts directly and parses the HTML receipt body (supports both `subscription-lockup__container` and `item-cell`/`price-cell` Apple receipt templates) after quoted-printable decoding.
