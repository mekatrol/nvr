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
  module: string
  class_name: string
}

type Pipeline = {
  id: string
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

const cameras = ref<Camera[]>([])
const selectedCameraId = ref('')
const pipelines = ref<Pipeline[]>([])
const edges = ref<Edge[]>([])
const debugState = ref<DebugState>({ status: 'idle', records: [] })
const metadata = ref<Record<string, unknown>>({})
const selectedBreakpoint = ref('')
const apiError = ref('')
const isLoadingCameras = ref(false)

const selectedCamera = computed(() =>
  cameras.value.find((camera) => camera.id === selectedCameraId.value),
)

const latestRecord = computed(() => debugState.value.records?.at(-1))

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

async function loadGraph() {
  if (!selectedCameraId.value) return
  const graph = await getJson<{ pipelines: Pipeline[]; edges: Edge[] }>(
    `/api/pipeline-graph?camera_id=${encodeURIComponent(selectedCameraId.value)}`,
  )
  pipelines.value = graph.pipelines
  edges.value = graph.edges
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
    await loadGraph()
    await loadDebugState()
  } catch {
    return
  }
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

onMounted(() => {
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
    </aside>

    <section class="workspace">
      <header class="statusbar">
        <span>Status: {{ debugState.status }}</span>
        <span>Step {{ debugState.cursor ?? 0 }} / {{ debugState.total_steps ?? 0 }}</span>
      </header>

      <section class="graph">
        <div v-for="pipeline in pipelines" :key="pipeline.id" class="pipeline-card">
          <header>
            <strong>{{ pipeline.id }}</strong>
            <span>{{ pipeline.enabled ? 'enabled' : 'disabled' }}</span>
          </header>
          <button v-for="stage in pipeline.stages" :key="stage.id" class="stage-row">
            <span>{{ stage.id }}</span>
            <small>{{ stage.class_name }}</small>
          </button>
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
select {
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

.camera-state {
  display: grid;
  gap: 6px;
  color: #cbd5df;
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
  grid-template-rows: auto auto 1fr;
  gap: 16px;
  padding: 18px;
}

.statusbar {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #d7dee7;
  padding-bottom: 10px;
  font-size: 14px;
}

.graph {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
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

@media (max-width: 820px) {
  .shell,
  .details {
    grid-template-columns: 1fr;
  }
}
</style>
