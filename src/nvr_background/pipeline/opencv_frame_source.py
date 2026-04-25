from __future__ import annotations

from typing import Any

import cv2


class OpenCvFrameSource:
    def __init__(self, source: str) -> None:
        self.source = source
        self._capture: Any = None

    def open(self) -> None:
        self._capture = cv2.VideoCapture(self.source)
        if not self._capture.isOpened():
            raise RuntimeError(f"unable to open frame source: {self.source}")

    def read(self) -> Any:
        if self._capture is None:
            self.open()
        ok, frame = self._capture.read()
        if not ok:
            raise RuntimeError(f"unable to read frame from source: {self.source}")
        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
