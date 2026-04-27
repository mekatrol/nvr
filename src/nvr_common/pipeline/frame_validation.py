from __future__ import annotations

from typing import Any

import numpy as np


def bad_frame_reason(frame: Any) -> str | None:
    if not isinstance(frame, np.ndarray):
        return f"frame is {type(frame).__name__}, expected numpy.ndarray"
    if frame.size == 0:
        return "frame is empty"
    if frame.ndim not in (2, 3):
        return f"frame has unsupported dimensions: {frame.shape}"

    height, width = frame.shape[:2]
    if height < 1 or width < 1:
        return f"frame has invalid size: {frame.shape}"

    if frame.ndim == 3 and frame.shape[2] not in (1, 3, 4):
        return f"frame has unsupported channel count: {frame.shape}"

    if not np.issubdtype(frame.dtype, np.number):
        return f"frame has unsupported dtype: {frame.dtype}"

    if np.issubdtype(frame.dtype, np.floating) and not np.isfinite(frame).all():
        return "frame contains non-finite values"

    if _has_large_decoder_green_region(frame):
        return "frame contains a large green decoder artifact"

    return None


def _has_large_decoder_green_region(frame: np.ndarray) -> bool:
    if frame.ndim != 3 or frame.shape[2] < 3:
        return False

    bgr = frame[:, :, :3].astype(np.float32, copy=False)
    blue = bgr[:, :, 0]
    green = bgr[:, :, 1]
    red = bgr[:, :, 2]
    green_mask = (
        (green >= 70)
        & (green >= (red * 1.6 + 25))
        & (green >= (blue * 1.6 + 25))
    )
    if np.count_nonzero(green_mask) / green_mask.size >= 0.18:
        return True

    column_green_ratio = green_mask.mean(axis=0)
    green_columns = column_green_ratio >= 0.75
    min_band_width = max(1, int(frame.shape[1] * 0.12))
    return _has_run(green_columns, min_band_width)


def _has_run(values: np.ndarray, minimum_length: int) -> bool:
    run_length = 0
    for value in values:
        if value:
            run_length += 1
            if run_length >= minimum_length:
                return True
        else:
            run_length = 0
    return False
