from __future__ import annotations

import select
import subprocess
import time
from typing import BinaryIO

import cv2
import numpy as np


class FfmpegRtspFrameSource:
    def __init__(
        self,
        source: str,
        ffmpeg_binary: str = "ffmpeg",
        read_timeout_seconds: float = 15.0,
        read_chunk_size: int = 65536,
        hardware_acceleration: str | None = "auto",
    ) -> None:
        self.source = source
        self.ffmpeg_binary = ffmpeg_binary
        self.read_timeout_seconds = read_timeout_seconds
        self.read_chunk_size = read_chunk_size
        self.hardware_acceleration = hardware_acceleration
        self._process: subprocess.Popen[bytes] | None = None
        self._buffer = bytearray()

    def open(self) -> None:
        self.close()
        self._process = subprocess.Popen(
            self._build_command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

    def read(self) -> np.ndarray:
        if self._process is None:
            self.open()

        assert self._process is not None
        assert self._process.stdout is not None
        frame = self._read_jpeg_frame(self._process.stdout)
        if frame is None:
            self.close()
            self.open()
            assert self._process is not None
            assert self._process.stdout is not None
            frame = self._read_jpeg_frame(self._process.stdout)

        if frame is None:
            raise RuntimeError(f"unable to decode clean RTSP frame: {self.source}")
        return frame

    def close(self) -> None:
        if self._process is None:
            return

        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
        self._process = None
        self._buffer.clear()

    def _build_command(self) -> list[str]:
        command = [
            self.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-rtsp_flags",
            "prefer_tcp",
            "-fflags",
            "+discardcorrupt",
            "-err_detect",
            "ignore_err",
        ]
        if self.hardware_acceleration:
            command.extend(["-hwaccel", self.hardware_acceleration])
        command.extend(
            [
                "-i",
                self.source,
                "-an",
                "-sn",
                "-dn",
                "-map",
                "0:v:0",
                "-vf",
                "fps=1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-q:v",
                "2",
                "pipe:1",
            ]
        )
        return command

    def _read_jpeg_frame(self, stream: BinaryIO) -> np.ndarray | None:
        deadline = time.monotonic() + self.read_timeout_seconds
        while time.monotonic() < deadline:
            frame_bytes = self._pop_jpeg_frame()
            if frame_bytes:
                frame = cv2.imdecode(
                    np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
                )
                if frame is not None:
                    return frame

            ready, _, _ = select.select(
                [stream], [], [], max(0.0, deadline - time.monotonic())
            )
            if not ready:
                return None

            chunk = stream.read(self.read_chunk_size)
            if not chunk:
                return None
            self._buffer.extend(chunk)

        return None

    def _pop_jpeg_frame(self) -> bytes | None:
        start = self._buffer.find(b"\xff\xd8")
        if start < 0:
            self._buffer.clear()
            return None

        if start > 0:
            del self._buffer[:start]

        end = self._buffer.find(b"\xff\xd9", 2)
        if end < 0:
            return None

        frame_end = end + 2
        frame = bytes(self._buffer[:frame_end])
        del self._buffer[:frame_end]
        return frame
