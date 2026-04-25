# NVR Pipeline Graph Architecture

## Purpose

The image processing system should be built around named pipelines that can be connected together into a graph. Each named pipeline owns a focused set of processing stages, and its output can feed one or more downstream pipelines.

This allows reusable function groups such as preprocessing, object detection, thumbnail creation, post processing, event generation, and debug visualization to be combined per camera without duplicating stage definitions.

## Repository Layout Direction

Before implementing the pipeline graph, restructure the codebase into a `src` layout that separates background processes from web/API code.

The target separation is:

- background process package: service startup, recorder lifecycle, retention management, frame acquisition, and graph runner lifecycle
- common package: configuration, logging, RTSP sanitizing, shared models, and pipeline graph primitives that are used by both background and web/API code
- web/API package: future debug API, debug session endpoints, image preview endpoints, and web server integration

The exact package names should be decided during the first implementation phase. Acceptable directions include either separate packages such as `nvr_background`, `nvr_common`, and `nvr_web`, or one package such as `nvr` with `background`, `common`, and `web` subpackages.

Keep the root entry point thin after the move. It should only delegate to the background service entry point or be replaced by a documented module entry point.

## Core Model

### Pipeline Graph

A pipeline graph is a directed acyclic graph of named pipelines.

Each graph has:

- one or more input pipelines that receive camera frames or extracted images
- named pipeline nodes
- directed connections between pipeline nodes
- optional fan-out, where one pipeline output feeds multiple downstream pipelines
- optional fan-in, where one pipeline receives inputs from multiple upstream pipelines

Cycles should be rejected during configuration validation. Feedback loops can be considered later, but they require explicit buffering, scheduling, and termination rules.

### Named Pipeline

A named pipeline is an ordered chain of stages with a clear functional purpose.

Examples:

- `preprocessing`
- `object_detection`
- `thumbnail`
- `post_processing`
- `approach_detection`
- `mqtt_events`

Each pipeline:

- has a stable id
- can be enabled or disabled
- contains zero or more configured stages
- receives one or more pipeline inputs
- produces one pipeline output
- can pass its output to one or more downstream pipelines

### Stage

A stage is a pluggable Python processing module inside a named pipeline.

Each stage:

- has a stable id within its parent pipeline
- can be enabled or disabled
- receives the pipeline input image set, original image, current image, and metadata
- returns an updated current image and metadata
- may add debug artifacts
- may emit controlled side effects through services such as MQTT

Disabled stages remain visible in configuration and debugging, but execution skips them.

## Data Model

### Original Image

The original image is preserved for the full graph execution. Every pipeline and every stage can access it. Stages must not replace or mutate the original image in place.

### Pipeline Input

A pipeline input includes:

- original image
- current image for that input branch
- metadata dictionary for that branch
- source pipeline id, when produced by another pipeline
- camera id and frame timestamp

For source pipelines, the current image starts as the original image.

### Pipeline Output

A pipeline output includes:

- pipeline id
- output image
- metadata dictionary
- optional debug artifacts
- timing and status information

Downstream pipelines receive upstream pipeline outputs as their inputs.

### Fan-Out

Fan-out means a single pipeline output is passed to multiple downstream pipelines.

Example:

```text
preprocessing
  -> object_detection
  -> thumbnail
```

The downstream pipelines should receive independent input objects so that one branch cannot accidentally mutate another branch's metadata or image reference. Image arrays may share memory internally only when the implementation can guarantee stages will not mutate shared data unexpectedly.

### Fan-In

Fan-in means a pipeline receives outputs from two or more upstream pipelines and processes them as a set.

Example:

```text
preprocessing -> object_detection -> post_processing
preprocessing -> thumbnail        -> post_processing
```

The fan-in pipeline receives both `object_detection` and `thumbnail` outputs. Its stages can inspect each upstream image and metadata set, then produce a single combined output.

Fan-in requires scheduling rules:

- A fan-in pipeline should run when all required upstream inputs for the same source frame are available.
- Inputs should be correlated by camera id and frame id or timestamp.
- Missing or failed upstream inputs should follow configured behavior: skip, wait until timeout, or run with partial inputs.

## Example Graph

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

Alternative with fan-in:

```text
camera_frame
  -> preprocessing
       -> object_detection
            -> post_processing
       -> thumbnail
            -> post_processing
```

In the second example, `post_processing` runs after both `object_detection` and `thumbnail` outputs are available for the same frame.

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

## Debugging Model

The debugger should expose both graph-level and stage-level state.

Graph-level debugging:

- show named pipelines and edges
- show pending, running, completed, skipped, and failed pipeline nodes
- allow breakpoints on pipeline ids
- show fan-out branches and fan-in waits

Stage-level debugging:

- show stages inside the selected pipeline
- allow breakpoints on stage ids
- support step through a stage
- support step over one whole pipeline
- display input image, output image, metadata before, and metadata after

For fan-in pipelines, the UI should display the set of upstream inputs together.

## Implementation Notes

- Start with a directed acyclic graph executor.
- Validate unknown pipeline ids, duplicate ids, disabled references, and cycles before runtime.
- Keep branch metadata isolated unless a stage explicitly combines metadata.
- Treat side-effect stages as normal stages, but inject services such as MQTT rather than letting stages create uncontrolled global clients.
- Preserve compatibility with a simple linear pipeline by representing it as a graph where each pipeline has one downstream pipeline.
