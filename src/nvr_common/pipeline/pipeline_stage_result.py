from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PipelineStageResult:
    output_image: Any = None
    metadata_updates: dict[str, Any] = field(default_factory=dict)
    debug_artifacts: dict[str, Any] = field(default_factory=dict)
    events: tuple[Any, ...] = field(default_factory=tuple)
