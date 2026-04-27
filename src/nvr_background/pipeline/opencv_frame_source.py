from __future__ import annotations

import os
from typing import Any

import cv2


class OpenCvFrameSource:
    def __init__(
        self,
        source: str,
        open_timeout_milliseconds: int = 5000,
        read_timeout_milliseconds: int = 5000,
        warmup_frames: int = 8,
        read_drain_frames: int = 3,
    ) -> None:
        self.source = source
        self.open_timeout_milliseconds = open_timeout_milliseconds
        self.read_timeout_milliseconds = read_timeout_milliseconds
        self.warmup_frames = warmup_frames
        self.read_drain_frames = read_drain_frames
        self._capture: Any = None

    def open(self) -> None:
        self._capture = cv2.VideoCapture()
        self._configure_rtsp_transport()
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._capture.set(
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_milliseconds
        )
        self._capture.set(
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_milliseconds
        )
        self._capture.open(self.source)
        if not self._capture.isOpened():
            raise RuntimeError(f"unable to open frame source: {self.source}")
        self._discard_warmup_frames()

    def read(self) -> Any:
        if self._capture is None:
            self.open()
        try:
            return self._read_latest_frame()
        except RuntimeError:
            self.close()
            self.open()
            return self._read_latest_frame()

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _configure_rtsp_transport(self) -> None:
        if not self.source.lower().startswith("rtsp://"):
            return
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

    def _discard_warmup_frames(self) -> None:
        if self._capture is None:
            return

        for _ in range(max(0, self.warmup_frames)):
            if not self._capture.grab():
                break

    def _read_latest_frame(self) -> Any:
        frame = None
        ok = False
        for _ in range(max(1, self.read_drain_frames)):
            ok, next_frame = self._capture.read()
            if ok and next_frame is not None:
                frame = next_frame
            else:
                break

        if frame is None:
            raise RuntimeError(f"unable to read frame from source: {self.source}")
        return frame
