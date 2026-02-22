import json
from pathlib import Path

from apple_receipt_to_ynab.logger import append_log_block, append_log_event


def test_append_log_event_stdout_pretty_prints_json(capsys) -> None:
    append_log_event(path=None, event={"z": 1, "a": {"b": 2}}, echo_stdout=False)

    output = capsys.readouterr().out
    assert "\n" in output
    assert '  "a"' in output
    payload = json.loads(output)
    assert payload["a"]["b"] == 2
    assert payload["z"] == 1


def test_append_log_event_file_stays_compact_json_line(tmp_path: Path) -> None:
    log_path = tmp_path / "run.log"
    append_log_event(path=log_path, event={"b": 2, "a": 1}, echo_stdout=False)

    log_text = log_path.read_text(encoding="utf-8")
    assert log_text == '{"a":1,"b":2}\n'


def test_append_log_block_pretty_prints_json_lines_only(capsys) -> None:
    append_log_block(
        path=None,
        lines=['{"x":1}', "plain line"],
        echo_stdout=False,
    )

    output = capsys.readouterr().out
    assert '  "x"' in output
    assert "plain line" in output
