from __future__ import annotations

from pathlib import Path
import subprocess
import threading
import time
from typing import List, Tuple, Optional

from utils.config import Config
from log.logger import Logger
from log.rtsp_sanitizing_filter import sanitize_rtsp_url


class CameraRecorder(threading.Thread):
    """
    Per-camera recording thread that runs ffmpeg in a loop, segmenting
    output into files and logging ffmpeg output to a per-camera log file.
    """

    def __init__(self, id: str) -> None:
        super().__init__(daemon=True)

        self.global_conf: Config = Config()
        self.camera_conf = self.global_conf.get_camera(id)
        self.stop_event = threading.Event()
        self.proc: Optional[subprocess.Popen[str]] = None

        # Application logger
        self.logger = Logger().logger

        # Per-camera ffmpeg log file
        self.log_dir = Path(self.global_conf.get("log_path", "./logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_log_path = self.log_dir / f"{self.camera_conf['name']}.ffmpeg.log"

    def build_ffmpeg_command(self) -> Tuple[List[str], str]:
        """
        Build the ffmpeg command and return (cmd_list, rtsp_url).
        """
        stream_output_path = Path(self.global_conf.stream_output_path)
        camera_name = self.camera_conf["name"]
        segment_seconds = self.global_conf.stream_segment_seconds
        ffmpeg_bin = self.global_conf.get("ffmpeg_binary", "ffmpeg")

        out_dir = stream_output_path / camera_name
        out_dir.mkdir(parents=True, exist_ok=True)

        # e.g. 20251122_203000_300s.mp4
        out_pattern = str(out_dir / f"%Y%m%d_%H%M%S_{segment_seconds}s.mp4")

        rtsp_url: str = self.camera_conf["rtsp_url"]

        cmd: List[str] = [
            ffmpeg_bin,
            "-rtsp_transport",
            "tcp",
            "-i",
            rtsp_url,
            "-an",
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            "-strftime",
            "1",
            out_pattern,
        ]

        return cmd, rtsp_url

    def stop(self) -> None:
        """
        Signal the thread to stop and terminate ffmpeg if it is running.
        """
        self.stop_event.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                # Best-effort termination; ignore errors
                pass

    def run(self) -> None:
        camera_name = self.camera_conf["name"]

        # Only start if enabled
        if not self.camera_conf.get("enabled", True):
            self.logger.info(
                "Skipping recorder for camera %s because it is disabled",
                camera_name,
            )
            return

        # Strings to look for in ffmpeg output that indicate an auth problem
        auth_error_markers = [
            "401 unauthorized",
            "403 forbidden",
            "authorization failed",
            "auth failed",
            "unauthorized",  # generic, keep lowercase check
            "authentication failed",
        ]

        while not self.stop_event.is_set():
            cmd, rtsp_url = self.build_ffmpeg_command()

            # Validate RTSP URL after env expansion
            if (
                not rtsp_url
                or "{RTSP_USER}" in rtsp_url
                or "{RTSP_PASSWORD}" in rtsp_url
            ):
                self.logger.info(
                    "[%s] Invalid RTSP URL after env expansion: %r",
                    camera_name,
                    rtsp_url,
                )
                time.sleep(10)
                continue

            auth_error_detected = False

            try:
                # Build a sanitised command string for logging (extra safety;
                # main logger will also sanitize via RtspSanitizingFilter)
                safe_cmd: List[str] = []
                for part in cmd:
                    part_str = str(part)
                    if part_str.startswith("rtsp://"):
                        safe_cmd.append(sanitize_rtsp_url(part_str))
                    else:
                        safe_cmd.append(part_str)

                self.logger.info(
                    "[%s] Starting ffmpeg: %s",
                    camera_name,
                    " ".join(safe_cmd),
                )

                # Start ffmpeg, capturing stdout+stderr
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                assert self.proc.stdout is not None
                with open(
                    self.ffmpeg_log_path,
                    "a",
                    buffering=1,
                    encoding="utf-8",
                ) as log_file:
                    for line in self.proc.stdout:
                        if line is None:
                            break

                        raw_line = line.rstrip("\n")
                        safe_line = sanitize_rtsp_url(raw_line)
                        log_file.write(safe_line + "\n")

                        # Detect auth errors in ffmpeg output (case-insensitive)
                        lower = raw_line.lower()
                        if any(marker in lower for marker in auth_error_markers):
                            auth_error_detected = True

                        if self.stop_event.is_set():
                            break

                # Wait for process to exit (in case stdout loop ended early)
                ret = self.proc.wait()
                self.logger.info(
                    "[%s] ffmpeg exited with code %s (auth_error_detected=%s)",
                    camera_name,
                    ret,
                    auth_error_detected,
                )

            except Exception as e:
                self.logger.error(
                    "[%s] Error starting ffmpeg: %r",
                    camera_name,
                    e,
                )

            if self.stop_event.is_set():
                break

            # If we saw an authorization error, do NOT retry.
            if auth_error_detected:
                self.logger.error(
                    "[%s] Authorization error detected; "
                    "will not retry connecting to this camera.",
                    camera_name,
                )
                break

            # Otherwise, normal retry behavior
            self.logger.info("[%s] Restarting ffmpeg in 5s...", camera_name)
            time.sleep(5)
