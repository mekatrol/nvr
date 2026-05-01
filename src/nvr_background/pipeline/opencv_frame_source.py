from __future__ import annotations

from typing import Any

import cv2

from nvr_background.pipeline.ffmpeg_rtsp_frame_source import FfmpegRtspFrameSource
from nvr_common.pipeline.frame_validation import bad_frame_reason


class OpenCvFrameSource:
    def __init__(
        self,
        source: str,
        open_timeout_milliseconds: int = 5000,
        read_timeout_milliseconds: int = 5000,
        warmup_frames: int = 30,
        read_drain_frames: int = 3,
        clean_read_attempts: int = 5,
        capture_buffer_size: int = 8,
        ffmpeg_binary: str = "ffmpeg",
        hardware_acceleration: str | None = "auto",
    ) -> None:
        self.source = source
        self.open_timeout_milliseconds = open_timeout_milliseconds
        self.read_timeout_milliseconds = read_timeout_milliseconds
        self.warmup_frames = warmup_frames
        self.read_drain_frames = read_drain_frames
        self.clean_read_attempts = clean_read_attempts
        self.capture_buffer_size = capture_buffer_size
        self.ffmpeg_binary = ffmpeg_binary
        self.hardware_acceleration = hardware_acceleration
        self._capture: Any = None
        self._rtsp_source: FfmpegRtspFrameSource | None = None

    def open(self) -> None:
        if self._is_rtsp_source():
            if self._rtsp_source is not None:
                self._rtsp_source.close()
            self._rtsp_source = FfmpegRtspFrameSource(
                self.source,
                ffmpeg_binary=self.ffmpeg_binary,
                read_timeout_seconds=self.read_timeout_milliseconds / 1000,
                hardware_acceleration=self.hardware_acceleration,
            )
            self._rtsp_source.open()
            return

        self._capture = cv2.VideoCapture()
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, self.capture_buffer_size)
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
        if self._is_rtsp_source():
            if self._rtsp_source is None:
                self.open()
            assert self._rtsp_source is not None
            return self._rtsp_source.read()

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
        if self._rtsp_source is not None:
            self._rtsp_source.close()
            self._rtsp_source = None

        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _is_rtsp_source(self) -> bool:
        return self.source.lower().startswith("rtsp://")

    def _open_capture(self) -> None:
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
