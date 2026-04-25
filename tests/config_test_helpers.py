import os
from pathlib import Path

import yaml

from nvr_common.config import Config


def reset_config_singleton():
    if hasattr(Config, "_instance"):
        delattr(Config, "_instance")


def write_config(path: Path, pipeline_graph: dict, cameras: list[dict] | None = None):
    config = {
        "log_path": "../../nvr/logs",
        "ffmpeg_binary": "ffmpeg",
        "stream": {
            "segment_seconds": 300,
            "output_path": "../../nvr/streams",
            "retention_days": 0.1,
            "backup_retention_days": 5,
            "backup_output_path": "../../nvr/streams/backup",
        },
        "pipeline_graph": pipeline_graph,
        "cameras": cameras
        or [
            {
                "id": "driveway",
                "name": "driveway",
                "enabled": True,
                "log_ffmpeg": False,
                "rtsp_url": "rtsp://{RTSP_USER}:{RTSP_PASSWORD}@camera/stream",
            }
        ],
    }
    path.write_text(yaml.safe_dump(config), encoding="utf-8")


def set_config_env(path: Path):
    os.environ["NVR_CONFIG"] = str(path)
    os.environ["RTSP_USER"] = "user"
    os.environ["RTSP_PASSWORD"] = "password"
    reset_config_singleton()
