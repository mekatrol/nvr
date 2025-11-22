from pathlib import Path
import subprocess
import threading
import time

from utils.config import expand_env_in_url
from logging.logger import Logger


class CameraRecorder(threading.Thread):
    def __init__(self, cam_conf, global_conf):
        super().__init__(daemon=True)
        self.cam_conf = cam_conf
        self.global_conf = global_conf
        self.stop_event = threading.Event()
        self.proc = None
        self.logger = Logger()

        # Per-camera ffmpeg log file
        self.log_dir = Path(self.global_conf.get("log_path", "./logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_log_path = self.log_dir / f"{self.cam_conf['name']}.ffmpeg.log"

    def build_ffmpeg_command(self):
        storage_root = Path(self.global_conf["storage_root"])
        cam_name = self.cam_conf["name"]
        segment_seconds = int(self.global_conf.get("segment_seconds", 300))
        ffmpeg_bin = self.global_conf.get("ffmpeg_binary", "ffmpeg")

        out_dir = storage_root / cam_name
        out_dir.mkdir(parents=True, exist_ok=True)

        # e.g. 20251122_203000_300s.mp4
        out_pattern = str(out_dir / f"%Y%m%d_%H%M%S_{segment_seconds}s.mp4")

        rtsp_url = expand_env_in_url(self.cam_conf["rtsp_url"])

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
        cam_name = self.cam_conf["name"]

        while not self.stop_event.is_set():
            cmd, rtsp_url = self.build_ffmpeg_command()

            # Validate RTSP URL after env expansion
            if (
                not rtsp_url
                or "{RTSP_USER}" in rtsp_url
                or "{RTSP_PASSWORD}" in rtsp_url
            ):
                self.logger.log(
                    f"[{cam_name}] Invalid RTSP URL after env expansion: {rtsp_url!r}"
                )
                time.sleep(10)
                continue

            try:
                # Build a sanitised command string for logging
                safe_cmd = []
                for part in cmd:
                    if isinstance(part, str) and part.startswith("rtsp://"):
                        safe_cmd.append(self.logger.sanitize_rtsp_url(part))
                    else:
                        safe_cmd.append(str(part))

                self.logger.log(f"[{cam_name}] Starting ffmpeg: {' '.join(safe_cmd)}")

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
                        safe_line = self.logger.sanitize_rtsp_url(line.rstrip("\n"))
                        log_file.write(safe_line + "\n")

                        if self.stop_event.is_set():
                            break

                # Wait for process to exit (in case stdout loop ended early)
                ret = self.proc.wait()
                self.logger.log(f"[{cam_name}] ffmpeg exited with code {ret}")

            except Exception as e:
                self.logger.log(f"[{cam_name}] Error starting ffmpeg: {repr(e)}")

            if self.stop_event.is_set():
                break

            self.logger.log(f"[{cam_name}] Restarting ffmpeg in 5s...")
            time.sleep(5)
