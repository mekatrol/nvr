from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from nvr_common.config import Config
from nvr_common.pipeline import PipelineGraph


class PipelinesStore:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.config_path = Path(config.config_path)
        self.storage_path = config.get_pipelines_storage_path()
        self.draft_path = self.storage_path / "pipelines.draft.yaml"
        self.deployed_path = self.storage_path / "pipelines.deployed.yaml"

    def draft_response(self) -> dict[str, Any]:
        pipelines_config = self.load_draft_pipelines()
        return self.pipelines_response(pipelines_config)

    def deployed_response(self) -> dict[str, Any]:
        pipelines_config = self.config.get_pipelines_config()
        if not pipelines_config:
            return {"enabled": False, "pipelines": [], "edges": []}
        return self.pipelines_response(pipelines_config)

    def load_draft_pipelines(self) -> dict[str, Any]:
        if self.draft_path.exists():
            data = self._load_yaml(self.draft_path)
            pipelines_config = Config._unwrap_pipelines_config(data)
        else:
            pipelines_config = self.config.get_pipelines_config() or {
                Config.KEY_PIPELINES_ENABLED: True,
                Config.KEY_PIPELINE_FRAME_INTERVAL_SECONDS: 1.0,
                Config.KEY_PIPELINES: [],
                Config.KEY_PIPELINE_EDGES: [],
            }

        return self._normalize_pipelines_config(pipelines_config)

    def save_draft_pipelines(self, raw_pipelines: dict[str, Any]) -> dict[str, Any]:
        pipelines_config = self._normalize_pipelines_config(raw_pipelines)
        self._validate_pipelines_config(pipelines_config)
        self._write_yaml(self.draft_path, pipelines_config)
        return self.pipelines_response(pipelines_config)

    def deploy_draft_pipelines(self) -> dict[str, Any]:
        pipelines_config = self.load_draft_pipelines()
        self._validate_pipelines_config(pipelines_config)
        self._write_yaml(self.deployed_path, pipelines_config)
        return self.pipelines_response(pipelines_config)

    def pipelines_response(self, pipelines_config: dict[str, Any]) -> dict[str, Any]:
        pipelines_config = self._normalize_pipelines_config(pipelines_config)
        graph = Config._parse_pipelines(pipelines_config)
        return {
            "enabled": pipelines_config.get(Config.KEY_PIPELINES_ENABLED, True),
            "frame_interval_seconds": pipelines_config.get(
                Config.KEY_PIPELINE_FRAME_INTERVAL_SECONDS
            ),
            "draft_path": str(self.draft_path),
            "deployed_path": str(self.deployed_path),
            "config_path": str(self.config_path),
            "pipelines_config": pipelines_config,
            "pipelines": [
                {
                    "id": pipeline.id,
                    "enabled": pipeline.enabled,
                    "required_inputs": list(pipeline.required_inputs),
                    "stages": [
                        {
                            "id": stage.id,
                            "enabled": stage.enabled,
                            "module": stage.module,
                            "class_name": stage.class_name,
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
        pipelines_config = deepcopy(raw_pipelines)
        pipelines_config.setdefault(Config.KEY_PIPELINES_ENABLED, True)
        pipelines_config.setdefault(Config.KEY_PIPELINE_FRAME_INTERVAL_SECONDS, 1.0)
        pipelines_config.setdefault(Config.KEY_PIPELINES, [])
        pipelines_config.setdefault(Config.KEY_PIPELINE_EDGES, [])

        pipelines = pipelines_config.get(Config.KEY_PIPELINES)
        if isinstance(pipelines, list):
            for pipeline in pipelines:
                if not isinstance(pipeline, dict):
                    continue
                pipeline.setdefault(Config.KEY_PIPELINE_ENABLED, True)
                pipeline.setdefault(Config.KEY_PIPELINE_STAGES, [])
                stages = pipeline.get(Config.KEY_PIPELINE_STAGES)
                if not isinstance(stages, list):
                    continue
                for stage in stages:
                    if not isinstance(stage, dict):
                        continue
                    stage.setdefault(Config.KEY_STAGE_ENABLED, True)
                    if (
                        Config.KEY_STAGE_CLASS not in stage
                        and Config.KEY_STAGE_CLASS_NAME in stage
                    ):
                        stage[Config.KEY_STAGE_CLASS] = stage[
                            Config.KEY_STAGE_CLASS_NAME
                        ]
                    stage.pop(Config.KEY_STAGE_CLASS_NAME, None)
                    stage.setdefault(Config.KEY_STAGE_CONFIG, {})

        return pipelines_config

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _write_yaml(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = yaml.safe_dump(data, sort_keys=False)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as temp_file:
            temp_file.write(rendered)
            temp_path = Path(temp_file.name)
        temp_path.replace(path)
