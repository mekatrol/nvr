from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path
from shutil import copy2
from typing import Any

import yaml

from nvr_common.config import Config
from nvr_common.pipeline import PipelineGraph


class PipelinesStore:
    EXAMPLE_RESIZE_STAGE_FILENAME = "example_resize_stage.py"
    DEFAULT_FRAME_INTERVAL_SECONDS = 0.5

    def __init__(self, config: Config) -> None:
        self.config = config
        self.config_path = Path(config.config_path)
        self.storage_path = config.get_pipeline_config_storage_path()
        self.pipelines_dir = self.storage_path / "pipelines"
        self.deployed_dir = self.storage_path / "deployed"
        self.pipelines_path = self.pipelines_dir / "pipelines.yaml"
        self.deployed_path = config.get_deployed_pipelines_path()
        self.pipeline_conf_path = config.get_pipeline_config_path()
        self.pipelines_dir.mkdir(parents=True, exist_ok=True)
        self.deployed_dir.mkdir(parents=True, exist_ok=True)

    def pipeline_config_response(self) -> dict[str, Any]:
        pipelines_config = self.load_pipeline_config_pipelines()
        return self.pipelines_response(pipelines_config)

    def pipeline_config_graph(self) -> PipelineGraph | None:
        pipelines_config = self.load_pipeline_config_pipelines()
        if pipelines_config.get(Config.KEY_PIPELINES_ENABLED) is False:
            return None
        graph = Config._parse_pipelines(pipelines_config)
        graph.validate()
        return graph

    def deployed_response(self) -> dict[str, Any]:
        pipelines_config = self.config.get_pipelines_config()
        if not pipelines_config:
            return {"enabled": False, "pipelines": [], "edges": []}
        return self.pipelines_response(pipelines_config)

    def load_pipeline_config_pipelines(self) -> dict[str, Any]:
        if self.pipelines_path.exists():
            data = self._load_yaml(self.pipelines_path)
            pipelines_config = Config._unwrap_pipelines_config(data)
        else:
            pipelines_config = self.config.get_pipelines_config() or {
                Config.KEY_PIPELINES_ENABLED: True,
                Config.KEY_PIPELINE_FRAME_INTERVAL_SECONDS: (
                    self.DEFAULT_FRAME_INTERVAL_SECONDS
                ),
                Config.KEY_PIPELINES: [],
                Config.KEY_PIPELINE_EDGES: [],
            }

        return self._normalize_pipelines_config(pipelines_config)

    def save_pipeline_config_pipelines(self, raw_pipelines: dict[str, Any]) -> dict[str, Any]:
        pipelines_config = self._normalize_pipelines_config(raw_pipelines)
        self._validate_pipelines_config(pipelines_config)
        self._write_yaml(self.pipelines_path, pipelines_config)
        return self.pipelines_response(pipelines_config)

    def deploy_pipeline_config_pipelines(self) -> dict[str, Any]:
        pipelines_config = self.load_pipeline_config_pipelines()
        self._validate_pipelines_config(pipelines_config)
        deployed_config = self._copy_stage_files_to_deployed(pipelines_config)
        self._validate_pipelines_config(deployed_config)
        self._write_yaml(self.deployed_path, deployed_config)
        return self.pipelines_response(deployed_config)

    def generate_example_resize_pipeline(self) -> dict[str, Any]:
        stage_path = self.pipelines_dir / self.EXAMPLE_RESIZE_STAGE_FILENAME
        stage_path.write_text(self._example_resize_stage_source(), encoding="utf-8")

        pipelines_config = self.load_pipeline_config_pipelines()
        pipelines_config[Config.KEY_PIPELINES_ENABLED] = True
        pipelines_config[Config.KEY_PIPELINE_FRAME_INTERVAL_SECONDS] = (
            self.DEFAULT_FRAME_INTERVAL_SECONDS
        )
        pipelines = pipelines_config.setdefault(Config.KEY_PIPELINES, [])
        pipelines[:] = [
            pipeline
            for pipeline in pipelines
            if pipeline.get("id") != "example-resize"
        ]
        pipelines.append(self._example_resize_pipeline_config(stage_path))
        self._validate_pipelines_config(pipelines_config)
        self._write_yaml(self.pipelines_path, pipelines_config)
        return self.pipelines_response(pipelines_config)

    def pipelines_response(self, pipelines_config: dict[str, Any]) -> dict[str, Any]:
        pipelines_config = self._normalize_pipelines_config(pipelines_config)
        graph = Config._parse_pipelines(pipelines_config)
        return {
            "enabled": pipelines_config.get(Config.KEY_PIPELINES_ENABLED, True),
            "frame_interval_seconds": pipelines_config.get(
                Config.KEY_PIPELINE_FRAME_INTERVAL_SECONDS
            ),
            "pipelines_path": str(self.pipelines_path),
            "deployed_path": str(self.deployed_path),
            "pipeline_conf_path": str(self.pipeline_conf_path),
            "config_path": str(self.config_path),
            "pipelines_config": pipelines_config,
            "pipelines": [
                {
                    "id": pipeline.id,
                    "name": getattr(pipeline, "name", pipeline.id),
                    "enabled": pipeline.enabled,
                    "required_inputs": list(pipeline.required_inputs),
                    "stages": [
                        {
                            "id": stage.id,
                            "enabled": stage.enabled,
                            "module": stage.module,
                            "class_name": stage.class_name,
                            "filename": stage.filename,
                            "pipeline": stage.pipeline,
                            "config": deepcopy(stage.config),
                        }
                        for stage in pipeline.stages
                    ],
                }
                for pipeline in graph.pipelines
            ],
            "edges": [{"from": edge.source, "to": edge.target} for edge in graph.edges],
        }

    def _validate_pipelines_config(
        self, pipelines_config: dict[str, Any]
    ) -> PipelineGraph:
        errors: list[str] = []
        self.config._validate_pipelines(pipelines_config, "pipelines", errors)
        if errors:
            raise ValueError("Invalid pipelines:\n- " + "\n- ".join(errors))
        graph = Config._parse_pipelines(pipelines_config)
        graph.validate()
        return graph

    @staticmethod
    def _normalize_pipelines_config(raw_pipelines: dict[str, Any]) -> dict[str, Any]:
        return Config._normalize_pipelines_config(deepcopy(raw_pipelines))

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _write_yaml(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        yaml_data = deepcopy(data)
        yaml_data.pop(Config.KEY_PIPELINES_PIPELINE, None)
        rendered = yaml.safe_dump(yaml_data, sort_keys=False)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as temp_file:
            temp_file.write(rendered)
            temp_path = Path(temp_file.name)
        temp_path.replace(path)

    def _copy_stage_files_to_deployed(
        self, pipelines_config: dict[str, Any]
    ) -> dict[str, Any]:
        deployed_config = deepcopy(pipelines_config)
        for pipeline in deployed_config.get(Config.KEY_PIPELINES, []):
            if not isinstance(pipeline, dict):
                continue
            for stage in pipeline.get("stages", []):
                if not isinstance(stage, dict):
                    continue
                filename = stage.get("filename")
                if not isinstance(filename, str) or not filename:
                    continue
                source_path = Path(filename)
                if not source_path.exists():
                    continue
                deployed_path = self.deployed_dir / source_path.name
                copy2(source_path, deployed_path)
                stage["filename"] = str(deployed_path)
        return deployed_config

    @staticmethod
    def _example_resize_pipeline_config(stage_path: Path) -> dict[str, Any]:
        return {
            "id": "example-resize",
            "name": "Example resize",
            "enabled": True,
            "stages": [
                {
                    "id": "resize-frame",
                    "enabled": True,
                    "filename": str(stage_path),
                    "class": "ExampleResizeStage",
                    "config": {
                        "output_width": 640,
                        "output_height": 360,
                    },
                }
            ],
        }

    @staticmethod
    def _example_resize_stage_source() -> str:
        return '''from __future__ import annotations

from typing import Any

import cv2

from nvr_common.pipeline import PipelineContext, PipelineStageResult


class ExampleResizeStage:
    def __init__(self, config: dict[str, Any]) -> None:
        self.output_width = self._read_size(config, "output_width")
        self.output_height = self._read_size(config, "output_height")

    def process(self, context: PipelineContext) -> PipelineStageResult:
        source_image = context.current_image
        source_height, source_width = source_image.shape[:2]
        resized_image = cv2.resize(
            source_image,
            (self.output_width, self.output_height),
            interpolation=cv2.INTER_AREA,
        )
        return PipelineStageResult(
            output_image=resized_image,
            metadata_updates={
                "example_resize": {
                    "source_width": source_width,
                    "source_height": source_height,
                    "output_width": self.output_width,
                    "output_height": self.output_height,
                }
            },
        )

    @staticmethod
    def _read_size(config: dict[str, Any], key: str) -> int:
        value = config.get(key)
        if not isinstance(value, int) or value < 1:
            raise ValueError(f"{key} must be an integer >= 1")
        return value
'''
