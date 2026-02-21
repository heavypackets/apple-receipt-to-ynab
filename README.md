# app-store-ynab

Local CLI tool that parses Apple App Store subscription receipts from local `.eml` files or Gmail, maps each subscription with rules in the configuration, and creates the appropriate YNAB transactions.

## What it does

- Reads a local receipt email file (`.eml`) or fetches recent receipt emails from Gmail API.
- Matches each subscription against mapping rules in `config.yaml`.
- Creates one transaction for receipts with one subscription, or one split transaction for multiple subscription receipts.
- Prevents duplicate transactions by looking up recent YNAB transactions (7 days prior by default).
- With the `--dry-run` argument, always prints the processing log to stdout and does not make calls to YNAB.

## Install using pipx
```bash
./install_app.sh
```

## Configure

1. Create your config file at `~/.asy/config.yaml`:

```bash
mkdir -p ~/.asy
cp example-config.yaml ~/.asy/config.yaml
```

1. Edit `~/.asy/config.yaml` with your YNAB credentials, budget information and subscription mappings.
1. `app.mode` controls receipt source: `local` expects a receipt path argument, while `email` reads receipts from your Gmail account.

### `config.yaml` schema

```yaml
version: 1

ynab:
  api_token: "your-token"
  budget_id: "your-budget-id"
  api_url: "https://api.ynab.com/v1" # optional
  lookback_days: 7 # optional

app:
  mode: "local" # "local" or "email"
  log_path: "app_store_ynab.log" # optional; stdout when omitted

email: # required only when app.mode=email
  subject_filter: "Your receipt from Apple." # optional
  sender_filter: "no_reply@email.apple.com" # optional
  max_age_days: 7 # optional
  service_account_key_path: "./gmail-service-account.json"
  delegated_user_email: "finance-bot@example.com"
  max_results: 10 # optional
  query_extra: "in:inbox" # optional

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

### Notes

- If `app.log_path` is omitted, logging defaults to stdout.
- If fallback is used and `mappings.fallback.ynab_flag_color` is set, fallback color overrides the default flag color.

## Run

By default, the app reads config from `~/.asy/config.yaml`.
Use `--config /path/to/config.yaml` to override.

Local receipts:

```bash
app-store-ynab /path/to/apple_receipt.eml
```

Dry run:

```bash
app-store-ynab /path/to/apple_receipt.eml --dry-run
```

Email mode (set `app.mode: email` in config):

```bash
app-store-ynab --dry-run
app-store-ynab
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
