import os
from pathlib import Path
from collections.abc import MutableMapping
from typing import Any, Dict, Iterator, List, Set
from urllib.parse import urlparse

import yaml

from utils.singleton import Singleton


class Config(Singleton, MutableMapping):
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
        for camera in self._conf.get("cameras", []):
            if isinstance(camera, dict) and "id" in camera:
                camera_id: str = camera["id"]

                # Expand environment variables inside rtsp_url
                if "rtsp_url" in camera and isinstance(camera["rtsp_url"], str):
                    camera["rtsp_url"] = Config._expand_env_in_url(camera["rtsp_url"])

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

        # storage_root is set and a valid path
        storage_root: Any = self._conf.get("storage_root")
        if not isinstance(storage_root, str) or not storage_root:
            errors.append("storage_root must be a non-empty string")
        else:
            sr_path = Path(storage_root)
            if not sr_path.is_absolute():
                sr_path = (Path(self.config_path).parent / sr_path).resolve()
            if not sr_path.exists() or not sr_path.is_dir():
                errors.append(
                    f"storage_root path does not exist or is not a directory: {sr_path}"
                )

        # log_path is set and a valid path
        log_path: Any = self._conf.get("log_path")
        if not isinstance(log_path, str) or not log_path:
            errors.append("log_path must be a non-empty string")
        else:
            lp_path = Path(log_path)
            if not lp_path.is_absolute():
                lp_path = (Path(self.config_path).parent / lp_path).resolve()
            if not lp_path.exists() or not lp_path.is_dir():
                errors.append(
                    f"log_path path does not exist or is not a directory: {lp_path}"
                )

        # retention_days is valid integer
        retention_days: Any = self._conf.get("retention_days")
        if not isinstance(retention_days, int):
            errors.append("retention_days must be an integer")

        # segment_seconds is valid integer
        segment_seconds: Any = self._conf.get("segment_seconds")
        if not isinstance(segment_seconds, int):
            errors.append("segment_seconds must be an integer")

        # ffmpeg_binary is set
        ffmpeg_binary: Any = self._conf.get("ffmpeg_binary")
        if not isinstance(ffmpeg_binary, str) or not ffmpeg_binary.strip():
            errors.append("ffmpeg_binary must be a non-empty string")

        # cameras validation
        cameras: Any = self._conf.get("cameras", [])
        if not isinstance(cameras, list):
            errors.append("cameras must be a list")
        else:
            ids: Set[str] = set()
            names: Set[str] = set()

            for index, cam in enumerate(cameras):
                if not isinstance(cam, dict):
                    errors.append(f"camera entry at index {index} must be a mapping")
                    continue

                camera_id: Any = cam.get("id")
                if not isinstance(camera_id, str) or not camera_id:
                    errors.append(f"camera at index {index} must have a non-empty 'id'")
                elif camera_id in ids:
                    errors.append(f"duplicate camera id: {camera_id}")
                else:
                    ids.add(camera_id)

                camera_name: Any = cam.get("name")
                if not isinstance(camera_name, str) or not camera_name:
                    errors.append(
                        f"camera '{camera_id or index}' must have a non-empty 'name'"
                    )
                elif camera_name in names:
                    errors.append(f"duplicate camera name: {camera_name}")
                else:
                    names.add(camera_name)

                rtsp_url_val: Any = cam.get("rtsp_url")
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
