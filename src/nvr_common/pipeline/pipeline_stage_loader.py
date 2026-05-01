from __future__ import annotations

import importlib.util
from importlib import import_module
from pathlib import Path
from typing import Any

from nvr_common.pipeline.pipeline_stage import PipelineStage
from nvr_common.pipeline.pipeline_stage_config import PipelineStageConfig


class PipelineStageLoader:
    def load(self, stage_config: PipelineStageConfig) -> Any:
        if stage_config.pipeline:
            raise ValueError(
                f"stage {stage_config.id} references pipeline "
                f"{stage_config.pipeline} and is not directly loadable"
            )

        stage_class = self.load_stage_class(stage_config)
        stage = stage_class(stage_config.config)
        if not isinstance(stage, PipelineStage):
            raise TypeError(
                f"stage {stage_config.id} must inherit PipelineStage"
            )
        return stage

    def load_features(self, stage_config: PipelineStageConfig) -> list[str]:
        stage = self.load(stage_config)
        return sorted(feature.value for feature in stage.get_features())

    def load_stage_class(self, stage_config: PipelineStageConfig) -> type[Any]:
        if stage_config.filename:
            module = self._load_module_from_filename(stage_config.filename)
            class_name = stage_config.class_name or self._infer_class_name(
                stage_config.filename
            )
            return getattr(module, class_name)

        module = import_module(stage_config.module)
        return getattr(module, stage_config.class_name)

    @staticmethod
    def _load_module_from_filename(filename: str) -> Any:
        path = Path(filename)
        if path.exists():
            module_name = f"nvr_pipeline_stage_{path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load stage file: {filename}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        module_path = filename.removesuffix(".py").replace("/", ".")
        return import_module(module_path)

    @staticmethod
    def _infer_class_name(filename: str) -> str:
        stem = Path(filename).stem
        return "".join(part.capitalize() for part in stem.split("_"))
