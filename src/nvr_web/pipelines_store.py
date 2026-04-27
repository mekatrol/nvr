from __future__ import annotations

from copy import deepcopy
from os.path import relpath
from pathlib import Path
from shutil import copy2
import tempfile
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
        graph_config = self._expand_pipeline_config_paths(
            pipelines_config,
            self.pipelines_path,
            self.pipelines_dir,
            resolve_stage_filenames=True,
        )
        graph = Config._parse_pipelines(graph_config)
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
        pipelines_config = self._relativize_stage_filenames(
            pipelines_config, self.pipelines_path, self.pipelines_dir
        )
        self._validate_pipelines_config(
            pipelines_config, self.pipelines_path, self.pipelines_dir
        )
        self._write_yaml(self.pipelines_path, pipelines_config)
        return self.pipelines_response(pipelines_config)

    def deploy_pipeline_config_pipelines(self) -> dict[str, Any]:
        pipelines_config = self.load_pipeline_config_pipelines()
        self._validate_pipelines_config(
            pipelines_config, self.pipelines_path, self.pipelines_dir
        )
        deployed_config = self._copy_stage_files_to_deployed(pipelines_config)
        self._validate_pipelines_config(
            deployed_config, self.deployed_path, self.deployed_dir
        )
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
        pipelines_config = self._relativize_stage_filenames(
            pipelines_config, self.pipelines_path, self.pipelines_dir
        )
        self._validate_pipelines_config(
            pipelines_config, self.pipelines_path, self.pipelines_dir
        )
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
        self,
        pipelines_config: dict[str, Any],
        yaml_path: Path | None = None,
        allowed_root: Path | None = None,
    ) -> PipelineGraph:
        errors: list[str] = []
        validation_config = pipelines_config
        if yaml_path is not None and allowed_root is not None:
            try:
                validation_config = self._expand_pipeline_config_paths(
                    pipelines_config,
                    yaml_path,
                    allowed_root,
                    resolve_stage_filenames=True,
                )
            except ValueError as ex:
                errors.append(str(ex))
        self.config._validate_pipelines(validation_config, "pipelines", errors)
        if errors:
            raise ValueError("Invalid pipelines:\n- " + "\n- ".join(errors))
        graph = Config._parse_pipelines(validation_config)
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
        return self._copy_pipeline_config_to_deployed(
            pipelines_config, self.pipelines_path, self.deployed_path
        )

    def _copy_pipeline_config_to_deployed(
        self,
        pipelines_config: dict[str, Any],
        source_yaml_path: Path,
        deployed_yaml_path: Path,
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
                    pipeline_path = stage.get("pipeline")
                    if isinstance(pipeline_path, str) and self._is_yaml_path(
                        pipeline_path
                    ):
                        source_path = self._config_path_under(
                            pipeline_path, source_yaml_path, self.pipelines_dir
                        )
                        deployed_path = self.deployed_dir / source_path.relative_to(
                            self.pipelines_dir
                        )
                        child_config = self._load_yaml(source_path)
                        deployed_child_config = self._copy_pipeline_config_to_deployed(
                            child_config, source_path, deployed_path
                        )
                        self._write_yaml(deployed_path, deployed_child_config)
                        stage["pipeline"] = self._relative_path(
                            deployed_path, deployed_yaml_path
                        )
                    continue

                source_path = self._stage_path_under(
                    filename, source_yaml_path, self.pipelines_dir
                )
                if source_path.exists():
                    deployed_path = self.deployed_dir / source_path.relative_to(
                        self.pipelines_dir
                    )
                    deployed_path.parent.mkdir(parents=True, exist_ok=True)
                    copy2(source_path, deployed_path)
                    stage["filename"] = self._relative_path(
                        deployed_path, deployed_yaml_path
                    )
        return deployed_config

    def _relativize_stage_filenames(
        self, pipelines_config: dict[str, Any], yaml_path: Path, allowed_root: Path
    ) -> dict[str, Any]:
        config = deepcopy(pipelines_config)
        for pipeline in config.get(Config.KEY_PIPELINES, []):
            if not isinstance(pipeline, dict):
                continue
            for stage in pipeline.get("stages", []):
                if not isinstance(stage, dict):
                    continue
                filename = stage.get("filename")
                if not isinstance(filename, str) or not filename:
                    continue
                path = Path(filename)
                if path.is_absolute():
                    raise ValueError(
                        f"stage filename must be relative to {yaml_path}: {filename}"
                    )
                self._stage_path_under(filename, yaml_path, allowed_root)
        return config

    def _resolve_stage_filenames(
        self, pipelines_config: dict[str, Any], yaml_path: Path, allowed_root: Path
    ) -> dict[str, Any]:
        config = deepcopy(pipelines_config)
        for pipeline in config.get(Config.KEY_PIPELINES, []):
            if not isinstance(pipeline, dict):
                continue
            for stage in pipeline.get("stages", []):
                if not isinstance(stage, dict):
                    continue
                filename = stage.get("filename")
                if not isinstance(filename, str) or not filename:
                    continue
                stage["filename"] = str(
                    self._stage_path_under(filename, yaml_path, allowed_root)
                )
        return config

    def _expand_pipeline_config_paths(
        self,
        pipelines_config: dict[str, Any],
        yaml_path: Path,
        allowed_root: Path,
        resolve_stage_filenames: bool,
        seen_paths: set[Path] | None = None,
    ) -> dict[str, Any]:
        seen_paths = seen_paths or set()
        yaml_path = yaml_path.resolve()
        if yaml_path in seen_paths:
            raise ValueError(f"pipeline config include cycle at {yaml_path}")

        seen_paths.add(yaml_path)
        config = self._normalize_pipelines_config(pipelines_config)
        if resolve_stage_filenames:
            config = self._resolve_stage_filenames(config, yaml_path, allowed_root)
        else:
            config = deepcopy(config)

        merged_pipelines = list(config.get(Config.KEY_PIPELINES, []))
        merged_edges = list(config.get(Config.KEY_PIPELINE_EDGES, []))
        path_reference_targets: dict[str, str] = {}

        for pipeline in list(merged_pipelines):
            if not isinstance(pipeline, dict):
                continue
            source_pipeline_id = pipeline.get("id")
            stages = pipeline.get("stages", [])
            if not isinstance(source_pipeline_id, str) or not isinstance(stages, list):
                continue
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                pipeline_reference = stage.get("pipeline")
                if not (
                    isinstance(pipeline_reference, str)
                    and self._is_yaml_path(pipeline_reference)
                ):
                    continue

                child_yaml_path = self._config_path_under(
                    pipeline_reference, yaml_path, allowed_root
                )
                child_config = self._load_yaml(child_yaml_path)
                expanded_child = self._expand_pipeline_config_paths(
                    child_config,
                    child_yaml_path,
                    allowed_root,
                    resolve_stage_filenames,
                    seen_paths,
                )
                child_graph = Config._parse_pipelines(expanded_child)
                child_sources = child_graph.source_pipeline_ids()
                if len(child_sources) != 1:
                    raise ValueError(
                        f"pipeline config {child_yaml_path} must define exactly "
                        "one source pipeline"
                    )

                child_pipeline_id = child_sources[0]
                stage["pipeline"] = child_pipeline_id
                path_reference_targets[pipeline_reference] = child_pipeline_id
                for child_pipeline in expanded_child.get(Config.KEY_PIPELINES, []):
                    merged_pipelines.append(child_pipeline)
                for child_edge in expanded_child.get(Config.KEY_PIPELINE_EDGES, []):
                    merged_edges.append(child_edge)

        for edge in merged_edges:
            if not isinstance(edge, dict):
                continue
            target = edge.get(Config.KEY_PIPELINE_EDGE_TO)
            if isinstance(target, str) and target in path_reference_targets:
                edge[Config.KEY_PIPELINE_EDGE_TO] = path_reference_targets[target]
            source = edge.get(Config.KEY_PIPELINE_EDGE_FROM)
            if isinstance(source, str) and source in path_reference_targets:
                edge[Config.KEY_PIPELINE_EDGE_FROM] = path_reference_targets[source]

        config[Config.KEY_PIPELINES] = merged_pipelines
        config[Config.KEY_PIPELINE_EDGES] = [
            edge
            for edge in merged_edges
            if not (
                isinstance(edge, dict)
                and (
                    self._is_yaml_path(str(edge.get(Config.KEY_PIPELINE_EDGE_FROM, "")))
                    or self._is_yaml_path(
                        str(edge.get(Config.KEY_PIPELINE_EDGE_TO, ""))
                    )
                )
            )
        ]
        return self._normalize_pipelines_config(config)

    def _validate_stage_filenames_under(
        self,
        pipelines_config: dict[str, Any],
        yaml_path: Path,
        allowed_root: Path,
        errors: list[str] | None = None,
    ) -> None:
        for pipeline in pipelines_config.get(Config.KEY_PIPELINES, []):
            if not isinstance(pipeline, dict):
                continue
            pipeline_id = pipeline.get("id", "<unknown>")
            for stage in pipeline.get("stages", []):
                if not isinstance(stage, dict):
                    continue
                filename = stage.get("filename")
                if not isinstance(filename, str) or not filename:
                    continue
                try:
                    self._stage_path_under(filename, yaml_path, allowed_root)
                except ValueError as ex:
                    message = f"pipeline {pipeline_id} stage {stage.get('id', '<unknown>')}: {ex}"
                    if errors is None:
                        raise ValueError(message) from ex
                    errors.append(message)

    def _stage_path_under(
        self, filename: str, yaml_path: Path, allowed_root: Path
    ) -> Path:
        return self._relative_path_under(filename, yaml_path, allowed_root, "stage")

    def _config_path_under(
        self, filename: str, yaml_path: Path, allowed_root: Path
    ) -> Path:
        path = self._relative_path_under(filename, yaml_path, allowed_root, "pipeline")
        if not self._is_yaml_path(filename):
            raise ValueError(f"pipeline config reference must be a YAML file: {filename}")
        if not path.exists():
            raise ValueError(f"pipeline config does not exist: {filename}")
        return path

    def _relative_path_under(
        self, filename: str, yaml_path: Path, allowed_root: Path, label: str
    ) -> Path:
        path = Path(filename)
        if path.is_absolute():
            raise ValueError(
                f"{label} filename must be relative to {yaml_path}: {filename}"
            )

        yaml_dir = yaml_path.parent.resolve()
        allowed_root = allowed_root.resolve()
        resolved_path = (yaml_dir / path).resolve()
        try:
            resolved_path.relative_to(allowed_root)
        except ValueError as ex:
            raise ValueError(
                f"{label} filename escapes {allowed_root}: {filename}"
            ) from ex
        return resolved_path

    @staticmethod
    def _is_yaml_path(value: str) -> bool:
        return Path(value).suffix.lower() in {".yaml", ".yml"}

    def _relative_path(self, path: Path, yaml_path: Path) -> str:
        resolved_path = path.resolve()
        return relpath(resolved_path, yaml_path.parent.resolve())

    def _example_resize_pipeline_config(self, stage_path: Path) -> dict[str, Any]:
        return {
            "id": "example-resize",
            "name": "Example resize",
            "enabled": True,
            "stages": [
                {
                    "id": "resize-frame",
                    "enabled": True,
                    "filename": self._relative_path(stage_path, self.pipelines_path),
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
