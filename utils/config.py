import os
from pathlib import Path
from collections.abc import MutableMapping
from typing import Any, Dict

import yaml

from utils.singleton import Singleton


class Config(Singleton, MutableMapping):
    _conf: Dict[str, Any] = {}

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

        self.cameras_by_id = {}
        for camera in self._conf.get("cameras", []):
            if isinstance(camera, dict) and "id" in camera:
                cam_id = camera["id"]

                # Expand environment variables inside rtsp_url
                if "rtsp_url" in camera:
                    camera["rtsp_url"] = Config._expand_env_in_url(camera["rtsp_url"])

                self.cameras_by_id[cam_id] = camera

    def get_camera(self, camera_id: str) -> Dict[str, Any]:
        return self.cameras_by_id[camera_id]

    def __getitem__(self, key: str) -> Any:
        return self._conf[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._conf[key] = value

    def __delitem__(self, key: str) -> None:
        del self._conf[key]

    def __iter__(self):
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
