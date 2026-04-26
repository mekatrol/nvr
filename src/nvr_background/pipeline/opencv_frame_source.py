from __future__ import annotations

from typing import Any

import cv2


class OpenCvFrameSource:
    def __init__(
        self,
        source: str,
        open_timeout_milliseconds: int = 5000,
        read_timeout_milliseconds: int = 5000,
    ) -> None:
        self.source = source
        self.open_timeout_milliseconds = open_timeout_milliseconds
        self.read_timeout_milliseconds = read_timeout_milliseconds
        self._capture: Any = None

    def open(self) -> None:
        self._capture = cv2.VideoCapture()
        self._capture.set(
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_milliseconds
        )
        self._capture.set(
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_milliseconds
        )
        self._capture.open(self.source)
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
