from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PipelineOutput:
    pipeline_id: str
    output_image: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    debug_artifacts: dict[str, Any] = field(default_factory=dict)
    events: tuple[Any, ...] = field(default_factory=tuple)
    status: str = "completed"
    elapsed_seconds: float = 0.0
    camera_id: str = ""
    frame_id: str = ""
    frame_timestamp: datetime | None = None
