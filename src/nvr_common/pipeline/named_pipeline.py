from __future__ import annotations

from dataclasses import dataclass, field

from nvr_common.pipeline.pipeline_stage_config import PipelineStageConfig


@dataclass(frozen=True)
class NamedPipeline:
    id: str
    name: str = ""
    stages: tuple[PipelineStageConfig, ...] = field(default_factory=tuple)
    enabled: bool = True
    required_inputs: tuple[str, ...] = field(default_factory=tuple)
