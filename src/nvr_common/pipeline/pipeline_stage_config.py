from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PipelineStageConfig:
    id: str
    module: str
    class_name: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
