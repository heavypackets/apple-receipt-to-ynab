from pathlib import Path

from apple_receipt_to_ynab.paths import resolve_mapping_config_path


def test_resolve_mapping_config_uses_cli_override(tmp_path: Path) -> None:
    custom = tmp_path / "custom.yaml"
    assert resolve_mapping_config_path(custom, tmp_path) == custom


def test_resolve_mapping_config_prefers_yml_when_present(tmp_path: Path) -> None:
    yml = tmp_path / "mappings.yml"
    yaml = tmp_path / "mappings.yaml"
    yml.write_text("version: 1\n", encoding="utf-8")
    yaml.write_text("version: 1\n", encoding="utf-8")

    resolved = resolve_mapping_config_path(None, tmp_path)
    assert resolved == yml


def test_resolve_mapping_config_falls_back_to_yaml(tmp_path: Path) -> None:
    yaml = tmp_path / "mappings.yaml"
    yaml.write_text("version: 1\n", encoding="utf-8")

    resolved = resolve_mapping_config_path(None, tmp_path)
    assert resolved == yaml

