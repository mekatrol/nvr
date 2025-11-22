import os
from pathlib import Path
from collections.abc import MutableMapping
from typing import Any, Dict, Iterator, List, Set
from urllib.parse import urlparse

import yaml

from utils.singleton import Singleton


class Config(Singleton, MutableMapping):
    # Config key constants
    KEY_LOG_PATH: str = "log_path"
    KEY_STREAM: str = "stream"
    KEY_STREAM_OUTPUT_PATH: str = "output_path"
    KEY_STREAM_SEGMENT_SECONDS: str = "segment_seconds"
    KEY_STREAM_RETENTION_DAYS: str = "retention_days"
    KEY_FFMPEG_BINARY: str = "ffmpeg_binary"
    KEY_CAMERAS: str = "cameras"
    KEY_CAMERA_ID: str = "id"
    KEY_CAMERA_NAME: str = "name"
    KEY_CAMERA_RTSP_URL: str = "rtsp_url"

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

    def _validate(self) -> None:
        errors: List[str] = []

        # log_path is set and a valid path
        log_path: Any = self._conf.get(self.KEY_LOG_PATH)
        if not isinstance(log_path, str) or not log_path:
            errors.append("stream->log_path must be a non-empty string")
        else:
            path = Path(log_path)
            if not path.is_absolute():
                path = (Path(self.config_path).parent / path).resolve()
            if not path.exists() or not path.is_dir():
                errors.append(
                    f"stream->log_path path does not exist or is not a directory: {path}"
                )

        stream_cfg = self._conf.get(self.KEY_STREAM)
        if not isinstance(stream_cfg, dict):
            errors.append("stream must be a dictionary value")
        else:
            # stream output path is set and a valid path
            stream_output_path: Any = stream_cfg.get(self.KEY_STREAM_OUTPUT_PATH)
            if not isinstance(stream_output_path, str) or not stream_output_path:
                errors.append("stream->output_path must be a non-empty string")
            else:
                path = Path(stream_output_path)
                if not path.is_absolute():
                    path = (Path(self.config_path).parent / path).resolve()
                if not path.exists() or not path.is_dir():
                    errors.append(
                        f"stream->output_path does not exist or is not a directory: {path}"
                    )

            # retention_days is valid integer
            stream_retention_days: Any = stream_cfg.get(self.KEY_STREAM_RETENTION_DAYS)
            if not isinstance(stream_retention_days, int):
                errors.append("stream->retention_days must be an integer")

            # segment_seconds is valid integer
            stream_segment_seconds: Any = stream_cfg.get(
                self.KEY_STREAM_SEGMENT_SECONDS
            )
            if not isinstance(stream_segment_seconds, int):
                errors.append("stream->segment_seconds must be an integer")

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
