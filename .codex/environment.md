# Codex Environment

This Codex workspace has been initialized for the NVR repository.

## Repository Shape

- Language: Python 3.12
- Frontend: Vue 3 TypeScript Vite SPA in `src/nvr_ui`
- Dependency file: `requirements.txt`
- Frontend dependency file: `src/nvr_ui/package.json`
- Tool configuration: `pyproject.toml`
- Existing virtual environment: `.venv`
- Main command: `.venv/bin/python nvr.py`
- Background module command: `PYTHONPATH=src .venv/bin/python -m nvr_background`
- Main external dependency: `ffmpeg`

## Project Configuration

Check `pyproject.toml` before making Python formatting, linting, or tooling changes. It is the source of project-specific Ruff configuration and should be kept in sync with validation commands.

## Project-Specific Coding Standards

### Python

- Read and follow the rules defined in `pyproject.toml` before making Python changes.
- Use Ruff as the Python formatter and linter for this repository.
- Preserve formatter behavior that avoids magic trailing commas / dangling commas.
- Keep one top-level class per file, including dataclasses.
- Do not introduce new Python files that contain multiple classes.
- Unused Python imports are not allowed.

### Design

- Avoid gradient colors in icons, graphics, and UI styling unless explicitly requested.
- Do not use spin controls for floating-point entry in the UI; use validated text inputs instead.

## Safe Default Checks

Run these before handing back Python changes:

```bash
.venv/bin/python -m compileall nvr.py src
.venv/bin/ruff check .
```

## Runtime Notes

The app expects RTSP credentials in environment variables and camera definitions in YAML:

```bash
RTSP_USER
RTSP_PASSWORD
NVR_CONFIG
```

`NVR_CONFIG` is optional and defaults to `config.yaml`.

Avoid running the service as a routine check because it launches `ffmpeg` subprocesses for configured cameras.

The Vue SPA is a separate Node/Vite subproject under `src/nvr_ui`. Its generated directories such as `node_modules`, `dist`, `dist-ssr`, coverage output, and TypeScript build info should remain ignored.
