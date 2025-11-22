from pathlib import Path
import subprocess
import threading
import time

from utils.config import Config
from logging.logger import Logger


class CameraRecorder(threading.Thread):
    def __init__(self, id: str):
        super().__init__(daemon=True)
        self.global_conf = Config()
        self.camera_conf = self.global_conf.get_camera(id)
        self.stop_event = threading.Event()
        self.proc = None
        self.logger = Logger()

        # Per-camera ffmpeg log file
        self.log_dir = Path(self.global_conf.get("log_path", "./logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_log_path = self.log_dir / f"{self.camera_conf['name']}.ffmpeg.log"

    def build_ffmpeg_command(self):
        stream_output_path = Path(self.global_conf.stream_output_path)
        camera_name = self.camera_conf["name"]
        segment_seconds = self.global_conf.stream_segment_seconds
        ffmpeg_bin = self.global_conf.get("ffmpeg_binary", "ffmpeg")

        out_dir = stream_output_path / camera_name
        out_dir.mkdir(parents=True, exist_ok=True)

        # e.g. 20251122_203000_300s.mp4
        out_pattern = str(out_dir / f"%Y%m%d_%H%M%S_{segment_seconds}s.mp4")

        rtsp_url = self.camera_conf["rtsp_url"]

        cmd = [
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

    def stop(self):
        self.stop_event.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def run(self):
        camera_name = self.camera_conf["name"]

        # Only start if enabled
        if not self.camera_conf.get("enabled", True):
            self.logger.log(
                f"Skipping started recorder for camera: {camera_name} as it is disabled"
            )

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
                self.logger.log(
                    f"[{camera_name}] Invalid RTSP URL after env expansion: {rtsp_url!r}"
                )
                time.sleep(10)
                continue

            # Reset per-run state
            auth_error_detected = False

            try:
                # Build a sanitised command string for logging
                safe_cmd = []
                for part in cmd:
                    if isinstance(part, str) and part.startswith("rtsp://"):
                        safe_cmd.append(self.logger._sanitize_rtsp_url(part))
                    else:
                        safe_cmd.append(str(part))

                self.logger.log(
                    f"[{camera_name}] Starting ffmpeg: {' '.join(safe_cmd)}"
                )

                # Start ffmpeg, capturing its stdout+stderr
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                # Stream ffmpeg output to per-camera log, sanitising credentials
                assert self.proc.stdout is not None
                with open(
                    self.ffmpeg_log_path, "a", buffering=1, encoding="utf-8"
                ) as log_file:
                    for line in self.proc.stdout:
                        if line is None:
                            break

                        raw_line = line.rstrip("\n")
                        safe_line = self.logger._sanitize_rtsp_url(raw_line)
                        log_file.write(safe_line + "\n")

                        # Detect auth errors in ffmpeg output (case-insensitive)
                        lower = raw_line.lower()
                        if any(marker in lower for marker in auth_error_markers):
                            auth_error_detected = True

                        if self.stop_event.is_set():
                            break

                # Wait for process to exit (in case stdout loop ended early)
                ret = self.proc.wait()
                self.logger.log(
                    f"[{camera_name}] ffmpeg exited with code {ret} "
                    f"(auth_error_detected={auth_error_detected})"
                )

                self.logger.log(f"Started recorder for camera: {camera_name}")

            except Exception as e:
                self.logger.log(f"[{camera_name}] Error starting ffmpeg: {repr(e)}")
                # In this case we don't know if it's auth-related, so we fall through
                # to the normal retry logic unless stop_event is set.

            # Stop requested: leave the loop
            if self.stop_event.is_set():
                break

            # If we saw an authorization error, do NOT retry.
            if auth_error_detected:
                self.logger.log(
                    f"[{camera_name}] Authorization error detected; "
                    f"will not retry connecting to this camera."
                )
                break

            # Otherwise, normal retry behavior
            self.logger.log(f"[{camera_name}] Restarting ffmpeg in 5s...")
            time.sleep(5)
