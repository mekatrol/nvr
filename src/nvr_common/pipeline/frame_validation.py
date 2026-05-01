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

    return None
