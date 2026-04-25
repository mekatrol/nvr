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
  - `.venv/bin/python -m compileall nvr.py utils log recorder`
  - `.venv/bin/ruff check .`
- After the `src` restructure is complete, update `.codex/environment.md`, this plan, and validation commands to use the new paths.
- Preserve RTSP credential redaction in all logging paths.
- Do not commit or write real camera credentials, MQTT credentials, generated recordings, or generated debug captures.
- When frontend work begins, the Vue app will be created manually by the user with `npm create vue@latest`. Do not scaffold it before the user confirms that step is done.

## Current Status

Status: planning

No pipeline implementation has started yet.

## Key Design Decisions

- Decision: Restructure the codebase into a `src` layout before adding pipeline features.
  Status: proposed
  Notes: Separate long-running background service code from web/API code so the pipeline executor, debug backend, and future Vue UI have clear ownership boundaries.

- Decision: Use OpenCV as the likely image processing foundation.
  Status: proposed
  Notes: Confirm exact package name and dependency strategy before implementation, likely `opencv-python-headless` for service use unless UI/local display requirements force otherwise.

- Decision: Pipeline modules are normal Python modules loaded through configuration.
  Status: proposed
  Notes: Define a small plugin contract before writing sample modules.

- Decision: The processing system is a graph of named pipelines, not only one linear pipeline.
  Status: proposed
  Notes: A named pipeline contains an ordered chain of stages. Pipeline outputs can fan out to multiple downstream pipelines and fan in from multiple upstream pipelines. See `.codex/architecture.md`.

- Decision: Each stage receives the original image, the current image, and mutable metadata.
  Status: proposed
  Notes: The original image must remain available to every stage in every named pipeline and must not be overwritten by downstream transformations.

- Decision: Disabled stages stay configured but are skipped at runtime.
  Status: proposed
  Notes: This allows users to turn modules on and off without deleting configuration.

- Decision: Debugging should support step, run, breakpoint, step over a single module stage, and step over a whole named pipeline.
  Status: proposed
  Notes: Implement backend debug control for both graph-level and stage-level execution before building the Vue UI.

## Open Questions

- What exact package names should be used under `src`: for example `src/nvr_background`, `src/nvr_web`, and `src/nvr_common`, or a single `src/nvr` package with `background`, `web`, and `common` subpackages?
- Should the root `nvr.py` remain as a compatibility launcher, or should the main command move to a module entry point such as `.venv/bin/python -m nvr.background`?
- Should the pipeline run on live frames, completed MP4 segments, snapshots extracted from `ffmpeg`, or a separate camera frame reader?
- What frame rate should the pipeline process for detection: every frame, every Nth frame, or time-based sampling?
- Should processed images be persisted for debugging, kept in memory, or both?
- Which MQTT broker settings and topic format should be supported?
- Should plugin configuration be global, per camera, or both?
- Should AI detection use a bundled model, a user-provided model path, or an external service?
- Should fan-in pipelines require all upstream outputs, allow partial input, or support both by configuration?
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

Status: pending

Purpose: Move the current Python code into a `src` layout and create clear boundaries between background processes, common/shared code, and future web/API code before adding the pipeline graph.

Target direction:

- Background process code: recorder lifecycle, retention, service startup, signal handling, and camera processing.
- Common code: configuration, logging, RTSP sanitizing, shared models, and later pipeline graph primitives.
- Web/API code: future debug API and web server integration.
- Root scripts: keep only thin compatibility launchers or project entry points.

Tasks:

- [ ] Read current imports and entry points in `nvr.py`, `utils`, `log`, and `recorder`.
- [ ] Choose the concrete `src` package layout.
- [ ] Move current background service modules under `src`.
- [ ] Separate shared modules from background-only modules.
- [ ] Reserve a web/API package path for later debug API work without implementing the API yet.
- [ ] Update imports after the move.
- [ ] Update `pyproject.toml` if needed so Ruff and tests understand the new source layout.
- [ ] Update validation commands in `.codex/environment.md`, `AGENTS.md` if appropriate, and this plan.
- [ ] Keep `nvr.py` as a thin launcher or replace it with a documented module entry point.
- [ ] Add or update smoke tests for importability if a test framework exists.
- [ ] Update this file with the final chosen layout.

Milestone test:

- [ ] Run the updated compileall command for the new `src` paths.
- [ ] Run `.venv/bin/ruff check .`.
- [ ] Do not run the service unless explicitly requested.

### Phase 2: Discovery and Shape

Status: pending

Purpose: Understand the current recorder lifecycle and choose where the pipeline should attach without disrupting recording.

Tasks:

- [ ] Read the restructured service entry point, config module, camera recorder, and retention manager.
- [ ] Identify where camera frames or snapshots can be obtained safely.
- [ ] Decide whether initial pipeline input comes from live frames, snapshots, or recorded segments.
- [ ] Decide whether pipeline configuration is global, per camera, or both.
- [ ] Decide whether the first implementation supports only acyclic graphs or reserves support for explicit feedback loops later.
- [ ] Decide the initial fan-in behavior: require all upstream inputs, allow partial input, or configure per pipeline.
- [ ] Document the chosen integration point in this file.

Milestone test:

- [ ] No code required unless needed for discovery.
- [ ] If code changes are made, run compileall and Ruff.

### Phase 3: Core Pipeline Interfaces

Status: pending

Purpose: Add the backend abstractions for graph-based image and metadata flow without connecting to live cameras yet.

Tasks:

- [ ] Add a pipeline package with one top-level class per file.
- [ ] Define named pipeline, graph, edge, input, context, output, and result data structures.
- [ ] Define the plugin stage contract.
- [ ] Implement stage loading from Python module and class names.
- [ ] Implement enabled/disabled stage skipping.
- [ ] Implement graph validation for duplicate pipeline ids, unknown edge references, and cycles.
- [ ] Implement fan-out from one pipeline output to multiple downstream pipelines.
- [ ] Implement basic fan-in where one pipeline receives outputs from multiple upstream pipelines for the same frame.
- [ ] Ensure original image and current branch image are both available to every stage.
- [ ] Ensure branch metadata is isolated unless a stage explicitly combines upstream metadata.
- [ ] Add focused unit tests using synthetic images.

Milestone test:

- [ ] Run unit tests for the pipeline package.
- [ ] Run the updated compileall command for the `src` layout.
- [ ] Run `.venv/bin/ruff check .`.

### Phase 4: Configuration Support

Status: pending

Purpose: Extend config loading and validation for pipeline settings.

Tasks:

- [ ] Add pipeline config parsing.
- [ ] Support global defaults and per-camera overrides if selected in Phase 2.
- [ ] Validate required pipeline fields: `id`, `enabled`, and `stages`.
- [ ] Validate required edge fields: `from` and `to`.
- [ ] Validate required stage fields: `id`, `enabled`, `module`, and class or factory reference.
- [ ] Validate stage config remains a dictionary.
- [ ] Validate fan-in input requirements for pipelines with multiple upstream edges.
- [ ] Add example disabled stages to `config.yaml` without real credentials.
- [ ] Add tests for config merge behavior, including `config.debug.yaml` overlays.

Milestone test:

- [ ] Run config tests.
- [ ] Run compileall and Ruff.

### Phase 5: OpenCV Dependency and Sample Stages

Status: pending

Purpose: Prove the pipeline can transform images with OpenCV.

Tasks:

- [ ] Choose and add the OpenCV package dependency.
- [ ] Add a simple clip/crop stage.
- [ ] Add a simple resize or grayscale stage.
- [ ] Add a metadata annotation stage for testing metadata flow.
- [ ] Add tests using generated images.
- [ ] Confirm disabled sample stages are skipped.
- [ ] Confirm a sample preprocessing pipeline can fan out into object detection and thumbnail pipelines.
- [ ] Confirm a sample post-processing pipeline can receive outputs from two upstream pipelines.

Milestone test:

- [ ] Run sample-stage tests.
- [ ] Run compileall and Ruff.

### Phase 6: Camera Integration Prototype

Status: pending

Purpose: Connect the pipeline to camera input at a controlled sampling rate while preserving recording behavior.

Tasks:

- [ ] Implement frame acquisition based on the Phase 2 decision.
- [ ] Add per-camera graph runner lifecycle management.
- [ ] Ensure pipeline failures are logged and isolated from recording failures.
- [ ] Add sampling controls such as every N seconds or every N frames.
- [ ] Add structured logs that do not expose RTSP credentials.
- [ ] Test with local image or video fixtures instead of real cameras where possible.

Milestone test:

- [ ] Run integration-style tests with fixture input.
- [ ] Run compileall and Ruff.
- [ ] Manual live-camera run only if explicitly requested.

### Phase 7: Detection and Tracking Foundation

Status: pending

Purpose: Add enough AI/object-processing structure to detect people and reason about movement direction.

Tasks:

- [ ] Choose initial person detection strategy.
- [ ] Support model path or detector configuration.
- [ ] Add metadata schema for detections: class, confidence, bounding box, timestamp, and track id if available.
- [ ] Add movement tracking metadata across frames.
- [ ] Add approach-direction detection as a separate stage.
- [ ] Add tests for approach logic using synthetic detection sequences.

Milestone test:

- [ ] Run detection/tracking unit tests.
- [ ] Run compileall and Ruff.

### Phase 8: MQTT Event Output

Status: pending

Purpose: Emit controlled MQTT messages when pipeline metadata indicates an actionable event.

Tasks:

- [ ] Add MQTT dependency if needed.
- [ ] Add MQTT config with host, port, auth, TLS, topic, and payload options.
- [ ] Ensure credentials are not logged.
- [ ] Implement an MQTT event stage.
- [ ] Add rate limiting or cooldown to avoid repeated light-on messages.
- [ ] Add tests using a fake MQTT client.

Milestone test:

- [ ] Run MQTT stage tests.
- [ ] Run compileall and Ruff.
- [ ] Optional manual test against a local broker only when explicitly requested.

### Phase 9: Debug Backend

Status: pending

Purpose: Make pipeline execution inspectable and controllable before building the web UI.

Tasks:

- [ ] Add debug session state for each camera, graph run, pipeline run, and stage run.
- [ ] Support breakpoints by pipeline id and stage id.
- [ ] Support run, pause, step, and step over one stage.
- [ ] Support step over one named pipeline.
- [ ] Show fan-out branches and fan-in waits in debug state.
- [ ] Store current stage input image, output image, metadata before, and metadata after.
- [ ] Add APIs or service methods that the future web UI can call.
- [ ] Ensure debug mode has bounded memory use.
- [ ] Add tests for stepping and breakpoint behavior.

Milestone test:

- [ ] Run debug backend tests.
- [ ] Run compileall and Ruff.

### Phase 10: Web UI API Boundary

Status: pending

Purpose: Define and implement backend HTTP/WebSocket endpoints for the future Vue debugger.

Tasks:

- [ ] Choose backend serving approach compatible with the current service.
- [ ] Add endpoint to list cameras and pipeline stages.
- [ ] Add endpoint to list the pipeline graph, named pipelines, stages, and edges.
- [ ] Add endpoint to get debug session state.
- [ ] Add endpoint to set or clear breakpoints.
- [ ] Add endpoint to command run, pause, step, and step over.
- [ ] Add endpoint or stream for input/output image previews.
- [ ] Add endpoint to inspect metadata.
- [ ] Add tests for API behavior.

Milestone test:

- [ ] Run API tests.
- [ ] Run compileall and Ruff.
- [ ] Manual UI testing deferred until frontend exists.

### Phase 11: Vue Debugger Subproject

Status: blocked

Blocker: The user will manually create the Vue 3 Composition API, strict TypeScript, Vite subproject with `npm create vue@latest`.

Purpose: Build the visual debugger once the backend API exists and the frontend project has been created.

Tasks:

- [ ] Wait for user confirmation that the Vue subproject has been created.
- [ ] Read the generated frontend structure and package scripts.
- [ ] Build a debugger view with camera selection, stage list, breakpoints, controls, image previews, and metadata panel.
- [ ] Use Vue 3 Composition API and strict TypeScript.
- [ ] Avoid spin controls for floating-point entry; use validated text inputs.
- [ ] Avoid gradient styling unless explicitly requested.
- [ ] Add frontend tests or type checks based on the generated project setup.

Milestone test:

- [ ] Run frontend type check.
- [ ] Run frontend tests if configured.
- [ ] Start the frontend dev server and provide the local URL when requested or useful.

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

- Created this phased plan.
- Added graph-based named pipeline architecture to the plan.
- Added `.codex/architecture.md`.
- Added Phase 1 for restructuring the codebase into a `src` layout before pipeline work.
- Updated `.codex/architecture.md` with background/common/web layout direction.

Current blockers:

- Need Phase 1 `src` restructure before pipeline implementation.
- Need Phase 2 discovery before implementation choices are finalized.
- Vue frontend is blocked until the user manually creates the subproject.

Next recommended task:

- Start Phase 1 by restructuring the codebase into `src` and separating background, common, and future web/API code.

Validation last run:

- Not run. This session only added planning documentation.
