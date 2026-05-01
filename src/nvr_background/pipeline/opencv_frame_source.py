from __future__ import annotations

import os
from typing import Any

import cv2

from nvr_common.pipeline.frame_validation import bad_frame_reason

RTSP_FFMPEG_CAPTURE_OPTIONS = (
    "rtsp_transport;tcp"
    "|fflags;discardcorrupt+nobuffer"
    "|flags;low_delay"
    "|err_detect;explode"
    "|max_delay;500000"
    "|reorder_queue_size;0"
)


class OpenCvFrameSource:
    def __init__(
        self,
        source: str,
        open_timeout_milliseconds: int = 5000,
        read_timeout_milliseconds: int = 5000,
        warmup_frames: int = 8,
        read_drain_frames: int = 3,
        clean_read_attempts: int = 5,
    ) -> None:
        self.source = source
        self.open_timeout_milliseconds = open_timeout_milliseconds
        self.read_timeout_milliseconds = read_timeout_milliseconds
        self.warmup_frames = warmup_frames
        self.read_drain_frames = read_drain_frames
        self.clean_read_attempts = clean_read_attempts
        self._capture: Any = None

    def open(self) -> None:
        self._capture = cv2.VideoCapture()
        self._configure_rtsp_capture_options()
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._capture.set(
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_milliseconds
        )
        self._capture.set(
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_milliseconds
        )
        self._open_capture()
        if not self._capture.isOpened():
            raise RuntimeError(f"unable to open frame source: {self.source}")
        self._discard_warmup_frames()

    def read(self) -> Any:
        if self._capture is None:
            self.open()

        last_error = None
        attempts = max(1, self.clean_read_attempts)
        for attempt in range(attempts):
            try:
                frame = self._read_latest_frame()
            except RuntimeError as ex:
                last_error = str(ex)
                self.close()
                self.open()
                continue

            reason = bad_frame_reason(frame)
            if reason is None:
                return frame

            last_error = reason
            if attempt < attempts - 1:
                self._discard_warmup_frames()

        raise RuntimeError(
            f"unable to read clean frame from source: {self.source}; {last_error}"
        )

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _configure_rtsp_capture_options(self) -> None:
        if not self.source.lower().startswith("rtsp://"):
            return
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS", RTSP_FFMPEG_CAPTURE_OPTIONS
        )

    def _open_capture(self) -> None:
        if self.source.lower().startswith("rtsp://"):
            self._capture.open(self.source, cv2.CAP_FFMPEG)
            return
        self._capture.open(self.source)

    def _discard_warmup_frames(self) -> None:
        if self._capture is None:
            return

        for _ in range(max(0, self.warmup_frames)):
            ok, frame = self._capture.read()
            if not ok or frame is None:
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
