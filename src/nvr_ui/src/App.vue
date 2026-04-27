<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

type Camera = {
  id: string
  name: string
  enabled: boolean
  pipeline_enabled: boolean
}

type Stage = {
  id: string
  enabled: boolean
  module?: string
  class_name?: string
  filename?: string | null
  pipeline?: string | null
  config: Record<string, unknown>
}

type Pipeline = {
  id: string
  name?: string
  enabled: boolean
  required_inputs: string[]
  stages: Stage[]
}

type Edge = {
  from: string
  to: string
}

type DebugRecord = {
  pipeline_id: string
  stage_id: string
  status: string
  input_shape: number[] | null
  output_shape: number[] | null
  input_preview: string | null
  output_preview: string | null
  metadata_before: Record<string, unknown>
  metadata_after: Record<string, unknown>
}

type DebugState = {
  status: string
  cursor?: number
  total_steps?: number
  records?: DebugRecord[]
}

type PipelinesResponse = {
  enabled: boolean
  frame_interval_seconds: number | string | null
  pipelines: Pipeline[]
  edges: Edge[]
}

const iconPaths = {
  pipeline: 'M3 5.5A2.5 2.5 0 0 1 5.5 3H9l2 2h7.5A2.5 2.5 0 0 1 21 7.5v9A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z',
  stage: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5',
  file: 'M6 3h8l4 4v14H6zM14 3v5h5',
  link: 'M10 13a5 5 0 0 0 7.5.5l2-2A5 5 0 0 0 12.5 4l-1 1M14 11a5 5 0 0 0-7.5-.5l-2 2A5 5 0 0 0 11.5 20l1-1',
  plus: 'M12 5v14M5 12h14',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3',
} as const

const cameras = ref<Camera[]>([])
const selectedCameraId = ref('')
const pipelines = ref<Pipeline[]>([])
const edges = ref<Edge[]>([])
const debugState = ref<DebugState>({ status: 'idle', records: [] })
const metadata = ref<Record<string, unknown>>({})
const selectedBreakpoint = ref('')
const apiError = ref('')
const isLoadingCameras = ref(false)
const draftEnabled = ref(true)
const draftFrameIntervalSeconds = ref('1.0')
const draftPipelines = ref<Pipeline[]>([])
const draftEdges = ref<Edge[]>([])
const currentView = ref<'index' | 'debug'>('index')
const debugPipelineId = ref('')
const selectedPipelineId = ref('')
const selectedStageId = ref('')
const selectedPipelineIdEdit = ref('')
const selectedPipelineNameEdit = ref('')
const selectedStageIdEdit = ref('')
const selectedStageModule = ref('')
const selectedStageClassName = ref('')
const selectedStageFilename = ref('')
const selectedStagePipeline = ref('')
const selectedStageConfigJson = ref('{}')
const selectedPipelineRequiredInputs = ref('')
const deployStatus = ref('')

const selectedCamera = computed(() =>
  cameras.value.find((camera) => camera.id === selectedCameraId.value),
)

const latestRecord = computed(() => debugState.value.records?.at(-1))

const visiblePipelines = computed(() => {
  if (!debugPipelineId.value) return pipelines.value
  return pipelines.value.filter((pipeline) => pipeline.id === debugPipelineId.value)
})

const selectedDraftPipeline = computed(() =>
  draftPipelines.value.find((pipeline) => pipeline.id === selectedPipelineId.value),
)

const selectedDraftStage = computed(() =>
  selectedDraftPipeline.value?.stages.find((stage) => stage.id === selectedStageId.value),
)

async function loadCameras() {
  isLoadingCameras.value = true
  try {
    const payload = await getJson<{ cameras: Camera[] }>('/api/cameras')
    cameras.value = payload.cameras
    const firstCamera = cameras.value[0]
    if (!selectedCameraId.value && firstCamera) {
      selectedCameraId.value = firstCamera.id
    }
  } finally {
    isLoadingCameras.value = false
  }
}

async function loadPipelines() {
  if (!selectedCameraId.value) return
  const graph = await getJson<{ pipelines: Pipeline[]; edges: Edge[] }>(
    `/api/pipelines?camera_id=${encodeURIComponent(selectedCameraId.value)}`,
  )
  pipelines.value = graph.pipelines
  edges.value = graph.edges
}

async function loadDraftPipelines() {
  const graph = await getJson<PipelinesResponse>('/api/pipelines/draft')
  draftEnabled.value = graph.enabled
  draftFrameIntervalSeconds.value = String(graph.frame_interval_seconds ?? '1.0')
  draftPipelines.value = graph.pipelines
  draftEdges.value = graph.edges
  if (!selectedPipelineId.value && draftPipelines.value[0]) {
    selectPipeline(draftPipelines.value[0].id)
  } else {
    refreshSelectedEditors()
  }
}

async function loadDebugState() {
  if (!selectedCameraId.value) return
  debugState.value = await getJson<DebugState>(
    `/api/debug/state?camera_id=${encodeURIComponent(selectedCameraId.value)}`,
  )
  const payload = await getJson<{ metadata: Record<string, unknown> }>(
    `/api/debug/metadata?camera_id=${encodeURIComponent(selectedCameraId.value)}`,
  )
  metadata.value = payload.metadata
}

async function runCommand(command: string) {
  if (!selectedCameraId.value) return
  debugState.value = await postJson<DebugState>('/api/debug/command', {
    camera_id: selectedCameraId.value,
    command,
  })
  await loadDebugState()
}

async function toggleBreakpoint(enabled: boolean) {
  if (!selectedCameraId.value || !selectedBreakpoint.value) return
  const [pipelineId, stageId] = selectedBreakpoint.value.split(':')
  debugState.value = await postJson<DebugState>('/api/debug/breakpoints', {
    camera_id: selectedCameraId.value,
    pipeline_id: pipelineId,
    stage_id: stageId || null,
    enabled,
  })
}

async function refreshCamera() {
  try {
    showPipelineIndex()
    await loadPipelines()
    await loadDebugState()
    await loadDraftPipelines()
  } catch {
    return
  }
}

async function saveDraftPipelines() {
  deployStatus.value = ''
  const validationError = validateDraftPipelineReferences()
  if (validationError) {
    apiError.value = validationError
    return
  }
  const saved = await postJson<PipelinesResponse>('/api/pipelines/draft', toPipelinesPayload())
  draftPipelines.value = saved.pipelines
  draftEdges.value = saved.edges
  refreshSelectedEditors()
  deployStatus.value = 'Draft saved'
}

async function deployDraftPipelines() {
  await saveDraftPipelines()
  const deployed = await postJson<PipelinesResponse>('/api/pipelines/draft/deploy', {})
  pipelines.value = deployed.pipelines
  edges.value = deployed.edges
  await loadDebugState()
  deployStatus.value = 'Draft deployed and server config reloaded'
}

async function getJson<T>(path: string): Promise<T> {
  apiError.value = ''
  let response: Response
  try {
    response = await fetch(`${__API_BASE_URL__}${path}`)
  } catch (error) {
    apiError.value = `Unable to reach NVR web API at ${path}`
    throw error
  }
  if (!response.ok) {
    apiError.value = `${response.status} ${response.statusText}`
    throw new Error(apiError.value)
  }
  return response.json() as Promise<T>
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  apiError.value = ''
  let response: Response
  try {
    response = await fetch(`${__API_BASE_URL__}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (error) {
    apiError.value = `Unable to reach NVR web API at ${path}`
    throw error
  }
  if (!response.ok) {
    apiError.value = `${response.status} ${response.statusText}`
    throw new Error(apiError.value)
  }
  return response.json() as Promise<T>
}

function formatJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

function addPipeline() {
  const baseId = uniqueId('pipeline', draftPipelines.value.map((pipeline) => pipeline.id))
  draftPipelines.value.push({
    id: baseId,
    name: baseId,
    enabled: true,
    required_inputs: [],
    stages: [],
  })
  selectPipeline(baseId)
}

function addPipelineFromTree() {
  addPipeline()
  currentView.value = 'debug'
}

function deleteSelectedPipeline() {
  deletePipeline(selectedPipelineId.value)
}

function deletePipeline(pipelineId: string) {
  if (!pipelineId) return
  draftPipelines.value = draftPipelines.value.filter(
    (pipeline) => pipeline.id !== pipelineId,
  )
  draftEdges.value = draftEdges.value.filter(
    (edge) => edge.from !== pipelineId && edge.to !== pipelineId,
  )
  selectedPipelineId.value = draftPipelines.value[0]?.id ?? ''
  selectedStageId.value = ''
  if (debugPipelineId.value === pipelineId) {
    showPipelineIndex()
  }
  refreshSelectedEditors()
}

function addStage() {
  if (!selectedDraftPipeline.value) return
  const baseId = uniqueId(
    'stage',
    selectedDraftPipeline.value.stages.map((stage) => stage.id),
  )
  selectedDraftPipeline.value.stages.push({
    id: baseId,
    enabled: true,
    filename: 'nvr_common/pipeline/sample_stages/metadata_annotation_stage.py',
    class_name: 'MetadataAnnotationStage',
    config: { metadata: {} },
  })
  selectStage(baseId)
}

function addStageToPipeline(pipelineId: string) {
  selectPipeline(pipelineId)
  addStage()
  currentView.value = 'debug'
}

function deleteSelectedStage() {
  deleteStage(selectedPipelineId.value, selectedStageId.value)
}

function deleteStage(pipelineId: string, stageId: string) {
  const pipeline = draftPipelines.value.find((candidate) => candidate.id === pipelineId)
  if (!pipeline || !stageId) return
  pipeline.stages = pipeline.stages.filter((stage) => stage.id !== stageId)
  if (selectedPipelineId.value === pipelineId && selectedStageId.value === stageId) {
    selectedStageId.value = pipeline.stages[0]?.id ?? ''
  }
  refreshSelectedEditors()
}

function selectPipeline(pipelineId: string) {
  selectedPipelineId.value = pipelineId
  selectedStageId.value = selectedDraftPipeline.value?.stages[0]?.id ?? ''
  refreshSelectedEditors()
}

function selectStage(stageId: string) {
  selectedStageId.value = stageId
  refreshSelectedEditors()
}

function selectStageInPipeline(pipelineId: string, stageId: string) {
  selectedPipelineId.value = pipelineId
  selectedStageId.value = stageId
  refreshSelectedEditors()
}

function applyPipelineEdits() {
  const pipeline = selectedDraftPipeline.value
  if (!pipeline) return
  const nextId = selectedPipelineIdEdit.value.trim()
  if (!nextId) return
  const oldId = pipeline.id
  pipeline.id = nextId
  pipeline.name = selectedPipelineNameEdit.value.trim() || nextId
  pipeline.required_inputs = selectedPipelineRequiredInputs.value
    .split(',')
    .map((input) => input.trim())
    .filter((input) => input.length > 0)
  for (const edge of draftEdges.value) {
    if (edge.from === oldId) edge.from = nextId
    if (edge.to === oldId) edge.to = nextId
  }
  selectedPipelineId.value = nextId
}

function applyStageEdits() {
  const stage = selectedDraftStage.value
  if (!stage) return
  const nextId = selectedStageIdEdit.value.trim()
  if (!nextId) return
  try {
    stage.config = JSON.parse(selectedStageConfigJson.value) as Record<string, unknown>
  } catch {
    apiError.value = 'Stage config must be valid JSON'
    return
  }
  apiError.value = ''
  stage.id = nextId
  stage.module = selectedStageModule.value.trim() || undefined
  stage.class_name = selectedStageClassName.value.trim() || undefined
  stage.filename = selectedStageFilename.value.trim() || undefined
  stage.pipeline = selectedStagePipeline.value.trim() || undefined
  selectedStageId.value = nextId
}

function addEdge() {
  if (draftPipelines.value.length < 2) return
  const sourcePipeline = draftPipelines.value[0]
  const targetPipeline = draftPipelines.value[1]
  if (!sourcePipeline || !targetPipeline) return
  const from = sourcePipeline.id
  const to = targetPipeline.id
  draftEdges.value.push({ from, to })
}

function deleteEdge(index: number) {
  draftEdges.value.splice(index, 1)
}

function refreshSelectedEditors() {
  const pipeline = selectedDraftPipeline.value
  selectedPipelineIdEdit.value = pipeline?.id ?? ''
  selectedPipelineNameEdit.value = pipeline?.name ?? ''
  selectedPipelineRequiredInputs.value = pipeline?.required_inputs.join(', ') ?? ''
  const stage = selectedDraftStage.value
  selectedStageIdEdit.value = stage?.id ?? ''
  selectedStageModule.value = stage?.module ?? ''
  selectedStageClassName.value = stage?.class_name ?? ''
  selectedStageFilename.value = stage?.filename ?? ''
  selectedStagePipeline.value = stage?.pipeline ?? ''
  selectedStageConfigJson.value = formatJson(stage?.config ?? {})
}

function toPipelinesPayload() {
  const interval = Number(draftFrameIntervalSeconds.value)
  return {
    enabled: draftEnabled.value,
    frame_interval_seconds: Number.isFinite(interval) ? interval : draftFrameIntervalSeconds.value,
    pipelines: draftPipelines.value.map((pipeline) => ({
      id: pipeline.id,
      name: pipeline.name || pipeline.id,
      enabled: pipeline.enabled,
      inputs:
        pipeline.required_inputs.length > 0 ? { required: pipeline.required_inputs } : undefined,
      stages: pipeline.stages.map((stage) => ({
        id: stage.id,
        enabled: stage.enabled,
        ...(stage.pipeline ? { pipeline: stage.pipeline } : {}),
        ...(stage.filename ? { filename: stage.filename } : {}),
        ...(stage.module ? { module: stage.module } : {}),
        ...(stage.class_name ? { class: stage.class_name } : {}),
        config: stage.config,
      })),
    })),
    edges: draftEdges.value,
  }
}

function stageSummary(stage: Stage) {
  if (stage.pipeline) return `pipeline: ${stage.pipeline}`
  if (stage.filename) return stage.filename
  return stage.class_name || stage.module || 'stage'
}

function openPipelineDebug(pipelineId: string) {
  debugPipelineId.value = pipelineId
  selectedPipelineId.value = pipelineId
  currentView.value = 'debug'
  refreshSelectedEditors()
}

function openStageDebug(pipelineId: string, stageId: string) {
  debugPipelineId.value = pipelineId
  selectedPipelineId.value = pipelineId
  selectedStageId.value = stageId
  currentView.value = 'debug'
  refreshSelectedEditors()
}

function showPipelineIndex() {
  currentView.value = 'index'
  debugPipelineId.value = ''
}

function validateDraftPipelineReferences() {
  const pipelineIds = new Set(draftPipelines.value.map((pipeline) => pipeline.id))
  const downstream = new Map<string, string[]>()
  for (const pipeline of draftPipelines.value) {
    for (const stage of pipeline.stages) {
      if (!stage.pipeline) continue
      if (!pipelineIds.has(stage.pipeline)) {
        return `Stage ${pipeline.id}/${stage.id} references unknown pipeline ${stage.pipeline}`
      }
      if (stage.pipeline === pipeline.id) {
        return `Stage ${pipeline.id}/${stage.id} cannot reference its own pipeline`
      }
      const targets = downstream.get(pipeline.id) ?? []
      targets.push(stage.pipeline)
      downstream.set(pipeline.id, targets)
    }
  }

  const visiting = new Set<string>()
  const visited = new Set<string>()
  const visit = (pipelineId: string): string | null => {
    if (visiting.has(pipelineId)) return `Pipeline reference cycle detected at ${pipelineId}`
    if (visited.has(pipelineId)) return null
    visiting.add(pipelineId)
    for (const target of downstream.get(pipelineId) ?? []) {
      const error = visit(target)
      if (error) return error
    }
    visiting.delete(pipelineId)
    visited.add(pipelineId)
    return null
  }

  for (const pipeline of draftPipelines.value) {
    const error = visit(pipeline.id)
    if (error) return error
  }
  return ''
}

function uniqueId(prefix: string, existingIds: string[]) {
  let index = existingIds.length + 1
  let id = `${prefix}-${index}`
  while (existingIds.includes(id)) {
    index += 1
    id = `${prefix}-${index}`
  }
  return id
}

onMounted(() => {
  showPipelineIndex()
  loadCameras()
    .then(refreshCamera)
    .catch(() => undefined)
})
</script>

<template>
  <main class="shell">
    <aside class="sidebar">
      <div class="brand">NVR Debugger</div>
      <label class="field">
        <span>Camera</span>
        <select v-model="selectedCameraId" @change="refreshCamera">
          <option v-if="isLoadingCameras" value="">Loading cameras</option>
          <option v-else-if="cameras.length === 0" value="">No cameras loaded</option>
          <option v-for="camera in cameras" :key="camera.id" :value="camera.id">
            {{ camera.name }}
          </option>
        </select>
      </label>
      <button class="refresh-button" @click="loadCameras().then(refreshCamera)">Refresh Cameras</button>
      <div class="camera-state">
        <span>{{ selectedCamera?.enabled ? 'Recorder enabled' : 'Recorder disabled' }}</span>
        <span>{{ selectedCamera?.pipeline_enabled ? 'Pipeline enabled' : 'Pipeline disabled' }}</span>
      </div>

      <section class="tree-panel">
        <header>
          <strong>Pipeline Tree</strong>
          <button title="Add pipeline" @click="addPipelineFromTree">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path :d="iconPaths.plus" />
            </svg>
          </button>
        </header>
        <div class="tree">
          <div v-if="draftPipelines.length === 0" class="tree-empty">No pipelines</div>
          <div v-for="pipeline in draftPipelines" :key="pipeline.id" class="tree-branch">
            <div
              class="tree-row"
              :class="{ selected: pipeline.id === selectedPipelineId && !selectedStageId }"
              @click="selectPipeline(pipeline.id)"
              @dblclick="openPipelineDebug(pipeline.id)"
            >
              <span class="tree-icon">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path :d="iconPaths.pipeline" />
                </svg>
              </span>
              <span class="tree-label">{{ pipeline.name || pipeline.id }}</span>
              <button title="Add stage" @click.stop="addStageToPipeline(pipeline.id)">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path :d="iconPaths.plus" />
                </svg>
              </button>
              <button title="Remove pipeline" @click.stop="deletePipeline(pipeline.id)">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path :d="iconPaths.trash" />
                </svg>
              </button>
            </div>
            <div class="tree-children">
              <div
                v-for="stage in pipeline.stages"
                :key="stage.id"
                class="tree-row stage"
                :class="{ selected: pipeline.id === selectedPipelineId && stage.id === selectedStageId }"
                @click="selectStageInPipeline(pipeline.id, stage.id)"
                @dblclick="openStageDebug(pipeline.id, stage.id)"
              >
                <span class="tree-icon">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path :d="stage.pipeline ? iconPaths.link : stage.filename ? iconPaths.file : iconPaths.stage" />
                  </svg>
                </span>
                <span class="tree-label">{{ stage.id }}</span>
                <button title="Remove stage" @click.stop="deleteStage(pipeline.id, stage.id)">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path :d="iconPaths.trash" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div class="controls">
        <button @click="runCommand('run')">Run</button>
        <button @click="runCommand('pause')">Pause</button>
        <button @click="runCommand('step')">Step</button>
        <button @click="runCommand('step_over_stage')">Step Stage</button>
        <button @click="runCommand('step_over_pipeline')">Step Pipeline</button>
      </div>
      <label class="field">
        <span>Breakpoint</span>
        <select v-model="selectedBreakpoint">
          <option value="">None</option>
          <template v-for="pipeline in pipelines" :key="pipeline.id">
            <option :value="`${pipeline.id}:`">{{ pipeline.id }}</option>
            <option
              v-for="stage in pipeline.stages"
              :key="`${pipeline.id}:${stage.id}`"
              :value="`${pipeline.id}:${stage.id}`"
            >
              {{ pipeline.id }} / {{ stage.id }}
            </option>
          </template>
        </select>
      </label>
      <div class="breakpoint-actions">
        <button @click="toggleBreakpoint(true)">Set</button>
        <button @click="toggleBreakpoint(false)">Clear</button>
      </div>
      <p v-if="apiError" class="error">{{ apiError }}</p>
      <p v-if="deployStatus" class="status">{{ deployStatus }}</p>
    </aside>

    <section v-if="currentView === 'index'" class="workspace">
      <header class="statusbar">
        <span>Pipelines</span>
        <span>{{ pipelines.length }} configured</span>
      </header>

      <section class="pipeline-index">
        <article v-for="pipeline in pipelines" :key="pipeline.id" class="pipeline-card">
          <header>
            <div>
              <strong>{{ pipeline.name || pipeline.id }}</strong>
              <small>{{ pipeline.id }}</small>
            </div>
            <span>{{ pipeline.enabled ? 'enabled' : 'disabled' }}</span>
          </header>
          <div class="stage-list">
            <div v-for="stage in pipeline.stages" :key="stage.id" class="stage-row static">
              <span>{{ stage.id }}</span>
              <small>{{ stageSummary(stage) }}</small>
            </div>
          </div>
          <button @click="openPipelineDebug(pipeline.id)">View</button>
        </article>
      </section>
    </section>

    <section v-else class="workspace">
      <header class="statusbar">
        <button @click="showPipelineIndex">Pipelines</button>
        <span>Status: {{ debugState.status }}</span>
        <span>Step {{ debugState.cursor ?? 0 }} / {{ debugState.total_steps ?? 0 }}</span>
      </header>

      <section class="graph">
        <div v-for="pipeline in visiblePipelines" :key="pipeline.id" class="pipeline-card">
          <header>
            <strong>{{ pipeline.name || pipeline.id }}</strong>
            <span>{{ pipeline.enabled ? 'enabled' : 'disabled' }}</span>
          </header>
          <button v-for="stage in pipeline.stages" :key="stage.id" class="stage-row">
            <span>{{ stage.id }}</span>
            <small>{{ stageSummary(stage) }}</small>
          </button>
        </div>
      </section>

      <section class="editor">
        <header class="editor-header">
          <strong>Pipeline Draft</strong>
          <div class="editor-actions">
            <button @click="loadDraftPipelines">Reload Draft</button>
            <button @click="saveDraftPipelines">Save Draft</button>
            <button @click="deployDraftPipelines">Deploy</button>
          </div>
        </header>

        <div class="editor-grid">
          <section class="editor-panel">
            <header>
              <strong>Pipelines</strong>
              <button @click="addPipeline">Add</button>
            </header>
            <label class="inline-field">
              <span>Enabled</span>
              <input v-model="draftEnabled" type="checkbox" />
            </label>
            <label class="field light">
              <span>Frame interval seconds</span>
              <input v-model="draftFrameIntervalSeconds" type="text" inputmode="decimal" />
            </label>
            <button
              v-for="pipeline in draftPipelines"
              :key="pipeline.id"
              class="stage-row"
              :class="{ selected: pipeline.id === selectedPipelineId }"
              @click="selectPipeline(pipeline.id)"
            >
              <span>{{ pipeline.id }}</span>
              <small>{{ pipeline.enabled ? 'enabled' : 'disabled' }}</small>
            </button>
          </section>

          <section class="editor-panel">
            <header>
              <strong>Pipeline</strong>
              <button @click="deleteSelectedPipeline">Delete</button>
            </header>
            <label class="field light">
              <span>ID</span>
              <input v-model="selectedPipelineIdEdit" type="text" />
            </label>
            <label class="field light">
              <span>Name</span>
              <input v-model="selectedPipelineNameEdit" type="text" />
            </label>
            <label class="inline-field">
              <span>Enabled</span>
              <input v-if="selectedDraftPipeline" v-model="selectedDraftPipeline.enabled" type="checkbox" />
            </label>
            <label class="field light">
              <span>Required inputs</span>
              <input v-model="selectedPipelineRequiredInputs" type="text" />
            </label>
            <button @click="applyPipelineEdits">Apply Pipeline</button>

            <header>
              <strong>Stages</strong>
              <button @click="addStage">Add</button>
            </header>
            <button
              v-for="stage in selectedDraftPipeline?.stages ?? []"
              :key="stage.id"
              class="stage-row"
              :class="{ selected: stage.id === selectedStageId }"
              @click="selectStage(stage.id)"
            >
              <span>{{ stage.id }}</span>
              <small>{{ stageSummary(stage) }}</small>
            </button>
          </section>

          <section class="editor-panel">
            <header>
              <strong>Stage</strong>
              <button @click="deleteSelectedStage">Delete</button>
            </header>
            <label class="field light">
              <span>ID</span>
              <input v-model="selectedStageIdEdit" type="text" />
            </label>
            <label class="inline-field">
              <span>Enabled</span>
              <input v-if="selectedDraftStage" v-model="selectedDraftStage.enabled" type="checkbox" />
            </label>
            <label class="field light">
              <span>Filename</span>
              <input v-model="selectedStageFilename" type="text" />
            </label>
            <label class="field light">
              <span>Pipeline reference</span>
              <select v-model="selectedStagePipeline">
                <option value=""></option>
                <option v-for="pipeline in draftPipelines" :key="pipeline.id" :value="pipeline.id">
                  {{ pipeline.id }}
                </option>
              </select>
            </label>
            <label class="field light">
              <span>Class</span>
              <input v-model="selectedStageClassName" type="text" />
            </label>
            <label class="field light">
              <span>Legacy module</span>
              <input v-model="selectedStageModule" type="text" />
            </label>
            <label class="field light">
              <span>Config JSON</span>
              <textarea v-model="selectedStageConfigJson" rows="8"></textarea>
            </label>
            <button @click="applyStageEdits">Apply Stage</button>
          </section>

          <section class="editor-panel">
            <header>
              <strong>Edges</strong>
              <button @click="addEdge">Add</button>
            </header>
            <div v-for="(edge, index) in draftEdges" :key="index" class="edge-row">
              <select v-model="edge.from">
                <option v-for="pipeline in draftPipelines" :key="pipeline.id" :value="pipeline.id">
                  {{ pipeline.id }}
                </option>
              </select>
              <select v-model="edge.to">
                <option v-for="pipeline in draftPipelines" :key="pipeline.id" :value="pipeline.id">
                  {{ pipeline.id }}
                </option>
              </select>
              <button @click="deleteEdge(index)">Delete</button>
            </div>
          </section>
        </div>
      </section>

      <section class="details">
        <div class="preview">
          <header>
            <strong>Preview</strong>
            <span>{{ latestRecord?.pipeline_id }} / {{ latestRecord?.stage_id }}</span>
          </header>
          <div class="preview-surface">
            <img
              v-if="latestRecord?.output_preview"
              :src="latestRecord.output_preview"
              alt="Latest stage output preview"
            />
            <span v-else>No preview available</span>
            <footer>
              <span>Input {{ latestRecord?.input_shape ?? [] }}</span>
              <span>Output {{ latestRecord?.output_shape ?? [] }}</span>
            </footer>
          </div>
        </div>

        <div class="metadata">
          <header>
            <strong>Metadata</strong>
            <span>{{ edges.length }} edges</span>
          </header>
          <pre>{{ formatJson(metadata) }}</pre>
        </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(body) {
  margin: 0;
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
  background: #f4f6f8;
  color: #1f2933;
}

button,
select,
input,
textarea {
  font: inherit;
}

.shell {
  display: grid;
  min-height: 100vh;
  grid-template-columns: 300px 1fr;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  background: #18222f;
  color: #f7fafc;
}

.brand {
  font-size: 20px;
  font-weight: 700;
}

.field {
  display: grid;
  gap: 6px;
  font-size: 13px;
}

.field select {
  width: 100%;
  border: 1px solid #506070;
  border-radius: 6px;
  padding: 8px;
  background: #ffffff;
  color: #1f2933;
}

.field.light input,
.field.light select,
.field.light textarea,
.edge-row select {
  width: 100%;
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 8px;
  background: #ffffff;
  color: #1f2933;
}

.field textarea {
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
    monospace;
  font-size: 12px;
}

.inline-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.camera-state {
  display: grid;
  gap: 6px;
  color: #cbd5df;
  font-size: 13px;
}

.tree-panel {
  display: grid;
  gap: 10px;
  min-height: 0;
}

.tree-panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}

.tree-panel header button,
.tree-row button {
  display: inline-grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid #506070;
  border-radius: 6px;
  background: #223044;
  color: #f7fafc;
  cursor: pointer;
}

.tree-panel svg,
.tree-row svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.tree {
  display: grid;
  gap: 4px;
  min-height: 80px;
  max-height: 34vh;
  overflow: auto;
  border: 1px solid #304157;
  border-radius: 8px;
  padding: 8px;
  background: #111b28;
}

.tree-empty {
  color: #9fb0c3;
  font-size: 13px;
}

.tree-branch {
  display: grid;
  gap: 2px;
}

.tree-children {
  display: grid;
  gap: 2px;
  margin-left: 18px;
}

.tree-row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  border-radius: 6px;
  padding: 2px 4px;
  color: #e6edf5;
  cursor: default;
}

.tree-row.stage {
  grid-template-columns: 18px minmax(0, 1fr) auto;
}

.tree-row:hover,
.tree-row.selected {
  background: #26364a;
}

.tree-icon {
  display: inline-grid;
  place-items: center;
  color: #a9c7ef;
}

.tree-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.controls,
.breakpoint-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.controls button,
.breakpoint-actions button,
.refresh-button,
.stage-row {
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 8px 10px;
  background: #ffffff;
  color: #1f2933;
  cursor: pointer;
}

.workspace {
  display: grid;
  grid-template-rows: auto auto auto 1fr;
  gap: 16px;
  padding: 18px;
}

.statusbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #d7dee7;
  padding-bottom: 10px;
  font-size: 14px;
}

.statusbar button,
.pipeline-card > button {
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 8px 10px;
  background: #ffffff;
  color: #1f2933;
  cursor: pointer;
}

.graph {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.pipeline-index {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
  align-content: start;
}

.pipeline-card header div {
  display: grid;
  gap: 2px;
}

.pipeline-card header small {
  color: #627386;
}

.stage-list {
  display: grid;
  gap: 8px;
}

.pipeline-card {
  display: grid;
  gap: 8px;
  border: 1px solid #d7dee7;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
}

.pipeline-card header,
.preview header,
.metadata header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.stage-row {
  display: grid;
  grid-template-columns: 1fr;
  text-align: left;
}

.stage-row small {
  color: #627386;
}

.stage-row.selected {
  border-color: #2563eb;
  background: #eff6ff;
}

.stage-row.static {
  cursor: default;
}

.editor {
  display: grid;
  gap: 12px;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.editor-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.editor-actions button,
.editor-panel button,
.edge-row button {
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 8px 10px;
  background: #ffffff;
  color: #1f2933;
  cursor: pointer;
}

.editor-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  gap: 12px;
}

.editor-panel {
  display: grid;
  align-content: start;
  gap: 10px;
  border: 1px solid #d7dee7;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
}

.editor-panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}

.edge-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: 8px;
}

.details {
  display: grid;
  grid-template-columns: minmax(260px, 420px) 1fr;
  gap: 16px;
  min-height: 0;
}

.preview,
.metadata {
  display: grid;
  gap: 10px;
  min-height: 0;
  border: 1px solid #d7dee7;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
}

.preview-surface {
  display: grid;
  grid-template-rows: 1fr auto;
  gap: 10px;
  align-items: center;
  justify-items: center;
  min-height: 260px;
  border: 1px dashed #9aa8b6;
  border-radius: 6px;
  padding: 10px;
  color: #627386;
}

.preview-surface img {
  display: block;
  max-width: 100%;
  max-height: 360px;
  object-fit: contain;
}

.preview-surface footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
  font-size: 12px;
}

.metadata pre {
  min-height: 0;
  overflow: auto;
  margin: 0;
  border-radius: 6px;
  padding: 12px;
  background: #111827;
  color: #e5e7eb;
  font-size: 13px;
}

.error {
  color: #fecaca;
}

.status {
  color: #bbf7d0;
}

@media (max-width: 820px) {
  .shell,
  .details,
  .editor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
