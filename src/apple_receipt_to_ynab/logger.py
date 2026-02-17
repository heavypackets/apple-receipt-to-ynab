from __future__ import annotations

from pathlib import Path
from typing import Iterable


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
