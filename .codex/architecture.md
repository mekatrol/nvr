# NVR Pipeline Graph Architecture

## Goal

- Build image processing as a DAG of named pipelines.
- Let pipeline output feed one or many downstream pipelines.
- Reuse groups: preprocessing, detection, thumbnail, post-processing, events, debug.
- Avoid duplicated stage config.

## Layout

- Use `src` layout.
- Keep root entry thin.
- Keep backend and SPA separate.

Packages:

- `src/nvr_background`: service startup, recorder lifecycle, retention, frame acquisition, graph runner.
- `src/nvr_common`: config, logging, RTSP sanitizing, shared models, graph primitives.
- `src/nvr_web`: debug API, debug sessions, image preview, web server.
- `src/nvr_ui`: Vue 3 TypeScript Vite debugger SPA. Not Python.

Ownership:

- Backend owns HTTP/WebSocket APIs and static serving.
- SPA owns browser routes, debugger screens, client state, API calls.

## Graph

- Directed acyclic graph.
- Validate cycles before runtime.
- Consider feedback loops later only with explicit buffering, scheduling, termination.

Graph has:

- input pipelines for camera frames or extracted images
- named pipeline nodes
- directed edges
- fan-out
- fan-in

## Pipeline

- Ordered chain of stages.
- Stable `id`.
- `enabled`.
- Zero or more stages.
- One or more inputs.
- One output.
- May feed multiple downstream pipelines.

Example ids:

- `preprocessing`
- `object_detection`
- `thumbnail`
- `post_processing`
- `approach_detection`
- `mqtt_events`

## Stage

- Python plugin inside one pipeline.
- Stable `id` inside parent pipeline.
- `enabled`.
- Input: all pipeline inputs, original image, current image, metadata.
- Output: current image, metadata.
- May add debug artifacts.
- May emit side effects through injected services, such as MQTT.
- Disabled stage stays visible but does not run.

## Data

Original image:

- Preserve for full graph run.
- Never replace or mutate in place.

Pipeline input:

- original image
- current branch image
- branch metadata
- source pipeline id
- camera id
- frame id or timestamp

Pipeline output:

- pipeline id
- output image
- metadata
- debug artifacts
- timing
- status

## Fan-Out

Example:

```text
preprocessing
  -> object_detection
  -> thumbnail
```

Rules:

- Give each branch independent input objects.
- Keep branch metadata isolated.
- Share image memory only when mutation safety is guaranteed.

## Fan-In

Example:

```text
preprocessing -> object_detection -> post_processing
preprocessing -> thumbnail        -> post_processing
```

Rules:

- Run when all required upstream inputs for same source frame exist.
- Correlate by camera id and frame id or timestamp.
- Missing or failed input behavior must be configured: skip, wait with timeout, or run partial.

## Example

```text
camera_frame
  -> preprocessing
       -> object_detection
            -> post_processing
                 -> approach_detection
                      -> mqtt_events
       -> thumbnail
            -> debug_preview
```

Fan-in variant:

```text
camera_frame
  -> preprocessing
       -> object_detection
            -> post_processing
       -> thumbnail
            -> post_processing
```

`post_processing` waits for both upstream outputs for the same frame.

## Config Shape

Expected YAML, refine as needed:

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
        - id: mqtt-person-approaching
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

## Debugger

Graph view:

- show pipelines and edges
- show pending, running, complete, skipped, failed
- breakpoints on pipeline ids
- show fan-out branches
- show fan-in waits

Stage view:

- show selected pipeline stages
- breakpoints on stage ids
- step through stage
- step over pipeline
- show input image, output image, metadata before, metadata after
- for fan-in, show upstream input set together

## Implementation

- Start with DAG executor.
- Validate unknown ids, duplicate ids, disabled refs, cycles.
- Keep branch metadata isolated unless stage combines it.
- Inject side-effect services. Do not let stages create globals.
- Represent simple linear pipeline as graph with one downstream edge per pipeline.
