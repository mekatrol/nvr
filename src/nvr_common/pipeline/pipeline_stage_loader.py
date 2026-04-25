from __future__ import annotations

from importlib import import_module
from typing import Any

from nvr_common.pipeline.pipeline_stage_config import PipelineStageConfig


class PipelineStageLoader:
    def load(self, stage_config: PipelineStageConfig) -> Any:
        module = import_module(stage_config.module)
        stage_class = getattr(module, stage_config.class_name)
        return stage_class(stage_config.config)
