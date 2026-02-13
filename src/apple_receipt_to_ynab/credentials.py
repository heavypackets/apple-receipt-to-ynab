from __future__ import annotations

import os


def resolve_secret(cli_value: str | None, env_key: str, dotenv_values: dict[str, str]) -> str | None:
    return cli_value or os.getenv(env_key) or dotenv_values.get(env_key)

