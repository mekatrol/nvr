from __future__ import annotations

import importlib.util
from importlib import import_module
from pathlib import Path
from typing import Any

from nvr_common.pipeline.pipeline_stage_config import PipelineStageConfig


class PipelineStageLoader:
    def load(self, stage_config: PipelineStageConfig) -> Any:
        if stage_config.pipeline:
            raise ValueError(
                f"stage {stage_config.id} references pipeline "
                f"{stage_config.pipeline} and is not directly loadable"
            )

        if stage_config.filename:
            module = self._load_module_from_filename(stage_config.filename)
            class_name = stage_config.class_name or self._infer_class_name(
                stage_config.filename
            )
            stage_class = getattr(module, class_name)
            return stage_class(stage_config.config)

        module = import_module(stage_config.module)
        stage_class = getattr(module, stage_config.class_name)
        return stage_class(stage_config.config)

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
