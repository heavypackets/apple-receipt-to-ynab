from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

try:
    from rich.console import Console
except ModuleNotFoundError:  # pragma: no cover - covered by fallback behavior tests
    Console = None  # type: ignore[assignment]

_STDOUT_CONSOLE = Console() if Console is not None else None


def print_structured_stdout(value: dict[str, Any] | list[Any] | str) -> None:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            print(value)
            return
    else:
        parsed = value

    if _STDOUT_CONSOLE is not None:
        try:
            _STDOUT_CONSOLE.print_json(json=json.dumps(parsed, ensure_ascii=True, sort_keys=True))
            return
        except Exception:
            pass

    print(json.dumps(parsed, ensure_ascii=True, indent=2, sort_keys=True))


def append_log_block(path: Path | None, lines: Iterable[str], echo_stdout: bool = False) -> None:
    log_lines = list(lines)

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for line in log_lines:
                handle.write(f"{line}\n")

    if path is None or echo_stdout:
        for line in log_lines:
            print_structured_stdout(line)


def append_log_event(path: Path | None, event: dict[str, Any], echo_stdout: bool = False) -> None:
    line = json.dumps(event, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")

    if path is None or echo_stdout:
        print_structured_stdout(event)
