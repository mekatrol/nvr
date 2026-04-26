from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StageDebugRecord:
    camera_id: str
    frame_id: str
    pipeline_id: str
    stage_id: str
    status: str
    metadata_before: dict[str, Any] = field(default_factory=dict)
    metadata_after: dict[str, Any] = field(default_factory=dict)
    input_shape: tuple[int, ...] | None = None
    output_shape: tuple[int, ...] | None = None
    input_preview: str | None = None
    output_preview: str | None = None
