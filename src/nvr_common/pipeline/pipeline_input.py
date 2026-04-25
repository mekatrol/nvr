from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PipelineInput:
    original_image: Any
    current_image: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    camera_id: str = ""
    frame_id: str = ""
    frame_timestamp: datetime | None = None
    source_pipeline_id: str | None = None
