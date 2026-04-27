from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PipelineStageConfig:
    id: str
    enabled: bool = True
    module: str = ""
    class_name: str = ""
    filename: str | None = None
    pipeline: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
