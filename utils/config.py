import os
import yaml
import logging
from pathlib import Path
from collections.abc import MutableMapping
from typing import Any, Dict, Iterator, List, Set
from urllib.parse import urlparse
from utils.singleton import Singleton


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
    KEY_CAMERA_RTSP_URL: str = "rtsp_url"

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

    def get_camera(self, camera_id: str) -> Dict[str, Any]:
        return self.cameras_by_id[camera_id]

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
        for cam_id, cam in self.cameras_by_id.items():
            safe_cam = dict(cam)

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
    def _merge_dicts(
        base: Dict[str, Any],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Recursively merge `overrides` into `base`.

        - If a key exists in both and both values are dicts, merge them.
        - Otherwise, the value from `overrides` replaces the one in `base`.
        """
        if not isinstance(base, dict):
            base = {}

        if not isinstance(overrides, dict):
            return base

        for key, override_value in overrides.items():
            base_value: Any = base.get(key)

            if isinstance(base_value, dict) and isinstance(override_value, dict):
                base[key] = Config._merge_dicts(base_value, override_value)
            else:
                base[key] = override_value

        return base

    @staticmethod
    def _load_config(path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data: Any = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}

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

            # Default to 5 minutes
            self.stream_segment_seconds = stream_segment_seconds = 5 * 50

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

        # cameras validation
        cameras: Any = self._conf.get(self.KEY_CAMERAS, [])
        if not isinstance(cameras, list):
            errors.append("cameras must be a list")
        else:
            ids: Set[str] = set()
            names: Set[str] = set()

            for index, cam in enumerate(cameras):
                if not isinstance(cam, dict):
                    errors.append(f"camera entry at index {index} must be a mapping")
                    continue

                camera_id: Any = cam.get(self.KEY_CAMERA_ID)
                if not isinstance(camera_id, str) or not camera_id:
                    errors.append(f"camera at index {index} must have a non-empty 'id'")
                elif camera_id in ids:
                    errors.append(f"duplicate camera id: {camera_id}")
                else:
                    ids.add(camera_id)

                camera_name: Any = cam.get(self.KEY_CAMERA_NAME)
                if not isinstance(camera_name, str) or not camera_name:
                    errors.append(
                        f"camera '{camera_id or index}' must have a non-empty 'name'"
                    )
                elif camera_name in names:
                    errors.append(f"duplicate camera name: {camera_name}")
                else:
                    names.add(camera_name)

                rtsp_url_val: Any = cam.get(self.KEY_CAMERA_RTSP_URL)
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

        if errors:
            message = "Invalid configuration:\n- " + "\n- ".join(errors)
            raise ValueError(message)
