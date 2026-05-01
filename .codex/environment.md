# Codex Environment

## Repo

- Python 3.12.
- Vue 3 + TypeScript + Vite SPA: `src/nvr_ui`.
- Python deps: `requirements.txt`.
- Frontend deps: `src/nvr_ui/package.json`.
- Tool config: `pyproject.toml`.
- Venv: `.venv`.
- Run app: `.venv/bin/python nvr.py`.
- Run background module: `PYTHONPATH=src .venv/bin/python -m nvr_background`.
- Needs `ffmpeg`.

## Config

- Read `pyproject.toml` before Python tooling changes.
- Keep Ruff config and validation commands aligned.

## Prompt Style

- Use caveman prompts.
- Short. Direct. Low-token.
- Prefer imperatives.
- Cut filler.
- Examples: `Fix tests`, `Add camera status API`, `Explain retention bug`, `Refactor config merge`.
- Expand only for precision, safety, or ambiguity.

## Python

- Follow `pyproject.toml`.
- Use Ruff formatter and linter.
- Preserve no-magic-trailing-comma behavior.
- One top-level class per file, including dataclasses.
- No new multi-class Python files.
- No unused imports.

## Design

- No gradients in icons, graphics, UI unless asked.
- No spin controls for float input. Use validated text input.

## Vue

- Order Vue SFC blocks as `template`, then `script`, then `style`.

## Checks

Run before handoff after Python changes:

```bash
.venv/bin/python -m compileall nvr.py src
.venv/bin/ruff check .
```

## Runtime

- Env vars: `RTSP_USER`, `RTSP_PASSWORD`, optional `NVR_CONFIG`.
- Default config: `config.yaml`.
- Do not run service for routine checks. It starts `ffmpeg` and touches camera paths.
- Vue SPA lives under `src/nvr_ui`.
- Keep generated frontend output ignored: `node_modules`, `dist`, `dist-ssr`, coverage, TS build info.

## Image Capture

- RTSP image capture must use `ffmpeg`, not OpenCV `VideoCapture`.
- OpenCV may decode already-complete image bytes or local files.
- Do not use OpenCV as the RTSP/H264/H265 transport or decoder.
- For RTSP H264/H265, prefer `FfmpegRtspFrameSource`.
- Keep ffmpeg RTSP transport on TCP.
