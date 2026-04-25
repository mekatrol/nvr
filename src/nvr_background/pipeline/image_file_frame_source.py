from __future__ import annotations

from typing import Any

import cv2


class ImageFileFrameSource:
    def __init__(self, path: str) -> None:
        self.path = path

    def open(self) -> None:
        return

    def read(self) -> Any:
        frame = cv2.imread(self.path, cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError(f"unable to read image fixture: {self.path}")
        return frame

    def close(self) -> None:
        return
