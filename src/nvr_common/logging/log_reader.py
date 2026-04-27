from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class LogReader:
    LOG_LINE_PATTERN = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
        r"\[(?P<level>[A-Z]+)\] (?P<logger>[^:]+): (?P<message>.*)$"
    )

    def __init__(self, log_file_path: Path) -> None:
        self.log_file_path = log_file_path

    def entries(self, limit: int = 500) -> list[dict[str, Any]]:
        if not self.log_file_path.exists():
            return []

        entries: list[dict[str, Any]] = []
        for line in self._tail_lines(limit * 4):
            match = self.LOG_LINE_PATTERN.match(line.rstrip("\n"))
            if match is None:
                if entries:
                    entries[-1]["description"] = (
                        f"{entries[-1]['description']}\n{line.rstrip()}"
                    )
                continue

            entries.append(
                {
                    "timestamp": match.group("timestamp"),
                    "level": match.group("level"),
                    "description": f"{match.group('logger')}: {match.group('message')}",
                }
            )

        return list(reversed(entries[-limit:]))

    def clear(self) -> None:
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file_path.write_text("", encoding="utf-8")

    def _tail_lines(self, line_count: int) -> list[str]:
        with self.log_file_path.open("r", encoding="utf-8", errors="replace") as file:
            return file.readlines()[-line_count:]
