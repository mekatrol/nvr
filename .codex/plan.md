# NVR Image Processing Pipeline Plan

## Goal

Add a configurable image processing pipeline graph to the NVR service so camera frames can pass through named, reusable pipelines made from pluggable Python stages. Pipelines can perform transformations, filtering, clipping, AI detection, object tracking, movement analysis, thumbnail generation, post processing, and event output such as MQTT messages.

A named pipeline is an ordered chain of stages. Pipeline outputs can feed one or more downstream pipelines, and a downstream pipeline can receive inputs from multiple upstream pipelines. This allows flows such as `preprocessing` feeding both `object_detection` and `thumbnail`, then combining those outputs in a later `post_processing` pipeline.

The target scenario is monitoring a camera for a person approaching in a configured direction, then emitting an MQTT message that can trigger actions such as turning on a light.

## Working Rules

- At the start of every new Codex session, read `.codex/environment.md` first. Do this even if the user does not explicitly ask for it.
- After `.codex/environment.md`, read `.codex/architecture.md`, this file, `AGENTS.md`, and the files relevant to the next task.
- Treat this file as the source of truth for phased progress. Update task status, notes, decisions, blockers, and validation results before ending each implementation session.
- Work in milestone-sized phases. Do not attempt the whole plan in one session unless explicitly requested.
- The first implementation phase must restructure the repository into a `src` layout that separates background process code from web/API code.
- Do not run `.venv/bin/python nvr.py` as routine validation because it launches camera and `ffmpeg` work.
- Use the repository virtual environment when running Python checks.
- Validate Python changes with:
  - `.venv/bin/python -m compileall nvr.py src`
  - `.venv/bin/ruff check .`
- After the `src` restructure is complete, update `.codex/environment.md`, this plan, and validation commands to use the new paths.
- Preserve RTSP credential redaction in all logging paths.
- Do not commit or write real camera credentials, MQTT credentials, generated recordings, or generated debug captures.
- The Vue app has been manually created by the user under `src/nvr_ui`. Treat it as a Vite SPA subproject, not as Python package code.

## Current Status

Status: Phase 11 complete; Phase 12 pending

The repository has been restructured into a `src` layout. Phase 2 discovery chose
a separate sampled frame acquisition path for initial pipeline input, leaving the
existing ffmpeg recording subprocess untouched. Core pipeline graph interfaces,
validation, dynamic stage loading, synthetic-frame execution, YAML
configuration parsing, OpenCV-backed sample stages, camera pipeline worker
prototype, synthetic detection/tracking/event stages, debug backend, web API
boundary, and Vue debugger UI now exist.

## Key Design Decisions

- Decision: Restructure the codebase into a `src` layout before adding pipeline features.
  Status: accepted
  Notes: Current layout uses Python packages `nvr_background`, `nvr_common`, and `nvr_web`, plus the Vue SPA subproject at `src/nvr_ui`.

- Decision: Keep the web backend and Vue SPA as separate codebases.
  Status: accepted
  Notes: `src/nvr_web` is the Python backend/API package. `src/nvr_ui` is the Vue 3 TypeScript Vite SPA with its own `package.json`, `package-lock.json`, and frontend toolchain.

- Decision: Use OpenCV as the likely image processing foundation.
  Status: accepted
  Notes: Phase 5 added `opencv-python-headless` for service-side image processing without GUI dependencies.

- Decision: Pipeline modules are normal Python modules loaded through configuration.
  Status: accepted
  Notes: `PipelineStageLoader` imports the configured module and class name, instantiates the class with its config dictionary, and expects a `process(context)` method returning `PipelineStageResult`.

- Decision: The processing system is a graph of named pipelines, not only one linear pipeline.
  Status: accepted
  Notes: A named pipeline contains an ordered chain of stages. Pipeline outputs can fan out to multiple downstream pipelines and fan in from multiple upstream pipelines. See `.codex/architecture.md`.

- Decision: Each stage receives the original image, the current image, and mutable metadata.
  Status: accepted
  Notes: The original image must remain available to every stage in every named pipeline and must not be overwritten by downstream transformations.

- Decision: Disabled stages stay configured but are skipped at runtime.
  Status: accepted
  Notes: This allows users to turn modules on and off without deleting configuration.

- Decision: Initial pipeline input comes from a separate sampled frame acquisition path, not from the recording ffmpeg process.
  Status: accepted
  Notes: `CameraRecorder` currently runs ffmpeg with `-c copy` into segmented MP4 files and does not expose decoded frames. Phase 6 should add a separate per-camera pipeline worker that samples RTSP frames at the configured interval, so pipeline failures and decode overhead stay isolated from recording.

- Decision: Pipeline configuration supports global defaults plus per-camera overrides.
  Status: accepted
  Notes: Global graph configuration defines reusable defaults. Camera-level overrides can disable or customize pipeline behavior for individual cameras while preserving existing camera-list merge behavior by camera `id`.

- Decision: Initial graph support is directed acyclic only.
  Status: accepted
  Notes: Reject cycles during configuration or graph validation. Feedback loops can be reconsidered later with explicit buffering, scheduling, and termination rules.

- Decision: Initial fan-in behavior requires all configured upstream inputs for the same frame.
  Status: accepted
  Notes: Phase 3 should model required inputs and same-frame correlation. Timeout and partial-input behavior are deferred until the graph runner is connected to live acquisition.

- Decision: Debugging should support step, run, breakpoint, step over a single module stage, and step over a whole named pipeline.
  Status: accepted
  Notes: Implemented through `PipelineDebugSession`, `nvr_web` debug API endpoints, and the Vue debugger UI.

## Open Questions

- Should processed images be persisted for debugging, kept in memory, or both?
- Which MQTT broker settings and topic format should be supported?
- Should AI detection use a bundled model, a user-provided model path, or an external service?
- What timeout should apply when a fan-in pipeline waits for multiple upstream outputs from the same frame?
- How should branch metadata conflicts be resolved when two upstream pipelines write the same metadata key?

## Proposed Architecture

Detailed architecture lives in `.codex/architecture.md`. Keep this section as the implementation tracking summary.

### Runtime Concepts

- `PipelineGraph`: directed acyclic graph of named pipelines and edges.
- `NamedPipeline`: ordered chain of configured stages with one functional purpose, such as preprocessing or object detection.
- `PipelineInput`: original image, current image, metadata, camera id, frame timestamp, and source pipeline id.
- `PipelineOutput`: output image, metadata, debug artifacts, timing, status, and pipeline id.
- `PipelineContext`: immutable or controlled-access context shared across stages. Expected fields include camera id, frame timestamp, original image, current image, upstream inputs, metadata, config, and logger.
- `PipelineStage`: a plugin-defined processing unit. It receives context and returns an updated image plus metadata changes.
- `PipelineGraphRunner`: loads configured named pipelines, validates edges, executes stages, handles fan-out and fan-in, skips disabled stages, and reports debug events.
- `PipelineRegistry` or loader: imports plugin modules from configuration and instantiates stages using a defined factory or class name.
- `PipelineDebugSession`: coordinates paused execution, breakpoints, step, run, and step-over behavior.
- `PipelineDebugStore`: stores current input/output images and metadata for the web UI during debugging.

### Data Flow

1. A camera frame enters the pipeline graph.
2. The original image is stored once and remains available to every pipeline and stage.
3. One or more source pipelines receive the frame.
4. Each named pipeline runs its enabled stages in order.
5. Each stage receives the original image, the pipeline current image, upstream inputs, and metadata.
6. The stage returns a new current image and optional metadata updates.
7. A pipeline output can fan out to one or more downstream pipelines.
8. A downstream pipeline can fan in outputs from two or more upstream pipelines and process them as a set.
9. Final image and metadata outputs are returned to the caller or terminal side-effect pipelines.
10. Event-producing stages can emit side effects through controlled services, such as MQTT.

### Plugin Contract

Define the exact contract during Phase 3, but the expected shape is:

```python
class ExampleStage:
    def __init__(self, config):
        ...

    def process(self, context):
        return result
```

The result should include:

- output image for the next stage
- metadata updates
- optional debug artifacts
- optional emitted events

For fan-in pipelines, the context should expose the set of upstream pipeline outputs as named inputs.

## Configuration Direction

Expected YAML shape, subject to refinement:

```yaml
pipeline_graph:
  enabled: true
  frame_interval_seconds: 1.0

  pipelines:
    - id: preprocessing
      enabled: true
      stages:
        - id: clip-driveway
          enabled: true
          module: pipeline_plugins.clip
          class: ClipStage
          config:
            x: 100
            y: 50
            width: 800
            height: 600

    - id: object_detection
      enabled: true
      stages:
        - id: person-detection
          enabled: true
          module: pipeline_plugins.person_detector
          class: PersonDetectorStage
          config:
            confidence_threshold: 0.6

    - id: thumbnail
      enabled: true
      stages:
        - id: make-thumbnail
          enabled: true
          module: pipeline_plugins.thumbnail
          class: ThumbnailStage
          config:
            width: 320

    - id: post_processing
      enabled: true
      inputs:
        required:
          - object_detection
          - thumbnail
      stages:
        - id: combine-results
          enabled: true
          module: pipeline_plugins.combine
          class: CombineResultsStage
          config: {}

    - id: mqtt_events
      enabled: true
      stages:
        - id: mqtt-event
          enabled: true
          module: pipeline_plugins.mqtt_event
          class: MqttEventStage
          config:
            topic: nvr/front-door/person-approaching

  edges:
    - from: preprocessing
      to: object_detection
    - from: preprocessing
      to: thumbnail
    - from: object_detection
      to: post_processing
    - from: thumbnail
      to: post_processing
    - from: post_processing
      to: mqtt_events
```

## Phases

### Phase 1: Restructure Into `src`

Status: complete

Purpose: Move the current Python code into a `src` layout and create clear boundaries between background processes, common/shared code, and future web/API code before adding the pipeline graph.

Target direction:

- Background process code: recorder lifecycle, retention, service startup, signal handling, and camera processing.
- Common code: configuration, logging, RTSP sanitizing, shared models, and later pipeline graph primitives.
- Web/API code: future debug API and web server integration.
- Root scripts: keep only thin compatibility launchers or project entry points.

Tasks:

- [x] Read current imports and entry points in `nvr.py`, `utils`, `log`, and `recorder`.
- [x] Choose the concrete `src` package layout.
- [x] Move current background service modules under `src`.
- [x] Separate shared modules from background-only modules.
- [x] Reserve a web/API package path for later debug API work without implementing the API yet.
- [x] Update imports after the move.
- [x] Update `pyproject.toml` if needed so Ruff and tests understand the new source layout.
- [x] Update validation commands in `.codex/environment.md`, `AGENTS.md` if appropriate, and this plan.
- [x] Keep `nvr.py` as a thin launcher or replace it with a documented module entry point.
- [x] Add or update smoke tests for importability if a test framework exists.
- [x] Update this file with the final chosen layout.

Final layout:

- `nvr.py`: compatibility launcher that adds `src` to `sys.path` and delegates to `nvr_background.main`.
- `src/nvr_background`: background service package, including recorder and retention lifecycle code.
- `src/nvr_common`: shared configuration, singleton, and logging code.
- `src/nvr_web`: reserved Python package for future debug API and web integration.
- `src/nvr_ui`: Vue 3 TypeScript Vite SPA subproject for the future debugger UI.

Milestone test:

- [x] Run the updated compileall command for the new `src` paths.
- [x] Run `.venv/bin/ruff check .`.
- [x] Do not run the service unless explicitly requested.

### Phase 2: Discovery and Shape

Status: complete

Purpose: Understand the current recorder lifecycle and choose where the pipeline should attach without disrupting recording.

Tasks:

- [x] Read the restructured service entry point, config module, camera recorder, and retention manager.
- [x] Identify where camera frames or snapshots can be obtained safely.
- [x] Decide whether initial pipeline input comes from live frames, snapshots, or recorded segments.
- [x] Decide whether pipeline configuration is global, per camera, or both.
- [x] Decide whether the first implementation supports only acyclic graphs or reserves support for explicit feedback loops later.
- [x] Decide the initial fan-in behavior: require all upstream inputs, allow partial input, or configure per pipeline.
- [x] Document the chosen integration point in this file.

Discovery notes:

- `nvr.py` is only a compatibility launcher. `src/nvr_background/main.py` owns service startup, starts one `CameraRecorder` thread per enabled camera, starts `RetentionManager`, and coordinates shutdown.
- `CameraRecorder` owns recording only. It starts a camera-specific ffmpeg process using RTSP TCP input, `-an`, `-c copy`, segment muxing, strftime output names, and stdout/stderr monitoring. Because the recorder copies encoded packets directly into MP4 segments, it does not decode frames or provide an in-process frame stream.
- `RetentionManager` only moves and deletes completed `.mp4` files by modification time. It is not a good pipeline input point for near-real-time detection and should remain independent from image processing.
- The safest initial integration point is a new background pipeline worker started from `src/nvr_background/main.py` alongside each enabled `CameraRecorder`. The worker should use the camera's expanded RTSP URL through a separate sampled frame reader, apply `pipeline_graph.frame_interval_seconds`, and pass decoded frames to the graph runner.
- Recording must remain the primary behavior. Pipeline worker failures should be logged, sanitized, and isolated from recorder threads. The recorder should not depend on pipeline startup, pipeline frame decoding, model loading, MQTT output, or debugger state.
- Initial graph execution should use generated images or fixture inputs during Phase 3 through Phase 5. Live RTSP acquisition belongs in Phase 6 after the graph interfaces and config validation exist.
- Pipeline configuration should start with global defaults and allow per-camera overrides. This fits the existing `config.debug.yaml` overlay and camera merge-by-`id` behavior while letting individual cameras disable or tune processing.
- Initial graph validation should reject cycles. Feedback loops are out of scope until explicit scheduling semantics exist.
- Initial fan-in should require all configured upstream outputs for the same frame before running the downstream pipeline. Partial fan-in and timeout behavior remain open for the live acquisition phase.

Milestone test:

- [x] No code required unless needed for discovery.
- [x] If code changes are made, run compileall and Ruff.

### Phase 3: Core Pipeline Interfaces

Status: complete

Purpose: Add the backend abstractions for graph-based image and metadata flow without connecting to live cameras yet.

Tasks:

- [x] Add a pipeline package with one top-level class per file.
- [x] Define named pipeline, graph, edge, input, context, output, and result data structures.
- [x] Define the plugin stage contract.
- [x] Implement stage loading from Python module and class names.
- [x] Implement enabled/disabled stage skipping.
- [x] Implement graph validation for duplicate pipeline ids, unknown edge references, and cycles.
- [x] Implement fan-out from one pipeline output to multiple downstream pipelines.
- [x] Implement basic fan-in where one pipeline receives outputs from multiple upstream pipelines for the same frame.
- [x] Ensure original image and current branch image are both available to every stage.
- [x] Ensure branch metadata is isolated unless a stage explicitly combines upstream metadata.
- [x] Add focused unit tests using synthetic images.

Implementation notes:

- Added `src/nvr_common/pipeline` with shared graph primitives, pipeline input/output/context objects, stage result objects, a plugin protocol, dynamic stage loading, graph validation, and a synchronous graph runner.
- `PipelineGraph.validate()` rejects duplicate pipeline ids, duplicate stage ids within a pipeline, unknown edge endpoints, self-edges, and cycles.
- `PipelineGraphRunner` starts at source pipelines, executes enabled stages in topological order, skips disabled stages, fans outputs to downstream pipelines, and runs fan-in pipelines once required upstream inputs for the frame are present.
- Fan-out downstream inputs receive deep-copied metadata so branch stages do not mutate sibling branch metadata.
- Fan-in pipelines receive all upstream inputs through `PipelineContext.upstream_inputs`. Their starting metadata is empty so metadata conflicts must be resolved explicitly by a combining stage.
- Tests use standard-library `unittest` and synthetic string images to keep Phase 3 independent from OpenCV.

Milestone test:

- [x] Run unit tests for the pipeline package.
- [x] Run the updated compileall command for the `src` layout.
- [x] Run `.venv/bin/ruff check .`.

### Phase 4: Configuration Support

Status: complete

Purpose: Extend config loading and validation for pipeline settings.

Tasks:

- [x] Add pipeline config parsing.
- [x] Support global defaults and per-camera overrides if selected in Phase 2.
- [x] Validate required pipeline fields: `id`, `enabled`, and `stages`.
- [x] Validate required edge fields: `from` and `to`.
- [x] Validate required stage fields: `id`, `enabled`, `module`, and class or factory reference.
- [x] Validate stage config remains a dictionary.
- [x] Validate fan-in input requirements for pipelines with multiple upstream edges.
- [x] Add example disabled stages to `config.yaml` without real credentials.
- [x] Add tests for config merge behavior, including `config.debug.yaml` overlays.

Implementation notes:

- Added `Config.get_pipeline_graph_config()`, `Config.get_pipeline_graph()`, and `Config.get_pipeline_frame_interval_seconds()` for global and per-camera pipeline configuration access.
- Pipeline graph overrides merge by pipeline `id`, and stage overrides merge by stage `id`, so camera-level config can disable or customize a shared stage without duplicating the whole graph.
- YAML validation now checks required pipeline, edge, and stage fields; stage config mapping shape; graph references and cycles through `PipelineGraph.validate()`; and explicit `inputs.required` entries for fan-in pipelines with multiple upstream edges.
- `config.debug.yaml` overlays use the same merge behavior as camera overrides.
- `config.yaml` now includes a disabled example pipeline graph with placeholder sample stage module paths and no real credentials.

Milestone test:

- [x] Run config tests.
- [x] Run compileall and Ruff.

Validation results:

- [x] `PYTHONPATH=src .venv/bin/python -m unittest tests.test_config_pipeline_graph`
- [x] `PYTHONPATH=src .venv/bin/python -m unittest discover`
- [x] `.venv/bin/python -m compileall nvr.py src`
- [x] `.venv/bin/ruff check .`

### Phase 5: OpenCV Dependency and Sample Stages

Status: complete

Purpose: Prove the pipeline can transform images with OpenCV.

Tasks:

- [x] Choose and add the OpenCV package dependency.
- [x] Add a simple clip/crop stage.
- [x] Add a simple resize or grayscale stage.
- [x] Add a metadata annotation stage for testing metadata flow.
- [x] Add tests using generated images.
- [x] Confirm disabled sample stages are skipped.
- [x] Confirm a sample preprocessing pipeline can fan out into object detection and thumbnail pipelines.
- [x] Confirm a sample post-processing pipeline can receive outputs from two upstream pipelines.

Implementation notes:

- Added `opencv-python-headless` to `requirements.txt` and installed it in the local virtual environment for validation.
- Added sample stage modules under `src/nvr_common/pipeline/sample_stages`: `CropStage`, `ResizeStage`, and `MetadataAnnotationStage`.
- `CropStage` crops NumPy/OpenCV image arrays using configured `x`, `y`, `width`, and `height`, clipping to image bounds and emitting crop metadata.
- `ResizeStage` resizes images with OpenCV and can preserve aspect ratio when only width is configured.
- `MetadataAnnotationStage` adds configured metadata and can record current image shape and upstream input ids for debugging and tests.
- Updated the disabled sample stage module paths in `config.yaml` to point at the new sample stage modules.
- Added generated-image tests for crop, resize, disabled-stage skipping, fan-out into object detection and thumbnail branches, and fan-in into a post-processing pipeline.

Milestone test:

- [x] Run sample-stage tests.
- [x] Run compileall and Ruff.

Validation results:

- [x] `PYTHONPATH=src .venv/bin/python -m unittest tests.test_sample_pipeline_stages`
- [x] `PYTHONPATH=src .venv/bin/python -m unittest discover`
- [x] `.venv/bin/python -m compileall nvr.py src`
- [x] `.venv/bin/ruff check .`

### Phase 6: Camera Integration Prototype

Status: complete

Purpose: Connect the pipeline to camera input at a controlled sampling rate while preserving recording behavior.

Tasks:

- [x] Implement frame acquisition based on the Phase 2 decision.
- [x] Add per-camera graph runner lifecycle management.
- [x] Ensure pipeline failures are logged and isolated from recording failures.
- [x] Add sampling controls such as every N seconds or every N frames.
- [x] Add structured logs that do not expose RTSP credentials.
- [x] Test with local image or video fixtures instead of real cameras where possible.

Implementation notes:

- Added `CameraPipelineWorker` under `src/nvr_background/pipeline`, using a separate OpenCV frame source and `PipelineGraphRunner`.
- Added `OpenCvFrameSource` for RTSP/video capture and `ImageFileFrameSource` for fixture-driven tests.
- `src/nvr_background/main.py` now starts pipeline workers alongside enabled recorders when a per-camera effective pipeline graph is enabled.
- Pipeline worker errors are logged and isolated from recorder threads; the worker samples according to `pipeline_graph.frame_interval_seconds`.

Milestone test:

- [x] Run integration-style tests with fixture input.
- [x] Run compileall and Ruff.
- [ ] Manual live-camera run only if explicitly requested.

### Phase 7: Detection and Tracking Foundation

Status: complete

Purpose: Add enough AI/object-processing structure to detect people and reason about movement direction.

Tasks:

- [x] Choose initial person detection strategy.
- [x] Support model path or detector configuration.
- [x] Add metadata schema for detections: class, confidence, bounding box, timestamp, and track id if available.
- [x] Add movement tracking metadata across frames.
- [x] Add approach-direction detection as a separate stage.
- [x] Add tests for approach logic using synthetic detection sequences.

Implementation notes:

- Initial detection strategy is synthetic/configured detections through `SyntheticPersonDetectorStage`; real model inference remains a later Phase 12+ enhancement.
- Added `MovementTrackerStage` with stateful per-track center movement, enabled by stage-instance caching in `PipelineGraphRunner`.
- Added `ApproachDirectionStage` to emit an event when tracked movement crosses a configured direction and minimum delta.

Milestone test:

- [x] Run detection/tracking unit tests.
- [x] Run compileall and Ruff.

### Phase 8: MQTT Event Output

Status: complete

Purpose: Emit controlled MQTT messages when pipeline metadata indicates an actionable event.

Tasks:

- [x] Add MQTT dependency if needed.
- [x] Add MQTT config with host, port, auth, TLS, topic, and payload options.
- [x] Ensure credentials are not logged.
- [x] Implement an MQTT event stage.
- [x] Add rate limiting or cooldown to avoid repeated light-on messages.
- [x] Add tests using a fake MQTT client.

Implementation notes:

- Added `paho-mqtt` to `requirements.txt`.
- Added `MqttEventStage` with host, port, username, password, TLS, topic, payload, event key, and cooldown options.
- Tests use an injected fake MQTT client factory so no broker or credentials are required.

Milestone test:

- [x] Run MQTT stage tests.
- [x] Run compileall and Ruff.
- [ ] Optional manual test against a local broker only when explicitly requested.

### Phase 9: Debug Backend

Status: complete

Purpose: Make pipeline execution inspectable and controllable before building the web UI.

Tasks:

- [x] Add debug session state for each camera, graph run, pipeline run, and stage run.
- [x] Support breakpoints by pipeline id and stage id.
- [x] Support run, pause, step, and step over one stage.
- [x] Support step over one named pipeline.
- [x] Show fan-out branches and fan-in waits in debug state.
- [x] Store current stage input image, output image, metadata before, and metadata after.
- [x] Add APIs or service methods that the future web UI can call.
- [x] Ensure debug mode has bounded memory use.
- [x] Add tests for stepping and breakpoint behavior.

Implementation notes:

- Added `PipelineDebugSession` and `StageDebugRecord` under `src/nvr_common/pipeline/debug`.
- Debug sessions keep bounded stage records, breakpoint state, cursor status, metadata before/after, and image shape summaries.
- Debug execution supports run, pause state, step, step over stage, and step over pipeline service methods.

Milestone test:

- [x] Run debug backend tests.
- [x] Run compileall and Ruff.

### Phase 10: Web UI API Boundary

Status: complete

Purpose: Define and implement backend HTTP/WebSocket endpoints for the future Vue debugger.

Tasks:

- [x] Choose backend serving approach compatible with the current service.
- [x] Add endpoint to list cameras and pipeline stages.
- [x] Add endpoint to list the pipeline graph, named pipelines, stages, and edges.
- [x] Add endpoint to get debug session state.
- [x] Add endpoint to set or clear breakpoints.
- [x] Add endpoint to command run, pause, step, and step over.
- [x] Add endpoint or stream for input/output image previews.
- [x] Add endpoint to inspect metadata.
- [x] Add tests for API behavior.

Implementation notes:

- Added a standard-library HTTP server under `src/nvr_web`, runnable with `PYTHONPATH=src .venv/bin/python -m nvr_web`.
- Added JSON endpoints: `/api/cameras`, `/api/pipeline-graph`, `/api/debug/state`, `/api/debug/breakpoints`, `/api/debug/command`, `/api/debug/preview`, and `/api/debug/metadata`.
- API tests exercise the request handler with in-memory streams because the sandbox blocks local socket creation.

Milestone test:

- [x] Run API tests.
- [x] Run compileall and Ruff.
- [x] Manual UI testing deferred until frontend screens are implemented.

### Phase 11: Vue Debugger Subproject

Status: complete

Note: The user manually created the Vue 3 TypeScript Vite subproject at `src/nvr_ui`.

Purpose: Build the visual debugger once the backend API exists and the frontend project has been created.

Tasks:

- [x] Wait for user confirmation that the Vue subproject has been created.
- [x] Read the generated frontend structure and package scripts.
- [x] Build a debugger view with camera selection, stage list, breakpoints, controls, image previews, and metadata panel.
- [x] Use Vue 3 Composition API and strict TypeScript.
- [x] Avoid spin controls for floating-point entry; use validated text inputs.
- [x] Avoid gradient styling unless explicitly requested.
- [x] Add frontend tests or type checks based on the generated project setup.

Implementation notes:

- Replaced the generated Vue starter screen with a debugger workspace in `src/nvr_ui/src/App.vue`.
- The UI loads cameras and graph data, runs debug commands, sets or clears breakpoints, shows pipeline/stage cards, shows latest input/output shape summaries, and displays metadata JSON.
- Styling is a restrained operational UI with no gradients and no numeric spin inputs.

Milestone test:

- [x] Run frontend type check.
- [x] Run frontend tests if configured.
- [x] Start the frontend dev server and provide the local URL when requested or useful.

Validation results for Phases 6-11:

- [x] `PYTHONPATH=src .venv/bin/python -m unittest tests.test_camera_pipeline_worker`
- [x] `PYTHONPATH=src .venv/bin/python -m unittest tests.test_detection_tracking_mqtt`
- [x] `PYTHONPATH=src .venv/bin/python -m unittest tests.test_debug_api`
- [x] `PYTHONPATH=src .venv/bin/python -m unittest discover`
- [x] `.venv/bin/python -m compileall nvr.py src`
- [x] `.venv/bin/ruff check .`
- [x] `npm run type-check` from `src/nvr_ui`
- [x] Started backend API at `http://127.0.0.1:8080/`
- [x] Started Vite debugger UI at `http://127.0.0.1:5173/`

### Phase 12: End-to-End Scenario

Status: pending

Purpose: Validate the original scenario from frame input through person-approaching detection to MQTT output and debugger visibility.

Tasks:

- [ ] Configure a test camera or fixture video.
- [ ] Configure preprocessing, person detection, approach detection, post-processing, thumbnail, and MQTT pipelines.
- [ ] Confirm metadata passes through all required stages.
- [ ] Confirm fan-out and fan-in behavior works for the end-to-end graph.
- [ ] Confirm MQTT message fires only for the intended approach condition.
- [ ] Confirm debugger shows input and output images for selected stages.
- [ ] Confirm recording behavior still works independently.

Milestone test:

- [ ] Run full automated test suite.
- [ ] Run compileall and Ruff.
- [ ] Manual live test only when explicitly requested and credentials are available locally.

## Session Handoff Template

Use this section at the end of each implementation session.

Last updated: 2026-04-25

Completed this session:

- Completed Phases 6 through 11.
- Added separate OpenCV frame acquisition and `CameraPipelineWorker` lifecycle alongside recorder threads.
- Added synthetic detection, movement tracking, approach-direction event, and MQTT event sample stages.
- Added bounded pipeline debug session state with breakpoints, run, pause, step, step-over-stage, and step-over-pipeline behavior.
- Added standard-library `nvr_web` debug API endpoints and static UI serving.
- Replaced the generated Vue starter page with a strict TypeScript debugger workspace.
- Added Python tests for fixture frame acquisition, detection/tracking, MQTT fake-client publishing, debug stepping, and API behavior.
- Updated VS Code F5 debug configuration so `Debug NVR Web App` starts the Python web API, starts the Vite UI task, and opens the browser at `http://127.0.0.1:5173/`.
- Enabled the default checked-in sample `pipeline_graph` and sample crop/thumbnail stages so the debugger starts with runnable pipeline stages.

Current blockers:

- Real person detection remains synthetic/configured until a model strategy is selected.
- Live RTSP pipeline acquisition has not been manually tested against real cameras.
- Debug image previews currently expose shape/metadata placeholders; encoded preview image streaming remains a future improvement.

Next recommended task:

- Start Phase 12 end-to-end scenario wiring with a fixture video or test camera config, then decide the real person detection model strategy.

Validation last run:

- `PYTHONPATH=src .venv/bin/python -m unittest discover`
- `.venv/bin/python -m compileall nvr.py src`
- `.venv/bin/ruff check .`
- `npm run type-check` from `src/nvr_ui`
- `.venv/bin/python -m json.tool .vscode/launch.json`
- `.venv/bin/python -m json.tool .vscode/tasks.json`
