from apple_receipt_to_ynab.credentials import resolve_secret


def test_resolve_secret_prefers_cli_value(monkeypatch) -> None:
    monkeypatch.setenv("YNAB_API_TOKEN", "env-token")
    value = resolve_secret("cli-token", "YNAB_API_TOKEN", {"YNAB_API_TOKEN": "dotenv-token"})
    assert value == "cli-token"


def test_resolve_secret_prefers_environment_over_dotenv(monkeypatch) -> None:
    monkeypatch.setenv("YNAB_API_TOKEN", "env-token")
    value = resolve_secret(None, "YNAB_API_TOKEN", {"YNAB_API_TOKEN": "dotenv-token"})
    assert value == "env-token"


def test_resolve_secret_uses_dotenv_fallback(monkeypatch) -> None:
    monkeypatch.delenv("YNAB_API_TOKEN", raising=False)
    value = resolve_secret(None, "YNAB_API_TOKEN", {"YNAB_API_TOKEN": "dotenv-token"})
    assert value == "dotenv-token"
