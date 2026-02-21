from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def append_log_block(path: Path | None, lines: Iterable[str], echo_stdout: bool = False) -> None:
    log_lines = list(lines)

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for line in log_lines:
                handle.write(f"{line}\n")

    if path is None or echo_stdout:
        for line in log_lines:
            print(line)


def append_log_event(path: Path | None, event: dict[str, Any], echo_stdout: bool = False) -> None:
    line = json.dumps(event, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")

    if path is None or echo_stdout:
        print(line)
