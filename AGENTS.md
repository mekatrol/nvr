# Codex Project Notes

## Project Overview

This repository is a small Python NVR service. It starts one `ffmpeg` process per enabled RTSP camera, writes segmented MP4 files, sanitizes RTSP credentials in logs, and moves or deletes old recordings through a background retention thread.

Key entry point:
- `nvr.py` starts config loading, logging, camera recorder threads, retention management, and signal handling.

Core modules:
- `src/nvr_background/main.py` owns background service startup, signal handling, recorder threads, and retention startup.
- `src/nvr_common/config.py` loads `config.yaml`, overlays optional `config.debug.yaml`, expands RTSP credential placeholders from environment variables, and validates config.
- `src/nvr_common/logging/logger.py` configures the singleton application logger.
- `src/nvr_common/logging/rtsp_sanitizing_filter.py` removes RTSP credentials from log output.
- `src/nvr_background/recorder/camera_recorder.py` builds and supervises each `ffmpeg` recorder process.
- `src/nvr_background/recorder/retention_manager.py` moves old `.mp4` segments to backup storage and deletes expired backups.
- `src/nvr_web` is reserved for future web/API work.
- `src/nvr_ui` is the Vue 3 TypeScript Vite SPA subproject for the future debugger UI.

## Local Environment

Use the repository virtual environment when available:

```bash
source .venv/bin/activate
```

Install or refresh dependencies with:

```bash
pip install -r requirements.txt
```

Runtime also requires `ffmpeg` on `PATH`, or `ffmpeg_binary` set in `config.yaml`.

## Configuration

Default config file: `config.yaml`

Local-only overrides: `config.debug.yaml`

`config.debug.yaml` is gitignored and is the preferred place for development paths, disabled cameras, shorter segment durations, and non-production RTSP endpoints.

Required environment variables for real camera URLs:

```bash
export RTSP_USER=...
export RTSP_PASSWORD=...
```

Do not commit real credentials, camera passwords, SMB credentials, or generated recording data.

## Validation Commands

Fast syntax check:

```bash
.venv/bin/python -m compileall nvr.py src
```

Lint:

```bash
.venv/bin/ruff check .
```

Run the service locally:

```bash
.venv/bin/python nvr.py
```

For normal Codex validation, prefer compile and lint. Avoid starting the service unless explicitly requested because it will create directories and try to connect to RTSP cameras.

## Important Behaviors

- RTSP credentials should stay redacted in every log path.
- `Config` and `Logger` are singletons; tests or repeated in-process runs may need to account for cached instances.
- `config.debug.yaml` is automatically merged over `config.yaml` when it exists next to the active config file.
- Camera config is merged by camera `id`; stream config is deep-merged.
- Retention uses file modification time to move primary recordings to backup and delete expired backup recordings.

## Known Caution

The checked-in `config.yaml` uses relative output paths outside this repo (`../../nvr/...`). Be careful when running the service or tests that instantiate `Logger`, since directories may be created relative to the config location.
