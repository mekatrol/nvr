import os

import yaml


def expand_env_in_url(url: str) -> str:
    return url.format(
        RTSP_USER=os.environ.get("RTSP_USER", ""),
        RTSP_PASSWORD=os.environ.get("RTSP_PASSWORD", ""),
    )


def merge_dicts(base: dict, overrides: dict) -> dict:
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
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(override_value, dict)
        ):
            merge_dicts(base[key], override_value)
        else:
            base[key] = override_value
    return base


def load_config(path: str):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
