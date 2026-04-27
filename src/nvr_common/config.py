import os
import yaml
import logging
from pathlib import Path
from collections.abc import MutableMapping
from typing import Any, Dict, Iterator, List, Set
from urllib.parse import urlparse
from nvr_common.pipeline import (
    NamedPipeline,
    PipelineEdge,
    PipelineGraph,
    PipelineStageConfig,
    PipelineValidationError,
)
from nvr_common.singleton import Singleton


class Config(Singleton, MutableMapping):
    # Config key constants
    KEY_LOG_PATH: str = "log_path"
    KEY_STREAM: str = "stream"
    KEY_STREAM_OUTPUT_PATH: str = "output_path"
    KEY_STREAM_RETENTION_DAYS: str = "retention_days"
    KEY_STREAM_BACKUP_OUTPUT_PATH: str = "backup_output_path"
    KEY_STREAM_BACKUP_RETENTION_DAYS: str = "backup_retention_days"
    KEY_STREAM_SEGMENT_SECONDS: str = "segment_seconds"
    KEY_FFMPEG_BINARY: str = "ffmpeg_binary"
    KEY_CAMERAS: str = "cameras"
    KEY_CAMERA_ID: str = "id"
    KEY_CAMERA_NAME: str = "name"
    KEY_CAMERA_ENABLED: str = "enabled"
    KEY_CAMERA_RTSP_URL: str = "rtsp_url"
    KEY_CAMERA_LOG_FFMPEG: str = "log_ffmpeg"
    KEY_PIPELINE_CONFIG_STORAGE_PATH: str = "pipeline_config_storage_path"
    KEY_PIPELINES_CONFIG: str = "pipelines"
    KEY_PIPELINES_CONFIG_FILENAME: str = "pipeline_conf.yaml"
    KEY_PIPELINES_ENABLED: str = "enabled"
    KEY_PIPELINE_FRAME_INTERVAL_SECONDS: str = "frame_interval_seconds"
    KEY_PIPELINES: str = "pipelines"
    KEY_PIPELINES_PIPELINE: str = "pipeline"
    KEY_PIPELINE_ID: str = "id"
    KEY_PIPELINE_NAME: str = "name"
    KEY_PIPELINE_ENABLED: str = "enabled"
    KEY_PIPELINE_STAGES: str = "stages"
    KEY_PIPELINE_INPUTS: str = "inputs"
    KEY_PIPELINE_INPUTS_REQUIRED: str = "required"
    KEY_PIPELINE_EDGES: str = "edges"
    KEY_PIPELINE_EDGE_FROM: str = "from"
    KEY_PIPELINE_EDGE_TO: str = "to"
    KEY_STAGE_ID: str = "id"
    KEY_STAGE_ENABLED: str = "enabled"
    KEY_STAGE_MODULE: str = "module"
    KEY_STAGE_CLASS: str = "class"
    KEY_STAGE_CLASS_NAME: str = "class_name"
    KEY_STAGE_FILENAME: str = "filename"
    KEY_STAGE_PIPELINE: str = "pipeline"
    KEY_STAGE_CONFIG: str = "config"

    stream_output_path = None
    stream_retention_days = 1
    stream_segment_seconds = 5 * 60  # Five minutes
    stream_backup_output_path = None
    stream_backup_retention_days = 0

    _conf: Dict[str, Any] = {}
    cameras_by_id: Dict[str, Dict[str, Any]]

    def __init__(self) -> None:
        # Base config (usually config.yaml, or whatever NVR_CONFIG env variable points to)
        self.config_path: str = os.path.abspath(
            os.environ.get("NVR_CONFIG", "config.yaml")
        )
        self._conf = self._load_config(self.config_path)

        # Local-only overrides: config.debug.yaml in the same directory as config.yaml
        base_path: Path = Path(self.config_path)
        debug_config_path: Path = base_path.with_name("config.debug.yaml")

        # If there there is a debug conf then merge configured values
        if debug_config_path.exists():
            debug_conf: Dict[str, Any] = self._load_config(str(debug_config_path))
            if debug_conf:
                self._conf = self._merge_dicts(self._conf, debug_conf)

        # Build camera lookup and expand RTSP URLs
        self.cameras_by_id = {}
        for camera in self._conf.get(self.KEY_CAMERAS, []):
            if isinstance(camera, dict) and self.KEY_CAMERA_ID in camera:
                camera_id: str = camera[self.KEY_CAMERA_ID]

                # Expand environment variables inside rtsp_url
                if self.KEY_CAMERA_RTSP_URL in camera and isinstance(
                    camera[self.KEY_CAMERA_RTSP_URL], str
                ):
                    camera[self.KEY_CAMERA_RTSP_URL] = Config._expand_env_in_url(
                        camera[self.KEY_CAMERA_RTSP_URL]
                    )

                self.cameras_by_id[camera_id] = camera

        # Validate the loaded configuration
        self._validate()
        pipeline_config_storage_path = self.get_pipeline_config_storage_path()
        pipeline_config_storage_path.mkdir(parents=True, exist_ok=True)
        (pipeline_config_storage_path / "pipelines").mkdir(parents=True, exist_ok=True)
        (pipeline_config_storage_path / "deployed").mkdir(parents=True, exist_ok=True)

    def get_camera(self, camera_id: str) -> Dict[str, Any]:
        return self.cameras_by_id[camera_id]

    def get_pipeline_config_storage_path(self) -> Path:
        raw_path = self._conf.get(self.KEY_PIPELINE_CONFIG_STORAGE_PATH)
        if isinstance(raw_path, str) and raw_path:
            path = Path(raw_path)
        else:
            path = Path("pipeline_config")

        if not path.is_absolute():
            path = (Path(self.config_path).parent / path).resolve()
        return path

    def get_deployed_pipelines_path(self) -> Path:
        return self.get_pipeline_config_storage_path() / "deployed" / "pipelines.yaml"

    def get_pipeline_config_path(self) -> Path:
        return Path(self.config_path).with_name(self.KEY_PIPELINES_CONFIG_FILENAME)

    def get_pipelines_config(
        self, camera_id: str | None = None
    ) -> Dict[str, Any] | None:
        pipelines = (
            self._load_deployed_pipelines_config()
            or self._load_pipeline_conf_config()
            or self._conf.get(self.KEY_PIPELINES_CONFIG)
        )

        if camera_id is not None:
            camera = self.get_camera(camera_id)
            camera_pipelines = camera.get(self.KEY_PIPELINES_CONFIG)
            if camera_pipelines is not None:
                pipelines = self._merge_pipelines_dict(pipelines, camera_pipelines)

        if not isinstance(pipelines, dict):
            return None
        return self._normalize_pipelines_config(pipelines)

    def _load_pipeline_conf_config(self) -> Dict[str, Any] | None:
        pipeline_conf_path = self.get_pipeline_config_path()
        if not pipeline_conf_path.exists():
            return None

        pipeline_conf = self._load_config(str(pipeline_conf_path))
        pipelines = self._unwrap_pipelines_config(pipeline_conf)

        debug_path = pipeline_conf_path.with_name("pipeline_conf.debug.yaml")
        if debug_path.exists():
            debug_conf = self._load_config(str(debug_path))
            debug_pipelines = self._unwrap_pipelines_config(debug_conf)
            if debug_pipelines:
                pipelines = self._merge_pipelines_dict(pipelines, debug_pipelines)

        return pipelines if isinstance(pipelines, dict) else None

    def _load_deployed_pipelines_config(self) -> Dict[str, Any] | None:
        deployed_path = self.get_deployed_pipelines_path()
        if not deployed_path.exists():
            return None
        deployed_config = self._load_config(str(deployed_path))
        pipelines = self._unwrap_pipelines_config(deployed_config)
        return (
            self._normalize_pipelines_config(pipelines)
            if isinstance(pipelines, dict)
            else None
        )

    def get_pipelines(self, camera_id: str | None = None) -> PipelineGraph | None:
        pipelines = self.get_pipelines_config(camera_id)
        if not pipelines:
            return None
        if pipelines.get(self.KEY_PIPELINES_ENABLED) is False:
            return None
        return self._parse_pipelines(pipelines)

    def get_pipeline_frame_interval_seconds(
        self, camera_id: str | None = None
    ) -> float | None:
        pipelines = self.get_pipelines_config(camera_id)
        if not pipelines:
            return None
        value = pipelines.get(self.KEY_PIPELINE_FRAME_INTERVAL_SECONDS)
        return float(value) if isinstance(value, (int, float)) else None

    def log_config(self, logger: logging.Logger | None = None) -> None:
        """
        Log all effective configuration values.

        Can be called from other modules via:
            from config import Config
            Config().log_config()
        """
        logger = logger or logging.getLogger(__name__)

        logger.info("Configuration file: %s", self.config_path)

        # Top-level raw config keys
        logger.info("Raw config keys: %s", ", ".join(sorted(self._conf.keys())))

        # Stream-related effective values
        logger.info("stream.output_path=%s", self.stream_output_path)
        logger.info("stream.retention_days=%s", self.stream_retention_days)
        logger.info("stream.segment_seconds=%s", self.stream_segment_seconds)
        logger.info("stream.backup_output_path=%s", self.stream_backup_output_path)
        logger.info(
            "stream.backup_retention_days=%s", self.stream_backup_retention_days
        )

        # ffmpeg
        ffmpeg_binary = self._conf.get(self.KEY_FFMPEG_BINARY)
        logger.info("ffmpeg_binary=%s", ffmpeg_binary)

        # Cameras (RTSP password redacted)
        for cam_id, camera in self.cameras_by_id.items():
            safe_cam = dict(camera)

            url_val = safe_cam.get(self.KEY_CAMERA_RTSP_URL)
            if isinstance(url_val, str):
                parsed = urlparse(url_val)

                # Redact password if present
                if parsed.password is not None:
                    host = parsed.hostname or ""
                    netloc = host
                    if parsed.username:
                        netloc = f"{parsed.username}:***@{host}"
                    if parsed.port:
                        netloc = f"{netloc}:{parsed.port}"
                    parsed = parsed._replace(netloc=netloc)
                    safe_cam[self.KEY_CAMERA_RTSP_URL] = parsed.geturl()

            logger.info("camera[%s]=%r", cam_id, safe_cam)

    def __getitem__(self, key: str) -> Any:
        return self._conf[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._conf[key] = value

    def __delitem__(self, key: str) -> None:
        del self._conf[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._conf)

    def __len__(self) -> int:
        return len(self._conf)

    @staticmethod
    def _expand_env_in_url(url: str) -> str:
        return url.format(
            RTSP_USER=os.environ.get("RTSP_USER", ""),
            RTSP_PASSWORD=os.environ.get("RTSP_PASSWORD", ""),
        )

    @staticmethod
    def _merge_camera_list(
        base_list: list[dict], override_list: list[dict]
    ) -> list[dict]:
        """
        Merge two camera lists (each a list of dicts) by camera 'id'.

        Rules:
        - If a camera ID appears only in base → kept as-is
        - If a camera ID appears in both → deep-merge their fields
        - If a camera ID appears only in overrides → append it
        """

        merged_by_id: dict[str, dict] = {}

        # Start with base cameras
        for camera in base_list:
            cam_id = camera.get(Config.KEY_CAMERA_ID)
            if isinstance(cam_id, str):
                merged_by_id[cam_id] = dict(camera)  # shallow copy

        # Merge in override cameras
        for override_cam in override_list:
            cam_id = override_cam.get(Config.KEY_CAMERA_ID)
            if not isinstance(cam_id, str):
                continue

            if cam_id in merged_by_id:
                # Deep merge the individual camera dict
                merged_by_id[cam_id] = Config._merge_dicts(
                    merged_by_id[cam_id], override_cam
                )
            else:
                merged_by_id[cam_id] = dict(override_cam)

        # Return as a list
        return list(merged_by_id.values())

    @staticmethod
    def _merge_stream_dict(
        base_stream: dict[str, Any] | None, override_stream: dict[str, Any] | None
    ) -> dict[str, Any]:
        """
        Merge two 'stream' dicts.

        Rules:
        - base_stream provides defaults.
        - override_stream only overrides specified fields.
        - If override_stream is not a dict, base_stream is returned unchanged.
        """

        if not isinstance(base_stream, dict):
            base_stream = {}
        if not isinstance(override_stream, dict):
            return base_stream

        # Reuse _merge_dicts for nested keys:
        return Config._merge_dicts(base_stream, override_stream)

    @staticmethod
    def _merge_dicts(base: Any, overrides: Any) -> Any:
        """
        Recursively merge `overrides` into `base`.

        Special cases:
        - KEY_CAMERAS: merge lists by camera 'id' instead of replacing.
        - KEY_STREAM:  deep-merge dict instead of replacing, and ignore
                       non-dict overrides.
        """

        # Case: both are dicts → deep merge by key
        if isinstance(base, dict) and isinstance(overrides, dict):
            result = dict(base)
            for key, override_value in overrides.items():
                base_value = base.get(key)

                # Cameras: list merge by id
                if (
                    key == Config.KEY_CAMERAS
                    and isinstance(base_value, list)
                    and isinstance(override_value, list)
                ):
                    result[key] = Config._merge_camera_list(base_value, override_value)

                # Stream: dict merge, ignore non-dict overrides
                elif (
                    key == Config.KEY_STREAM
                    and isinstance(base_value, dict)
                    and isinstance(override_value, dict)
                ):
                    result[key] = Config._merge_stream_dict(base_value, override_value)

                elif (
                    key == Config.KEY_PIPELINES_CONFIG
                    and isinstance(base_value, dict)
                    and isinstance(override_value, dict)
                ):
                    result[key] = Config._merge_pipelines_dict(
                        base_value, override_value
                    )

                else:
                    # Generic recursive merge
                    result[key] = Config._merge_dicts(base_value, override_value)

            return result

        # For non-dicts, overrides completely replace base
        return overrides

    @staticmethod
    def _merge_pipelines_dict(base_graph: Any, override_graph: Any) -> dict[str, Any]:
        if not isinstance(base_graph, dict):
            base_graph = {}
        if not isinstance(override_graph, dict):
            return dict(base_graph)

        result = dict(base_graph)
        for key, override_value in override_graph.items():
            base_value = base_graph.get(key)
            if (
                key in (Config.KEY_PIPELINES, Config.KEY_PIPELINES_PIPELINE)
                and isinstance(base_value, list)
                and isinstance(override_value, list)
            ):
                result[key] = Config._merge_pipeline_list(base_value, override_value)
            elif (
                key == Config.KEY_PIPELINES
                and isinstance(base_value, dict)
                and isinstance(override_value, dict)
            ):
                result[key] = Config._merge_pipelines_dict(base_value, override_value)
            else:
                result[key] = Config._merge_dicts(base_value, override_value)
        return result

    @staticmethod
    def _merge_pipeline_list(
        base_list: list[Any], override_list: list[Any]
    ) -> list[Any]:
        merged_by_id: dict[str, dict[str, Any]] = {}
        invalid_entries: list[Any] = []

        for pipeline in base_list:
            if not isinstance(pipeline, dict):
                invalid_entries.append(pipeline)
                continue
            pipeline_id = pipeline.get(Config.KEY_PIPELINE_ID)
            if isinstance(pipeline_id, str):
                merged_by_id[pipeline_id] = dict(pipeline)
            else:
                invalid_entries.append(dict(pipeline))

        for override_pipeline in override_list:
            if not isinstance(override_pipeline, dict):
                invalid_entries.append(override_pipeline)
                continue
            pipeline_id = override_pipeline.get(Config.KEY_PIPELINE_ID)
            if not isinstance(pipeline_id, str):
                invalid_entries.append(dict(override_pipeline))
                continue

            if pipeline_id in merged_by_id:
                merged_by_id[pipeline_id] = Config._merge_pipeline_dict(
                    merged_by_id[pipeline_id], override_pipeline
                )
            else:
                merged_by_id[pipeline_id] = dict(override_pipeline)

        return [*merged_by_id.values(), *invalid_entries]

    @staticmethod
    def _merge_pipeline_dict(
        base_pipeline: dict[str, Any], override_pipeline: dict[str, Any]
    ) -> dict[str, Any]:
        result = dict(base_pipeline)
        for key, override_value in override_pipeline.items():
            base_value = base_pipeline.get(key)
            if (
                key == Config.KEY_PIPELINE_STAGES
                and isinstance(base_value, list)
                and isinstance(override_value, list)
            ):
                result[key] = Config._merge_stage_list(base_value, override_value)
            else:
                result[key] = Config._merge_dicts(base_value, override_value)
        return result

    @staticmethod
    def _merge_stage_list(base_list: list[Any], override_list: list[Any]) -> list[Any]:
        merged_by_id: dict[str, dict[str, Any]] = {}
        invalid_entries: list[Any] = []

        for stage in base_list:
            if not isinstance(stage, dict):
                invalid_entries.append(stage)
                continue
            stage_id = stage.get(Config.KEY_STAGE_ID)
            if isinstance(stage_id, str):
                merged_by_id[stage_id] = dict(stage)
            else:
                invalid_entries.append(dict(stage))

        for override_stage in override_list:
            if not isinstance(override_stage, dict):
                invalid_entries.append(override_stage)
                continue
            stage_id = override_stage.get(Config.KEY_STAGE_ID)
            if not isinstance(stage_id, str):
                invalid_entries.append(dict(override_stage))
                continue

            if stage_id in merged_by_id:
                merged_by_id[stage_id] = Config._merge_dicts(
                    merged_by_id[stage_id], override_stage
                )
            else:
                merged_by_id[stage_id] = dict(override_stage)

        return [*merged_by_id.values(), *invalid_entries]

    @staticmethod
    def _load_config(path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data: Any = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}

    @classmethod
    def _unwrap_pipelines_config(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        wrapper = data.get(cls.KEY_PIPELINES_CONFIG)
        return wrapper if isinstance(wrapper, dict) else data

    @classmethod
    def _normalize_pipelines_config(
        cls, raw_pipelines: dict[str, Any]
    ) -> dict[str, Any]:
        pipelines_config = dict(raw_pipelines)
        pipelines_config.setdefault(cls.KEY_PIPELINES_ENABLED, True)
        pipelines_config.setdefault(cls.KEY_PIPELINE_FRAME_INTERVAL_SECONDS, 1.0)

        raw_pipeline_container = pipelines_config.get(cls.KEY_PIPELINES)
        if isinstance(raw_pipeline_container, dict):
            raw_pipeline_list = raw_pipeline_container.get(cls.KEY_PIPELINES_PIPELINE)
        else:
            raw_pipeline_list = raw_pipeline_container

        if cls.KEY_PIPELINES_PIPELINE in pipelines_config:
            raw_pipeline_list = pipelines_config.get(cls.KEY_PIPELINES_PIPELINE)

        pipelines_config[cls.KEY_PIPELINES] = (
            raw_pipeline_list if isinstance(raw_pipeline_list, list) else []
        )
        pipelines_config.setdefault(cls.KEY_PIPELINE_EDGES, [])

        for pipeline in pipelines_config[cls.KEY_PIPELINES]:
            if not isinstance(pipeline, dict):
                continue
            pipeline.setdefault(cls.KEY_PIPELINE_ENABLED, True)
            pipeline.setdefault(cls.KEY_PIPELINE_STAGES, [])
            stages = pipeline.get(cls.KEY_PIPELINE_STAGES)
            if not isinstance(stages, list):
                continue
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                stage.setdefault(cls.KEY_STAGE_ENABLED, True)
                stage.setdefault(cls.KEY_STAGE_CONFIG, {})
                if (
                    cls.KEY_STAGE_CLASS not in stage
                    and cls.KEY_STAGE_CLASS_NAME in stage
                ):
                    stage[cls.KEY_STAGE_CLASS] = stage[cls.KEY_STAGE_CLASS_NAME]
                stage.pop(cls.KEY_STAGE_CLASS_NAME, None)

        generated_edges = cls._pipeline_reference_edges(pipelines_config)
        explicit_edges = pipelines_config.get(cls.KEY_PIPELINE_EDGES)
        if isinstance(explicit_edges, list):
            edge_keys = {
                (
                    edge.get(cls.KEY_PIPELINE_EDGE_FROM),
                    edge.get(cls.KEY_PIPELINE_EDGE_TO),
                )
                for edge in explicit_edges
                if isinstance(edge, dict)
            }
            for edge in generated_edges:
                edge_key = (
                    edge[cls.KEY_PIPELINE_EDGE_FROM],
                    edge[cls.KEY_PIPELINE_EDGE_TO],
                )
                if edge_key not in edge_keys:
                    explicit_edges.append(edge)
        else:
            pipelines_config[cls.KEY_PIPELINE_EDGES] = generated_edges

        return pipelines_config

    @classmethod
    def _pipeline_reference_edges(
        cls, pipelines_config: dict[str, Any]
    ) -> list[dict[str, str]]:
        edges: list[dict[str, str]] = []
        raw_pipelines = pipelines_config.get(cls.KEY_PIPELINES)
        if not isinstance(raw_pipelines, list):
            return edges

        for pipeline in raw_pipelines:
            if not isinstance(pipeline, dict):
                continue
            source = pipeline.get(cls.KEY_PIPELINE_ID)
            if not isinstance(source, str):
                continue
            stages = pipeline.get(cls.KEY_PIPELINE_STAGES)
            if not isinstance(stages, list):
                continue
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                target = stage.get(cls.KEY_STAGE_PIPELINE)
                if isinstance(target, str) and target:
                    edges.append(
                        {
                            cls.KEY_PIPELINE_EDGE_FROM: source,
                            cls.KEY_PIPELINE_EDGE_TO: target,
                        }
                    )
        return edges

    def _validate_dir_path(
        self, raw_value: Any, field_label: str, errors: List[str], validate_exists: True
    ) -> bool:
        """
        Validate that raw_value is a non-empty string pointing to an existing directory.
        field_label is used verbatim in error messages (e.g. 'stream->log_path').
        """
        if not isinstance(raw_value, str) or not raw_value:
            errors.append(f"{field_label} must be a non-empty string")
            return False

        path = Path(raw_value)
        if not path.is_absolute():
            path = (Path(self.config_path).parent / path).resolve()

        if validate_exists and not path.exists():
            errors.append(f"{field_label} does not exist: {path}")
            return False

        # Must be a dreictory
        if path.exists() and not path.is_dir():
            errors.append(f"{field_label} is not a directory: {path}")
            return False

        return True

    @staticmethod
    def _validate_int(
        raw_value: Any,
        field_label: str,
        errors: List[str],
        min_value: int = None,
        max_value: int = None,
    ) -> None:
        """
        Validate that raw_value is an integer.
        field_label is used verbatim in error messages (e.g. 'stream->retention_days').
        """
        if not isinstance(raw_value, int):
            errors.append(f"{field_label} must be an integer")
            return False  # Can't validate further is not an integer

        has_error = False
        if min_value is not None and raw_value < min_value:
            errors.append(f"{field_label} must be greater than or equal to {min_value}")
            has_error = True

        if max_value is not None and raw_value > max_value:
            errors.append(f"{field_label} must be less than or equal to {max_value}")
            has_error = True

        return not has_error

    @staticmethod
    def _validate_float(
        raw_value: Any,
        field_label: str,
        errors: List[str],
        min_value: float = None,
        max_value: float = None,
    ) -> bool:
        """
        Validate that raw_value is a numeric value (int or float).
        field_label is used verbatim in error messages.
        """
        if not isinstance(raw_value, (int, float)):
            errors.append(f"{field_label} must be a number")
            return False  # do not attempt range checks

        has_error = False
        if min_value is not None and raw_value < min_value:
            errors.append(f"{field_label} must be greater than or equal to {min_value}")
            has_error = True

        if max_value is not None and raw_value > max_value:
            errors.append(f"{field_label} must be less than or equal to {max_value}")
            has_error = True

        return not has_error

    def _validate(self) -> None:
        errors: List[str] = []

        # log_path is set and a valid path
        log_path: Any = self._conf.get(self.KEY_LOG_PATH)
        self._validate_dir_path(log_path, "stream->log_path", errors, False)

        stream_cfg = self._conf.get(self.KEY_STREAM)
        if not isinstance(stream_cfg, dict):
            errors.append("stream must be a dictionary value")
        else:
            self.stream_output_path = None
            self.stream_retention_days = 1

            # stream output path is set and a valid path
            stream_output_path: Any = stream_cfg.get(self.KEY_STREAM_OUTPUT_PATH)
            if self._validate_dir_path(
                stream_output_path, "stream->output_path", errors, False
            ):
                self.stream_output_path = stream_output_path

            # retention_days is valid integer
            stream_retention_days: Any = stream_cfg.get(self.KEY_STREAM_RETENTION_DAYS)
            if self._validate_float(
                stream_retention_days,
                "stream->retention_days",
                errors,
                0,  # Must be zero or greater
            ):
                self.stream_retention_days = stream_retention_days

            # stream backup output path is set and a valid path
            stream_backup_output_path: Any = stream_cfg.get(
                self.KEY_STREAM_BACKUP_OUTPUT_PATH
            )
            if self._validate_dir_path(
                stream_backup_output_path, "stream->backup_output_path", errors, False
            ):
                self.stream_backup_output_path = stream_backup_output_path

            # backup_retention_days is valid integer
            stream_backup_retention_days: Any = stream_cfg.get(
                self.KEY_STREAM_BACKUP_RETENTION_DAYS
            )
            if self._validate_float(
                stream_backup_retention_days,
                "stream->backup_retention_days",
                errors,
                0,  # Must be zero or greater
            ):
                self.stream_backup_retention_days = stream_backup_retention_days

            # segment_seconds is valid integer
            stream_segment_seconds: Any = stream_cfg.get(
                self.KEY_STREAM_SEGMENT_SECONDS
            )

            # Default to 5 minutes when the value is missing or invalid
            self.stream_segment_seconds = 5 * 60

            if self._validate_int(
                stream_segment_seconds,
                "stream->segment_seconds",
                errors,
                1,  # Must be one or greater
            ):
                self.stream_segment_seconds = stream_segment_seconds

        # ffmpeg_binary is set
        ffmpeg_binary: Any = self._conf.get(self.KEY_FFMPEG_BINARY)
        if not isinstance(ffmpeg_binary, str) or not ffmpeg_binary.strip():
            errors.append("ffmpeg_binary must be a non-empty string")

        pipeline_config_storage_path: Any = self._conf.get(self.KEY_PIPELINE_CONFIG_STORAGE_PATH)
        if pipeline_config_storage_path is not None and (
            not isinstance(pipeline_config_storage_path, str) or not pipeline_config_storage_path
        ):
            errors.append("pipeline_config_storage_path must be a non-empty string")

        # cameras validation
        cameras: Any = self._conf.get(self.KEY_CAMERAS, [])
        if not isinstance(cameras, list):
            errors.append("cameras must be a list")
        else:
            ids: Set[str] = set()
            names: Set[str] = set()

            for index, camera in enumerate(cameras):
                if not isinstance(camera, dict):
                    errors.append(f"camera entry at index {index} must be a mapping")
                    continue

                camera_id: Any = camera.get(self.KEY_CAMERA_ID)
                if not isinstance(camera_id, str) or not camera_id:
                    errors.append(f"camera at index {index} must have a non-empty 'id'")
                elif camera_id in ids:
                    errors.append(f"duplicate camera id: {camera_id}")
                else:
                    ids.add(camera_id)

                camera_name: Any = camera.get(self.KEY_CAMERA_NAME)
                if not isinstance(camera_name, str) or not camera_name:
                    errors.append(
                        f"camera '{camera_id or index}' must have a non-empty 'name'"
                    )
                elif camera_name in names:
                    errors.append(f"duplicate camera name: {camera_name}")
                else:
                    names.add(camera_name)

                # enabled: may be missing (defaults to False) or a boolean.
                if self.KEY_CAMERA_ENABLED not in camera:
                    # Missing -> default to False
                    camera[self.KEY_CAMERA_ENABLED] = False
                else:
                    enabled_val: Any = camera.get(self.KEY_CAMERA_ENABLED)
                    if not isinstance(enabled_val, bool):
                        errors.append(
                            f"camera '{camera_id or index}' has invalid "
                            f"'enabled' (must be true/false if present)"
                        )

                rtsp_url_val: Any = camera.get(self.KEY_CAMERA_RTSP_URL)
                if not isinstance(rtsp_url_val, str) or not rtsp_url_val:
                    errors.append(
                        f"camera '{camera_id or index}' must have a non-empty 'rtsp_url'"
                    )
                else:
                    parsed = urlparse(rtsp_url_val)
                    if parsed.scheme.lower() != "rtsp":
                        errors.append(
                            f"camera '{camera_id or index}' has invalid rtsp_url "
                            f"(scheme must be rtsp): {rtsp_url_val}"
                        )

                # log_ffmpeg: may be missing (defaults to False) or a boolean.
                if self.KEY_CAMERA_LOG_FFMPEG not in camera:
                    # Missing -> default to False
                    camera[self.KEY_CAMERA_LOG_FFMPEG] = False
                else:
                    log_ffmpeg_val: Any = camera.get(self.KEY_CAMERA_LOG_FFMPEG)
                    if not isinstance(log_ffmpeg_val, bool):
                        errors.append(
                            f"camera '{camera_id or index}' has invalid "
                            f"'log_ffmpeg' (must be true/false if present)"
                        )

                if self.KEY_PIPELINES_CONFIG in camera:
                    effective_pipelines = self._merge_pipelines_dict(
                        self.get_pipelines_config(),
                        camera.get(self.KEY_PIPELINES_CONFIG),
                    )
                    self._validate_pipelines(
                        effective_pipelines,
                        f"camera '{camera_id or index}' pipelines",
                        errors,
                    )

        if self.KEY_PIPELINES_CONFIG in self._conf:
            self._validate_pipelines(
                self._conf.get(self.KEY_PIPELINES_CONFIG), "pipelines", errors
            )

        pipeline_conf = self._load_pipeline_conf_config()
        if pipeline_conf is not None:
            self._validate_pipelines(
                pipeline_conf, f"{self.get_pipeline_config_path()} pipelines", errors
            )

        deployed_pipelines = self._load_deployed_pipelines_config()
        if deployed_pipelines is not None:
            self._validate_pipelines(
                deployed_pipelines,
                f"{self.get_deployed_pipelines_path()} pipelines",
                errors,
            )

        if errors:
            message = "Invalid configuration:\n- " + "\n- ".join(errors)
            raise ValueError(message)

    def _validate_pipelines(
        self, raw_pipelines_config: Any, field_label: str, errors: List[str]
    ) -> None:
        if not isinstance(raw_pipelines_config, dict):
            errors.append(f"{field_label} must be a dictionary value")
            return
        raw_pipelines_config = self._normalize_pipelines_config(raw_pipelines_config)

        enabled = raw_pipelines_config.get(self.KEY_PIPELINES_ENABLED)
        if not isinstance(enabled, bool):
            errors.append(f"{field_label}->enabled must be true/false")

        interval = raw_pipelines_config.get(self.KEY_PIPELINE_FRAME_INTERVAL_SECONDS)
        if interval is not None:
            self._validate_float(
                interval, f"{field_label}->frame_interval_seconds", errors, 0
            )

        if self.KEY_PIPELINES not in raw_pipelines_config:
            errors.append(f"{field_label}->pipelines is required")
            return
        if self.KEY_PIPELINE_EDGES not in raw_pipelines_config:
            errors.append(f"{field_label}->edges is required")
            return

        try:
            graph = self._parse_pipelines(raw_pipelines_config)
        except ValueError as ex:
            errors.append(f"{field_label}: {ex}")
            return

        try:
            graph.validate()
        except PipelineValidationError as ex:
            errors.append(f"{field_label}: {ex}")
            return

        self._validate_fan_in_requirements(graph, field_label, errors)

    @classmethod
    def _parse_pipelines(cls, raw_pipelines_config: dict[str, Any]) -> PipelineGraph:
        raw_pipelines_config = cls._normalize_pipelines_config(raw_pipelines_config)
        raw_pipelines = raw_pipelines_config.get(cls.KEY_PIPELINES)
        raw_edges = raw_pipelines_config.get(cls.KEY_PIPELINE_EDGES)
        if not isinstance(raw_pipelines, list):
            raise ValueError("pipelines must be a list")
        if not isinstance(raw_edges, list):
            raise ValueError("edges must be a list")

        pipelines = tuple(
            cls._parse_named_pipeline(raw_pipeline, index)
            for index, raw_pipeline in enumerate(raw_pipelines)
        )
        edges = tuple(
            cls._parse_pipeline_edge(raw_edge, index)
            for index, raw_edge in enumerate(raw_edges)
        )
        return PipelineGraph(pipelines=pipelines, edges=edges)

    @classmethod
    def _parse_named_pipeline(cls, raw_pipeline: Any, index: int) -> NamedPipeline:
        if not isinstance(raw_pipeline, dict):
            raise ValueError(f"pipeline at index {index} must be a mapping")

        pipeline_id = cls._required_non_empty_string(
            raw_pipeline, cls.KEY_PIPELINE_ID, f"pipeline at index {index}"
        )
        pipeline_name = raw_pipeline.get(cls.KEY_PIPELINE_NAME, pipeline_id)
        if not isinstance(pipeline_name, str) or not pipeline_name:
            raise ValueError(
                f"pipeline '{pipeline_id}' name must be a non-empty string"
            )
        enabled = cls._required_bool(
            raw_pipeline, cls.KEY_PIPELINE_ENABLED, f"pipeline '{pipeline_id}'"
        )
        raw_stages = raw_pipeline.get(cls.KEY_PIPELINE_STAGES)
        if not isinstance(raw_stages, list):
            raise ValueError(f"pipeline '{pipeline_id}' stages must be a list")

        required_inputs = cls._parse_required_inputs(raw_pipeline, pipeline_id)
        stages = tuple(
            cls._parse_stage(stage, stage_index, pipeline_id)
            for stage_index, stage in enumerate(raw_stages)
        )
        return NamedPipeline(
            id=pipeline_id,
            name=pipeline_name,
            stages=stages,
            enabled=enabled,
            required_inputs=required_inputs,
        )

    @classmethod
    def _parse_required_inputs(
        cls, raw_pipeline: dict[str, Any], pipeline_id: str
    ) -> tuple[str, ...]:
        raw_inputs = raw_pipeline.get(cls.KEY_PIPELINE_INPUTS)
        if raw_inputs is None:
            return ()
        if not isinstance(raw_inputs, dict):
            raise ValueError(f"pipeline '{pipeline_id}' inputs must be a mapping")

        raw_required = raw_inputs.get(cls.KEY_PIPELINE_INPUTS_REQUIRED)
        if raw_required is None:
            return ()
        if not isinstance(raw_required, list) or not all(
            isinstance(input_id, str) and input_id for input_id in raw_required
        ):
            raise ValueError(
                f"pipeline '{pipeline_id}' inputs.required must be a list of strings"
            )
        return tuple(raw_required)

    @classmethod
    def _parse_stage(
        cls, raw_stage: Any, index: int, pipeline_id: str
    ) -> PipelineStageConfig:
        if not isinstance(raw_stage, dict):
            raise ValueError(
                f"stage at index {index} in pipeline '{pipeline_id}' must be a mapping"
            )

        stage_label = f"stage at index {index} in pipeline '{pipeline_id}'"
        stage_id = cls._required_non_empty_string(
            raw_stage, cls.KEY_STAGE_ID, stage_label
        )
        enabled = cls._required_bool(raw_stage, cls.KEY_STAGE_ENABLED, stage_label)
        filename = raw_stage.get(cls.KEY_STAGE_FILENAME)
        pipeline = raw_stage.get(cls.KEY_STAGE_PIPELINE)
        module = raw_stage.get(cls.KEY_STAGE_MODULE, "")

        has_filename = isinstance(filename, str) and bool(filename)
        has_pipeline = isinstance(pipeline, str) and bool(pipeline)
        has_module = isinstance(module, str) and bool(module)

        if sum((has_filename, has_pipeline, has_module)) != 1:
            raise ValueError(
                f"stage '{stage_id}' must define exactly one of "
                "'filename', 'pipeline', or 'module'"
            )

        class_name = raw_stage.get(cls.KEY_STAGE_CLASS)
        if class_name is None:
            class_name = raw_stage.get(cls.KEY_STAGE_CLASS_NAME)
        if has_module and (not isinstance(class_name, str) or not class_name):
            raise ValueError(f"stage '{stage_id}' must have a non-empty 'class'")
        if (
            has_filename
            and class_name is not None
            and (not isinstance(class_name, str) or not class_name)
        ):
            raise ValueError(f"stage '{stage_id}' class must be a non-empty string")

        config = raw_stage.get(cls.KEY_STAGE_CONFIG, {})
        if not isinstance(config, dict):
            raise ValueError(f"stage '{stage_id}' config must be a mapping")

        return PipelineStageConfig(
            id=stage_id,
            enabled=enabled,
            module=module if has_module else "",
            class_name=class_name if isinstance(class_name, str) else "",
            filename=filename if has_filename else None,
            pipeline=pipeline if has_pipeline else None,
            config=config,
        )

    @classmethod
    def _parse_pipeline_edge(cls, raw_edge: Any, index: int) -> PipelineEdge:
        if not isinstance(raw_edge, dict):
            raise ValueError(f"edge at index {index} must be a mapping")

        source = cls._required_non_empty_string(
            raw_edge, cls.KEY_PIPELINE_EDGE_FROM, f"edge at index {index}"
        )
        target = cls._required_non_empty_string(
            raw_edge, cls.KEY_PIPELINE_EDGE_TO, f"edge at index {index}"
        )
        return PipelineEdge(source=source, target=target)

    @classmethod
    def _required_non_empty_string(
        cls, raw_value: dict[str, Any], key: str, field_label: str
    ) -> str:
        value = raw_value.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_label} must have a non-empty '{key}'")
        return value

    @classmethod
    def _required_bool(
        cls, raw_value: dict[str, Any], key: str, field_label: str
    ) -> bool:
        value = raw_value.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"{field_label} must have '{key}' true/false")
        return value

    def _validate_fan_in_requirements(
        self, graph: PipelineGraph, field_label: str, errors: List[str]
    ) -> None:
        for pipeline in graph.pipelines:
            upstream_ids = graph.upstream_ids(pipeline.id)
            if len(upstream_ids) < 2:
                continue

            if not pipeline.required_inputs:
                errors.append(
                    f"{field_label}->pipeline '{pipeline.id}' must define "
                    "inputs.required for fan-in"
                )
                continue

            if set(pipeline.required_inputs) != set(upstream_ids):
                errors.append(
                    f"{field_label}->pipeline '{pipeline.id}' inputs.required "
                    "must match upstream edges"
                )
