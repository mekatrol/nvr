# NVR

Small Python NVR service that records RTSP cameras with `ffmpeg`, manages old recordings, and can run sampled camera frames through a configurable image-processing pipeline graph.

## How It Works

The background service starts one recorder thread per enabled camera. Each recorder launches `ffmpeg`, copies the RTSP stream into segmented MP4 files, and leaves recording independent from image processing.

Pipeline processing runs beside recording through a separate sampled frame acquisition path. A per-camera pipeline worker reads frames with OpenCV at `pipeline_graph.frame_interval_seconds`, runs the configured graph, and logs failures without stopping the recorder.

The pipeline graph is a directed acyclic graph of named pipelines. Each named pipeline contains ordered, pluggable Python stages. Pipeline outputs can fan out to multiple downstream pipelines, and a downstream pipeline can fan in multiple upstream outputs from the same frame.

Example flow:

```text
camera frame
  -> preprocessing
       -> object_detection
            -> post_processing
                 -> approach_detection
                      -> mqtt_events
       -> thumbnail
            -> post_processing
```

The original frame remains available to every stage. Branch metadata is isolated during fan-out. Fan-in pipelines start with empty metadata, so they should explicitly merge the upstream metadata they need, for example with `MergeUpstreamMetadataStage`.

## Repository Layout

- `nvr.py`: thin compatibility launcher for the background service.
- `src/nvr_background`: service startup, recorder lifecycle, retention management, frame acquisition, and camera pipeline workers.
- `src/nvr_common`: shared config, logging, RTSP sanitizing, and pipeline graph primitives.
- `src/nvr_common/pipeline/sample_stages`: OpenCV sample stages, synthetic detection/tracking stages, approach detection, MQTT output, and fan-in metadata merging.
- `src/nvr_web`: standard-library debug API server.
- `src/nvr_ui`: Vue 3 TypeScript Vite debugger UI.
- `tests`: Python unit and integration-style tests.

## Setup

Install `ffmpeg`:

```bash
sudo apt install ffmpeg
ffmpeg -version
```

Create the Python environment:

```bash
cd ~/repos/nvr
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Runtime camera URLs use environment variables:

```bash
export RTSP_USER=...
export RTSP_PASSWORD=...
```

`NVR_CONFIG` is optional and defaults to `config.yaml`:

```bash
export NVR_CONFIG=/path/to/config.yaml
```

Use `config.debug.yaml` next to the active config file for local-only overrides such as development paths, disabled cameras, shorter segment durations, or test RTSP endpoints. Do not commit real camera credentials, SMB credentials, MQTT credentials, generated recordings, or generated debug captures.

## Running

Run the background recorder service:

```bash
.venv/bin/python nvr.py
```

Equivalent module command:

```bash
PYTHONPATH=src .venv/bin/python -m nvr_background
```

Avoid running the service as routine validation because it creates directories and attempts RTSP and `ffmpeg` work for enabled cameras.

Run the debug API:

```bash
PYTHONPATH=src .venv/bin/python -m nvr_web
```

Run the Vue debugger UI:

```bash
cd src/nvr_ui
npm install
npm run dev
```

## Pipeline Configuration

Pipeline stages are normal Python classes loaded from config. A stage receives a `PipelineContext` and returns `PipelineStageResult`.

Minimal stage shape:

```python
class ExampleStage:
    def __init__(self, config):
        ...

    def process(self, context):
        return result
```

The checked-in `config.yaml` includes a runnable sample graph:

```yaml
pipeline_graph:
  enabled: true
  frame_interval_seconds: 1.0
  pipelines:
    - id: preprocessing
      enabled: true
      stages:
        - id: example-crop
          enabled: true
          module: nvr_common.pipeline.sample_stages.crop_stage
          class: CropStage
          config:
            x: 0
            y: 0
            width: 640
            height: 480

    - id: thumbnail
      enabled: true
      stages:
        - id: example-thumbnail
          enabled: true
          module: nvr_common.pipeline.sample_stages.resize_stage
          class: ResizeStage
          config:
            width: 320

  edges:
    - from: preprocessing
      to: thumbnail
```

Global pipeline config can be overridden per camera with a `pipeline_graph` block under that camera. Pipeline overrides merge by pipeline `id`; stage overrides merge by stage `id`.

Graph validation rejects duplicate pipeline ids, duplicate stage ids within a pipeline, unknown edge endpoints, self-edges, and cycles. Fan-in pipelines with multiple upstream edges should declare `inputs.required`.

## Debugger API

The debug backend exposes JSON endpoints for the Vue UI:

- `GET /api/cameras`
- `GET /api/pipeline-graph?camera_id=...`
- `GET /api/debug/state?camera_id=...`
- `POST /api/debug/breakpoints`
- `POST /api/debug/command`
- `GET /api/debug/preview?camera_id=...`
- `GET /api/debug/metadata?camera_id=...`

Debug sessions support run, pause, step, step over one stage, step over one named pipeline, and breakpoints by pipeline or stage. Current previews expose image shape summaries and metadata; encoded preview image streaming is still future work.

## Validation

Use the repository virtual environment:

```bash
.venv/bin/python -m compileall nvr.py src
.venv/bin/ruff check .
PYTHONPATH=src .venv/bin/python -m unittest discover
```

Frontend type check:

```bash
cd src/nvr_ui
npm run type-check
```

The automated end-to-end scenario test runs synthetic frames through preprocessing, person detection, tracking, thumbnail generation, fan-in post-processing, approach detection, fake MQTT output, and debugger records:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_end_to_end_pipeline_scenario
```

## Systemd Service Example

Adjust paths, user, and environment values before using:

```ini
[Unit]
Description=NVR service
After=network-online.target

[Service]
User=user
WorkingDirectory=/home/user/repos/nvr
Environment="RTSP_USER=your_rtsp_username"
Environment="RTSP_PASSWORD=your_rtsp_password"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/home/user/repos/nvr/.venv/bin/python /home/user/repos/nvr/nvr.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable nvr.service
sudo systemctl start nvr.service
sudo systemctl status nvr.service
```

## Current Limits

- Real person detection is still synthetic/configured until a model strategy is selected.
- Live RTSP pipeline acquisition has not been manually tested against real cameras in this repo session.
- Debug previews currently show shape and metadata placeholders, not encoded images.
