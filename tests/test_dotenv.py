from pathlib import Path

from apple_receipt_to_ynab.dotenv import load_dotenv


def test_load_dotenv_parses_basic_and_export_lines(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "YNAB_API_TOKEN=token123",
                "export YNAB_BUDGET_ID=budget456",
            ]
        ),
        encoding="utf-8",
    )

    values = load_dotenv(env_path)

    assert values["YNAB_API_TOKEN"] == "token123"
    assert values["YNAB_BUDGET_ID"] == "budget456"


def test_load_dotenv_handles_quotes_and_inline_comments(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                'YNAB_API_TOKEN="quoted token"',
                "YNAB_BUDGET_ID=budget123   # inline comment",
            ]
        ),
        encoding="utf-8",
    )

    values = load_dotenv(env_path)

    assert values["YNAB_API_TOKEN"] == "quoted token"
    assert values["YNAB_BUDGET_ID"] == "budget123"

