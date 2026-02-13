from __future__ import annotations

from pathlib import Path


def resolve_mapping_config_path(cli_value: Path | None, cwd: Path) -> Path:
    if cli_value is not None:
        return cli_value

    yml = cwd / "mappings.yml"
    yaml = cwd / "mappings.yaml"
    if yml.exists():
        return yml
    if yaml.exists():
        return yaml
    return yml

