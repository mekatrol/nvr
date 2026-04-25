from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from nvr_common.pipeline.pipeline_input import PipelineInput


@dataclass(frozen=True)
class PipelineContext:
    camera_id: str
    frame_id: str
    original_image: Any
    current_image: Any
    metadata: dict[str, Any]
    pipeline_id: str
    stage_id: str
    frame_timestamp: datetime | None = None
    upstream_inputs: dict[str, PipelineInput] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    logger: Any = None
