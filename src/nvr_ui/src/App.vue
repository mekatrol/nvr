<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MainNavBar from './components/MainNavBar.vue'

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
  features?: string[]
  config: Record<string, unknown>
}

type Pipeline = {
  id: string
  name?: string
  enabled: boolean
  stages: Stage[]
}

type PipelineIntegrityIssue = {
  level: string
  message: string
}

type PipelineIntegrity = {
  ok: boolean
  issues: PipelineIntegrityIssue[]
}

type DebugRecord = {
  pipeline_id: string
  stage_id: string
  status: string
  input_shape: number[] | null
  output_shape: number[] | null
  input_preview: string | null
  output_preview: string | null
}

type DebugState = {
  status: string
  cursor?: number
  total_steps?: number
  records?: DebugRecord[]
}

type PipelinesResponse = {
  enabled: boolean
  integrity?: PipelineIntegrity
  frame_interval_seconds: number | string | null
  selected_pipeline_config_path?: string
  pipelines: Pipeline[]
}

type LogEntry = {
  timestamp: string
  level: string
  description: string
}

type LogSeverity = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

type MaskPoint = {
  x: number
  y: number
}

type MaskConfig = {
  polygons?: MaskPoint[][]
  [key: string]: unknown
}

const logSeverityOptions: LogSeverity[] = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

const materialIcons = {
  pipeline: 'account_tree',
  stage: 'deployed_code',
  file: 'description',
  link: 'link',
  plus: 'add',
  trash: 'delete',
  run: 'play_arrow',
  stop: 'stop',
  step: 'skip_next',
  stepStage: 'step_into',
  stepPipeline: 'account_tree',
  breakpoint: 'radio_button_checked',
  clearBreakpoint: 'block',
  expand: 'fullscreen',
  collapse: 'fullscreen_exit',
} as const

const cameras = ref<Camera[]>([])
const defaultPipelineFrameIntervalSeconds = 0.5
const selectedCameraId = ref('')
const pipelines = ref<Pipeline[]>([])
const debugState = ref<DebugState>({ status: 'idle', records: [] })
const selectedBreakpoint = ref('')
const apiError = ref('')
const isLoadingCameras = ref(false)
const pipelineConfigPipelines = ref<Pipeline[]>([])
const selectedPipelineConfigPath = ref('')
const pipelineIntegrity = ref<PipelineIntegrity>({ ok: true, issues: [] })
const debugPipelineId = ref('')
const selectedPipelineId = ref('')
const selectedStageId = ref('')
const selectedStageConfigJson = ref('{}')
const deployStatus = ref('')
const logEntries = ref<LogEntry[]>([])
const selectedLogSeverities = ref<LogSeverity[]>([...logSeverityOptions])
const isLoadingLogs = ref(false)
const logRefreshTimer = ref<ReturnType<typeof setInterval> | null>(null)
const route = useRoute()
const vscodeLoadFailed = ref(false)
const runLoopTimer = ref<ReturnType<typeof setInterval> | null>(null)
const isRunLoopActive = ref(false)
const isRunLoopTicking = ref(false)
const currentAction = ref('')
const maskPreviewImage = ref<HTMLImageElement | null>(null)
const maskDraftPolygon = ref<MaskPoint[]>([])
const expandedPreview = ref<'input' | 'output' | null>(null)
const ignoreNextMaskClick = ref(false)
const allowPolygonsFeature = 'AllowPolygons'
const vscodeWebUrl = computed(
  () =>
    import.meta.env.VITE_VSCODE_WEB_URL ||
    'http://127.0.0.1:8000/?folder=/home/dad/nvr/pipeline_config/pipelines',
)
const isEditorRoute = computed(() => route.path === '/editor')
const isLogRoute = computed(() => route.path === '/log')

const selectedCamera = computed(() =>
  cameras.value.find((camera) => camera.id === selectedCameraId.value),
)
const selectedDebugPipeline = computed(() =>
  pipelines.value.find((pipeline) => pipeline.id === debugPipelineId.value),
)
const selectedDebugPipelineStages = computed(() => selectedDebugPipeline.value?.stages ?? [])

const latestRecord = computed(() => debugState.value.records?.at(-1))
const selectedStagePreviewRecord = computed(() => {
  const records = debugState.value.records ?? []
  if (!selectedPipelineId.value || !selectedStageId.value) return undefined
  for (let index = records.length - 1; index >= 0; index -= 1) {
    const record = records[index]
    if (
      record?.pipeline_id === selectedPipelineId.value &&
      record.stage_id === selectedStageId.value
    ) {
      return record
    }
  }
  return undefined
})
const stagePreviewRecord = computed(() => selectedStagePreviewRecord.value ?? latestRecord.value)
const hasPipelineIntegrityProblem = computed(() => !pipelineIntegrity.value.ok)

const filteredLogEntries = computed(() => {
  const selectedLevels = new Set(selectedLogSeverities.value)
  return logEntries.value.filter((entry) => selectedLevels.has(entry.level as LogSeverity))
})

const selectedPipelinesPipeline = computed(() =>
  pipelineConfigPipelines.value.find((pipeline) => pipeline.id === selectedPipelineId.value),
)

const selectedPipelinesStage = computed(() =>
  selectedPipelinesPipeline.value?.stages.find((stage) => stage.id === selectedStageId.value),
)

const isActionBusy = computed(() => currentAction.value.length > 0)
const hasSelectedCamera = computed(() => selectedCameraId.value.length > 0)
const hasPipelinesStage = computed(() => Boolean(selectedPipelinesStage.value))
const isSelectedMaskStage = computed(() => {
  const stage = selectedPipelinesStage.value
  if (!stage) return false
  return stage.features?.includes(allowPolygonsFeature) ?? false
})
const canRun = computed(
  () =>
    hasSelectedCamera.value &&
    !hasPipelineIntegrityProblem.value &&
    !isRunLoopActive.value &&
    !isActionBusy.value,
)
const canStop = computed(() => isRunLoopActive.value && !isActionBusy.value)
const canStep = computed(
  () =>
    hasSelectedCamera.value &&
    !hasPipelineIntegrityProblem.value &&
    !isRunLoopActive.value &&
    !isActionBusy.value,
)
const canEditPipelines = computed(() => !isRunLoopActive.value && !isActionBusy.value)
const maskPreviewShape = computed(() => selectedStagePreviewRecord.value?.input_shape ?? null)
const maskFrameWidth = computed(() => maskPreviewShape.value?.[1] ?? 0)
const maskFrameHeight = computed(() => maskPreviewShape.value?.[0] ?? 0)
const canDraftMask = computed(
  () =>
    hasPipelinesStage.value &&
    isSelectedMaskStage.value &&
    Boolean(selectedStagePreviewRecord.value?.input_preview) &&
    maskFrameWidth.value > 0 &&
    maskFrameHeight.value > 0,
)
const hasMaskDraftArea = computed(() => polygonArea(maskDraftPolygon.value) > 0)
const maskPolygons = computed(() => readMaskPolygons())
const canSetBreakpoint = computed(
  () =>
    hasSelectedCamera.value &&
    !hasPipelineIntegrityProblem.value &&
    selectedBreakpoint.value.length > 0 &&
    !isRunLoopActive.value &&
    !isActionBusy.value,
)

const loadCameras = async (): Promise<void> => {
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

const loadPipelines = async (): Promise<void> => {
  if (!selectedCameraId.value) return
  const pathQuery = pipelineConfigPathQuery()
  const graph = await getJson<{
    pipelines: Pipeline[]
    integrity?: PipelineIntegrity
  }>(`/api/pipelines?camera_id=${encodeURIComponent(selectedCameraId.value)}${pathQuery}`)
  applyPipelineGraph(graph)
}

const applyPipelineGraph = (graph: { pipelines: Pipeline[]; integrity?: PipelineIntegrity }): void => {
  pipelines.value = graph.pipelines
  pipelineIntegrity.value = graph.integrity ?? { ok: true, issues: [] }
  syncDebugPipelineSelection()
}

const loadPipelineConfigPipelines = async (): Promise<void> => {
  const graph = await getJson<PipelinesResponse>('/api/pipeline_config/pipelines')
  pipelineIntegrity.value = graph.integrity ?? { ok: true, issues: [] }
  pipelineConfigPipelines.value = graph.pipelines
  if (!selectedPipelineId.value && pipelineConfigPipelines.value[0]) {
    selectPipeline(pipelineConfigPipelines.value[0].id)
  } else {
    refreshSelectedEditors()
  }
  syncDebugPipelineSelection()
}

const reloadPipelines = async (): Promise<void> => {
  await stopRunLoop(false)
  await postJson<{ pipelines: Pipeline[]; integrity?: PipelineIntegrity }>(
    '/api/pipelines/reload',
    {},
  )
  await loadPipelines()
  await loadPipelineConfigPipelines()
  await loadDebugState()
  deployStatus.value = 'Pipelines reloaded from disk'
}

const loadDebugState = async (): Promise<void> => {
  if (!selectedCameraId.value) return
  const pathQuery = pipelineConfigPathQuery()
  debugState.value = await getJson<DebugState>(
    `/api/debug/state?camera_id=${encodeURIComponent(selectedCameraId.value)}${pathQuery}`,
  )
}

const loadLogs = async (): Promise<void> => {
  isLoadingLogs.value = true
  try {
    const payload = await getJson<{ entries: LogEntry[] }>('/api/logs?limit=500')
    logEntries.value = payload.entries
  } finally {
    isLoadingLogs.value = false
  }
}

const clearLogs = async (): Promise<void> => {
  const payload = await postJson<{ entries: LogEntry[] }>('/api/logs/clear', {})
  logEntries.value = payload.entries
}

const runCommand = async (command: string): Promise<void> => {
  if (!selectedCameraId.value) return
  debugState.value = await postJson<DebugState>('/api/debug/command', {
    camera_id: selectedCameraId.value,
    pipeline_config_path: selectedPipelineConfigPath.value,
    command,
  })
  await loadDebugState()
  syncSelectionToLatestDebugRecord()
}

const runDebuggerCommand = async (command: string): Promise<void> => {
  if (isActionBusy.value) return
  await withAction(command, () => runCommand(command))
}

const stopDebuggerRun = async (): Promise<void> => {
  if (!canStop.value) return
  await withAction('stop', () => stopRunLoop())
}

const startRunLoop = async (): Promise<void> => {
  if (isRunLoopActive.value || isActionBusy.value) return
  isRunLoopActive.value = true
  try {
    await runLoopTick()
  } catch {
    stopRunLoop(false)
    return
  }
  if (!isRunLoopActive.value) return
  runLoopTimer.value = setInterval(() => {
    runLoopTick().catch(() => stopRunLoop(false))
  }, defaultPipelineFrameIntervalSeconds * 1000)
}

const runLoopTick = async (): Promise<void> => {
  if (isRunLoopTicking.value) return
  if (!selectedCameraId.value) {
    stopRunLoop(false)
    return
  }
  isRunLoopTicking.value = true
  try {
    await runCommand('run')
    if (debugState.value.status === 'paused') {
      stopRunLoop(false)
    }
  } finally {
    isRunLoopTicking.value = false
  }
}

const stopRunLoop = async (sendPause: boolean = true): Promise<void> => {
  isRunLoopActive.value = false
  if (runLoopTimer.value) {
    clearInterval(runLoopTimer.value)
    runLoopTimer.value = null
  }
  if (sendPause && selectedCameraId.value) {
    await runCommand('pause').catch(() => undefined)
  }
}

const toggleBreakpoint = async (enabled: boolean): Promise<void> => {
  if (isActionBusy.value || !selectedCameraId.value || !selectedBreakpoint.value) return
  currentAction.value = enabled ? 'set_breakpoint' : 'clear_breakpoint'
  try {
    const [pipelineId, stageId] = selectedBreakpoint.value.split(':')
    debugState.value = await postJson<DebugState>('/api/debug/breakpoints', {
      camera_id: selectedCameraId.value,
      pipeline_config_path: selectedPipelineConfigPath.value,
      pipeline_id: pipelineId,
      stage_id: stageId || null,
      enabled,
    })
  } finally {
    currentAction.value = ''
  }
}

const refreshCamera = async (): Promise<void> => {
  await stopRunLoop(false)
  try {
    selectedPipelineConfigPath.value = ''
    await loadPipelines()
    await loadDebugState()
    await loadPipelineConfigPipelines()
  } catch {
    return
  }
}

const withAction = async <T,>(action: string, task: () => Promise<T>): Promise<T | undefined> => {
  if (isActionBusy.value) return undefined
  currentAction.value = action
  try {
    return await task()
  } finally {
    currentAction.value = ''
  }
}

const generateExampleResizePipeline = async (): Promise<void> => {
  const generated = await postJson<PipelinesResponse>('/api/pipelines/examples/resize', {})
  pipelineConfigPipelines.value = generated.pipelines
  selectPipeline('example-resize')
  deployStatus.value =
    'Example resize pipeline generated. Use Debugger to run it, or deploy pipelines when ready.'
}

const deployPipelinesFromEditor = async (): Promise<void> => {
  const deployed = await postJson<PipelinesResponse>('/api/pipeline_config/pipelines/deploy', {})
  pipelines.value = deployed.pipelines
  syncDebugPipelineSelection()
  deployStatus.value = 'Pipelines deployed and server config reloaded'
}

const getJson = async <T,>(path: string): Promise<T> => {
  apiError.value = ''
  let response: Response
  try {
    response = await fetch(`${__API_BASE_URL__}${path}`)
  } catch (error) {
    apiError.value = `Unable to reach NVR web API at ${path}`
    throw error
  }
  if (!response.ok) {
    apiError.value = await responseErrorMessage(response)
    throw new Error(apiError.value)
  }
  return response.json() as Promise<T>
}

const postJson = async <T,>(path: string, body: Record<string, unknown>): Promise<T> => {
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
    apiError.value = await responseErrorMessage(response)
    throw new Error(apiError.value)
  }
  return response.json() as Promise<T>
}

const responseErrorMessage = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.clone().json()) as { error?: unknown }
    if (typeof payload.error === 'string' && payload.error.length > 0) {
      return payload.error
    }
  } catch {
    return `${response.status} ${response.statusText}`
  }
  return `${response.status} ${response.statusText}`
}

const formatJson = (value: unknown): string => {
  return JSON.stringify(value ?? {}, null, 2)
}

const selectPipeline = (pipelineId: string): void => {
  selectedPipelineId.value = pipelineId
  selectedStageId.value = selectedPipelinesPipeline.value?.stages[0]?.id ?? ''
  refreshSelectedEditors()
}

const refreshSelectedEditors = (): void => {
  const stage = selectedPipelinesStage.value
  selectedStageConfigJson.value = formatJson(stage?.config ?? {})
  maskDraftPolygon.value = []
}

const selectDebugPipeline = (pipelineId: string): void => {
  if (hasPipelineIntegrityProblem.value || !pipelineId) return
  const pipeline =
    pipelines.value.find((candidate) => candidate.id === pipelineId) ??
    pipelineConfigPipelines.value.find((candidate) => candidate.id === pipelineId)
  if (!pipeline) return
  debugPipelineId.value = pipeline.id
  selectedPipelineId.value = pipeline.id
  selectedStageId.value = pipeline.stages[0]?.id ?? ''
  refreshSelectedEditors()
}

const selectDebugStage = (stageId: string): void => {
  selectedStageId.value = stageId
  refreshSelectedEditors()
}

const syncSelectionToLatestDebugRecord = (): void => {
  const record = debugState.value.records?.at(-1)
  if (!record) return
  const pipeline = pipelines.value.find((candidate) => candidate.id === record.pipeline_id)
  if (!pipeline) return
  debugPipelineId.value = pipeline.id
  selectedPipelineId.value = pipeline.id
  selectedStageId.value = record.stage_id
  refreshSelectedEditors()
}

const syncDebugPipelineSelection = (): void => {
  if (hasPipelineIntegrityProblem.value || pipelines.value.length === 0) {
    debugPipelineId.value = ''
    refreshSelectedEditors()
    return
  }
  const selectedPipeline =
    pipelines.value.find((pipeline) => pipeline.id === debugPipelineId.value) ??
    pipelines.value.find((pipeline) => pipeline.id === selectedPipelineId.value) ??
    pipelines.value[0]
  if (selectedPipeline) {
    selectDebugPipeline(selectedPipeline.id)
  }
}

const pipelineConfigPathQuery = (): string => {
  if (!selectedPipelineConfigPath.value) return ''
  return `&pipeline_config_path=${encodeURIComponent(selectedPipelineConfigPath.value)}`
}

const handleMaskPreviewClick = (event: MouseEvent): void => {
  if (ignoreNextMaskClick.value) {
    ignoreNextMaskClick.value = false
    return
  }
  addMaskPreviewPoint(event)
}

const handleMaskPreviewDoubleClick = (event: MouseEvent): void => {
  ignoreNextMaskClick.value = true
  addMaskPreviewPoint(event)
  commitMaskDraftPolygon()
}

const addMaskPreviewPoint = (event: MouseEvent): void => {
  if (!canDraftMask.value) return
  const image = maskPreviewImage.value
  if (!image) return
  const rect = image.getBoundingClientRect()
  const x = Math.round(((event.clientX - rect.left) / rect.width) * maskFrameWidth.value)
  const y = Math.round(((event.clientY - rect.top) / rect.height) * maskFrameHeight.value)
  maskDraftPolygon.value.push({
    x: clamp(x, 0, Math.max(0, maskFrameWidth.value - 1)),
    y: clamp(y, 0, Math.max(0, maskFrameHeight.value - 1)),
  })
}

const togglePreviewExpansion = (preview: 'input' | 'output'): void => {
  expandedPreview.value = expandedPreview.value === preview ? null : preview
}

const updateMaskConfig = (polygons: MaskPoint[][]): void => {
  const config = readMaskConfig()
  config.polygons = polygons
  selectedStageConfigJson.value = formatJson(config)
  const stage = selectedPipelinesStage.value
  if (stage && isSelectedMaskStage.value) {
    stage.config = config
  }
}

const commitMaskDraftPolygon = (): void => {
  if (!hasMaskDraftArea.value) return
  updateMaskConfig([...maskPolygons.value, [...maskDraftPolygon.value]])
  maskDraftPolygon.value = []
}

const readMaskPolygons = (): MaskPoint[][] => {
  return readMaskConfig().polygons ?? []
}

const readMaskConfig = (): MaskConfig => {
  try {
    const parsed = JSON.parse(selectedStageConfigJson.value || '{}') as MaskConfig
    const polygons = Array.isArray(parsed.polygons) ? parsed.polygons : []
    return {
      ...parsed,
      polygons: polygons
        .map((polygon) => normalizeMaskPolygon(polygon))
        .filter((polygon) => polygon.length > 0),
    }
  } catch {
    return { polygons: [] }
  }
}

const normalizeMaskPolygon = (value: unknown): MaskPoint[] => {
  if (!Array.isArray(value)) return []
  return value
    .map((point) => normalizeMaskPoint(point))
    .filter((point): point is MaskPoint => point !== null)
}

const normalizeMaskPoint = (value: unknown): MaskPoint | null => {
  if (!value || typeof value !== 'object') return null
  const point = value as Record<string, unknown>
  const x = point.x
  const y = point.y
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null
  return { x: Math.round(Number(x)), y: Math.round(Number(y)) }
}

const maskPolygonPoints = (polygon: MaskPoint[]): string => {
  return polygon.map((point) => `${point.x},${point.y}`).join(' ')
}

const polygonArea = (polygon: MaskPoint[]): number => {
  if (polygon.length < 3) return 0
  let area = 0
  for (let index = 0; index < polygon.length; index += 1) {
    const current = polygon[index]!
    const next = polygon[(index + 1) % polygon.length]!
    area += current.x * next.y - next.x * current.y
  }
  return Math.abs(area) / 2
}

const clamp = (value: number, min: number, max: number): number => {
  return Math.min(Math.max(value, min), max)
}

const startLogRefresh = (): void => {
  if (logRefreshTimer.value) return
  loadLogs().catch(() => undefined)
  logRefreshTimer.value = setInterval(() => {
    loadLogs().catch(() => undefined)
  }, 3000)
}

const stopLogRefresh = (): void => {
  if (!logRefreshTimer.value) return
  clearInterval(logRefreshTimer.value)
  logRefreshTimer.value = null
}

onMounted(() => {
  syncDebugPipelineSelection()
  if (isLogRoute.value) {
    startLogRefresh()
  }
  loadCameras()
    .then(refreshCamera)
    .catch(() => undefined)
})

watch(
  () => route.path,
  (path) => {
    if (path === '/log') {
      startLogRefresh()
    } else {
      stopLogRefresh()
    }
  },
)

onBeforeUnmount(() => {
  stopRunLoop(false)
  stopLogRefresh()
})
</script>

<template>
  <div class="app-layout">
    <aside class="app-sidebar">
      <div class="app-brand">NVR</div>
      <MainNavBar />
    </aside>

    <main class="app-content">
      <section v-if="isEditorRoute" class="vscode-shell">
        <header class="vscode-header">
          <div>
            <strong>NVR Editor</strong>
            <span>pipeline_conf.yaml and Python stage files</span>
          </div>
          <div class="vscode-actions">
            <button :disabled="!canEditPipelines" @click="withAction('example_resize', generateExampleResizePipeline)">
              Example Resize
            </button>
            <button :disabled="!canEditPipelines" @click="withAction('deploy_pipelines', deployPipelinesFromEditor)">
              Deploy Pipelines
            </button>
            <a :href="vscodeWebUrl" target="_blank" rel="noreferrer">Open</a>
          </div>
        </header>
        <section class="vscode-stage">
          <p v-if="apiError" class="vscode-message error">{{ apiError }}</p>
          <p v-if="deployStatus" class="vscode-message status">{{ deployStatus }}</p>
          <iframe class="vscode-frame" :src="vscodeWebUrl" title="VS Code Web editor"
            allow="clipboard-read; clipboard-write" @load="vscodeLoadFailed = false"
            @error="vscodeLoadFailed = true"></iframe>
          <div v-if="vscodeLoadFailed" class="vscode-error">
            <strong>VS Code Web is not available.</strong>
            <span>Start it with code serve-web --host 127.0.0.1 --port 8000 --without-connection-token
              --accept-server-license-terms --default-folder /home/dad/nvr/pipeline_config, then
              reload this view.</span>
          </div>
        </section>
      </section>

      <section v-else-if="isLogRoute" class="log-shell">
        <header class="vscode-header">
          <div>
            <strong>NVR Log</strong>
            <span>{{ filteredLogEntries.length }} / {{ logEntries.length }} entries shown</span>
          </div>
          <div class="log-actions">
            <fieldset class="log-filter">
              <legend>Severity</legend>
              <label v-for="level in logSeverityOptions" :key="level">
                <input v-model="selectedLogSeverities" type="checkbox" :value="level" />
                <span>{{ level }}</span>
              </label>
            </fieldset>
            <button :disabled="isLoadingLogs" @click="loadLogs">Refresh</button>
            <button :disabled="isLoadingLogs || logEntries.length === 0" @click="clearLogs">
              Clear
            </button>
          </div>
        </header>

        <section class="log-workspace">
          <p v-if="apiError" class="log-error">{{ apiError }}</p>
          <div class="log-table" role="table" aria-label="NVR log entries">
            <div class="log-row log-heading" role="row">
              <span role="columnheader">Date/time</span>
              <span role="columnheader">Log level</span>
              <span role="columnheader">Log description</span>
            </div>
            <div v-if="filteredLogEntries.length === 0" class="log-empty">No log entries</div>
            <div v-for="(entry, index) in filteredLogEntries" :key="`${entry.timestamp}-${index}`" class="log-row"
              role="row">
              <span class="log-time" role="cell">{{ entry.timestamp }}</span>
              <span class="log-level" :class="`level-${entry.level.toLowerCase()}`" role="cell">
                {{ entry.level }}
              </span>
              <span class="log-description" role="cell">{{ entry.description }}</span>
            </div>
          </div>
        </section>
      </section>

      <section v-else class="shell">
        <section class="workspace">
          <section class="pipeline-ribbon" aria-label="Pipeline debugger controls">
            <div class="ribbon-group debugger-selectors">
              <label class="ribbon-field">
                <span>Camera</span>
                <select v-model="selectedCameraId" @change="refreshCamera">
                  <option v-if="isLoadingCameras" value="">Loading cameras</option>
                  <option v-else-if="cameras.length === 0" value="">No cameras loaded</option>
                  <option v-for="camera in cameras" :key="camera.id" :value="camera.id">
                    {{ camera.name }}
                  </option>
                </select>
              </label>
              <label class="ribbon-field">
                <span>Pipeline</span>
                <select v-model="debugPipelineId" :disabled="hasPipelineIntegrityProblem || pipelines.length === 0"
                  @change="selectDebugPipeline(debugPipelineId)">
                  <option v-if="pipelines.length === 0" value="">No pipelines loaded</option>
                  <option v-for="pipeline in pipelines" :key="pipeline.id" :value="pipeline.id">
                    {{ pipeline.name || pipeline.id }}
                  </option>
                </select>
              </label>
              <label class="ribbon-field">
                <span>Stage</span>
                <select v-model="selectedStageId"
                  :disabled="hasPipelineIntegrityProblem || selectedDebugPipelineStages.length === 0"
                  @change="selectDebugStage(selectedStageId)">
                  <option v-if="selectedDebugPipelineStages.length === 0" value="">No stages loaded</option>
                  <option v-for="stage in selectedDebugPipelineStages" :key="stage.id" :value="stage.id">
                    {{ stage.id }}
                  </option>
                </select>
              </label>
              <button class="refresh-button" :disabled="isActionBusy || isRunLoopActive"
                @click="withAction('refresh_cameras', () => loadCameras().then(refreshCamera))">
                Refresh
              </button>
              <button class="refresh-button" :disabled="isActionBusy || isRunLoopActive"
                @click="withAction('reload_pipelines', reloadPipelines)">
                Reload Pipeline
              </button>
            </div>
            <div class="ribbon-group">
              <button :disabled="!canRun" title="Run" @click="startRunLoop">
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.run }}
                </span>
                <span>{{ isRunLoopActive ? 'Running' : 'Run' }}</span>
              </button>
              <button :disabled="!canStop" title="Stop" @click="stopDebuggerRun">
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.stop }}
                </span>
                <span>Stop</span>
              </button>
              <button :disabled="!canStep" title="Step" @click="runDebuggerCommand('step')">
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.step }}
                </span>
                <span>Step</span>
              </button>
              <button :disabled="!canStep" title="Step stage" @click="runDebuggerCommand('step_over_stage')">
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.stepStage }}
                </span>
                <span>Step Stage</span>
              </button>
              <button :disabled="!canStep" title="Step pipeline" @click="runDebuggerCommand('step_over_pipeline')">
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.stepPipeline }}
                </span>
                <span>Step Pipeline</span>
              </button>
            </div>
            <div class="ribbon-group breakpoint-ribbon">
              <label class="ribbon-field">
                <span>Breakpoint</span>
                <select v-model="selectedBreakpoint">
                  <option value="">None</option>
                  <template v-for="pipeline in pipelines" :key="pipeline.id">
                    <option :value="`${pipeline.id}:`">{{ pipeline.name || pipeline.id }}</option>
                    <option v-for="stage in pipeline.stages" :key="`${pipeline.id}:${stage.id}`"
                      :value="`${pipeline.id}:${stage.id}`">
                      {{ pipeline.name || pipeline.id }} / {{ stage.id }}
                    </option>
                  </template>
                </select>
              </label>
              <button :disabled="!canSetBreakpoint" title="Set breakpoint" @click="toggleBreakpoint(true)">
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.breakpoint }}
                </span>
                <span>Set</span>
              </button>
              <button :disabled="!canSetBreakpoint" title="Clear breakpoint" @click="toggleBreakpoint(false)">
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.clearBreakpoint }}
                </span>
                <span>Clear</span>
              </button>
            </div>
          </section>

          <header class="statusbar">
            <span>{{ selectedDebugPipeline?.name || selectedDebugPipeline?.id || 'No pipeline selected' }}</span>
            <span>{{
              selectedCamera?.enabled ? 'Recorder enabled' : 'Recorder disabled'
            }}</span>
            <span>{{
              selectedCamera?.pipeline_enabled ? 'Pipeline enabled' : 'Pipeline disabled'
            }}</span>
            <span v-if="hasPipelineIntegrityProblem">Debugging blocked: pipeline integrity problem</span>
            <span v-else>Status: {{ debugState.status }}</span>
            <span>Step {{ debugState.cursor ?? 0 }} / {{ debugState.total_steps ?? 0 }}</span>
          </header>

          <p v-if="apiError" class="workspace-message error">{{ apiError }}</p>
          <p v-if="deployStatus" class="workspace-message status">{{ deployStatus }}</p>

          <section v-if="hasPipelineIntegrityProblem" class="workspace-integrity">
            <strong>Pipeline integrity problem</strong>
            <span v-for="(issue, index) in pipelineIntegrity.issues" :key="index">
              {{ issue.message }}
            </span>
          </section>

          <section v-else-if="!selectedDebugPipeline" class="workspace-integrity">
            <strong>No pipeline selected</strong>
            <span>Select a camera and pipeline to debug.</span>
          </section>

          <section class="stage-preview" aria-label="Stage image preview">
            <header class="stage-preview-header">
              <strong>Stage Preview</strong>
              <span>{{ stagePreviewRecord?.pipeline_id }} / {{ stagePreviewRecord?.stage_id }}</span>
            </header>
            <div class="stage-preview-grid">
              <article class="stage-preview-pane" :class="{ expanded: expandedPreview === 'input' }">
                <header>
                  <strong>Entering Stage</strong>
                  <button :disabled="!stagePreviewRecord?.input_preview" :title="expandedPreview === 'input'
                    ? 'Collapse input preview'
                    : 'Expand input preview'
                    " @click="togglePreviewExpansion('input')">
                    <span class="material-symbols-outlined" aria-hidden="true">
                      {{
                        expandedPreview === 'input' ? materialIcons.collapse : materialIcons.expand
                      }}
                    </span>
                  </button>
                </header>
                <div class="preview-surface">
                  <div v-if="stagePreviewRecord?.input_preview" class="mask-preview-frame"
                    :class="{ editable: canDraftMask }">
                    <img ref="maskPreviewImage" :src="stagePreviewRecord.input_preview" alt="Stage input preview"
                      @click="handleMaskPreviewClick" @dblclick="handleMaskPreviewDoubleClick" />
                    <svg v-if="maskFrameWidth > 0 && maskFrameHeight > 0" class="mask-overlay"
                      :viewBox="`0 0 ${maskFrameWidth} ${maskFrameHeight}`" preserveAspectRatio="none"
                      aria-hidden="true">
                      <polygon v-for="(polygon, index) in maskPolygons" :key="`mask-${index}`"
                        :points="maskPolygonPoints(polygon)" class="mask-polygon" />
                      <template v-for="(polygon, polygonIndex) in maskPolygons" :key="`points-${polygonIndex}`">
                        <circle v-for="(point, pointIndex) in polygon" :key="`point-${polygonIndex}-${pointIndex}`"
                          :cx="point.x" :cy="point.y" :r="Math.max(3, Math.round(maskFrameWidth / 160))"
                          class="mask-polygon-point" />
                      </template>
                      <polygon v-if="hasMaskDraftArea" :points="maskPolygonPoints(maskDraftPolygon)"
                        class="mask-draft-polygon" />
                      <polyline v-if="maskDraftPolygon.length > 0" :points="maskPolygonPoints(maskDraftPolygon)"
                        class="mask-draft-line" />
                      <circle v-for="(point, index) in maskDraftPolygon" :key="`draft-${index}`" :cx="point.x"
                        :cy="point.y" :r="Math.max(3, Math.round(maskFrameWidth / 160))" class="mask-draft-point" />
                    </svg>
                  </div>
                  <span v-else>No input preview available</span>
                  <footer>
                    <span>Input {{ stagePreviewRecord?.input_shape ?? [] }}</span>
                  </footer>
                </div>
              </article>

              <article class="stage-preview-pane" :class="{ expanded: expandedPreview === 'output' }">
                <header>
                  <strong>Exiting Stage</strong>
                  <button :disabled="!stagePreviewRecord?.output_preview" :title="expandedPreview === 'output'
                    ? 'Collapse output preview'
                    : 'Expand output preview'
                    " @click="togglePreviewExpansion('output')">
                    <span class="material-symbols-outlined" aria-hidden="true">
                      {{
                        expandedPreview === 'output' ? materialIcons.collapse : materialIcons.expand
                      }}
                    </span>
                  </button>
                </header>
                <div class="preview-surface">
                  <img v-if="stagePreviewRecord?.output_preview" :src="stagePreviewRecord.output_preview"
                    alt="Stage output preview" />
                  <span v-else>No output preview available</span>
                  <footer>
                    <span>Output {{ stagePreviewRecord?.output_shape ?? [] }}</span>
                  </footer>
                </div>
              </article>
            </div>
          </section>

        </section>
      </section>
    </main>
  </div>
</template>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(body) {
  margin: 0;
  font-family:
    Inter,
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
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

button:disabled {
  border-color: #cbd5df;
  background: #eef2f6;
  color: #718096;
  cursor: not-allowed;
  opacity: 0.55;
}

button:disabled .material-symbols-outlined {
  opacity: 0.75;
}

.app-layout {
  display: grid;
  min-height: 100vh;
  grid-template-columns: 220px minmax(0, 1fr);
}

.app-sidebar {
  display: flex;
  position: sticky;
  top: 0;
  flex-direction: column;
  gap: 20px;
  height: 100vh;
  border-right: 1px solid #304157;
  padding: 20px 16px;
  background: #111b28;
  color: #f7fafc;
}

.app-brand {
  font-size: 18px;
  font-weight: 700;
}

.app-content {
  min-width: 0;
}

.shell {
  min-height: 100vh;
  background: #f4f6f8;
}

.vscode-header a,
.vscode-header button,
.log-actions button {
  border: 1px solid #506070;
  border-radius: 6px;
  padding: 8px 10px;
  background: #223044;
  color: #f7fafc;
  text-decoration: none;
  font-size: 13px;
  cursor: pointer;
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
.field.light textarea {
  width: 100%;
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 8px;
  background: #ffffff;
  color: #1f2933;
}

.field textarea {
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
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

.pipeline-integrity {
  display: grid;
  gap: 6px;
  border: 1px solid #b45309;
  border-radius: 6px;
  padding: 10px;
  background: #fffbeb;
  color: #78350f;
  font-size: 13px;
}

.pipeline-integrity span {
  overflow-wrap: anywhere;
}

.workspace-integrity {
  display: grid;
  gap: 6px;
  border: 1px solid #b45309;
  border-radius: 8px;
  padding: 12px;
  background: #fffbeb;
  color: #78350f;
  font-size: 14px;
}

.workspace-integrity span {
  overflow-wrap: anywhere;
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

.tree-panel .material-symbols-outlined,
.tree-row .material-symbols-outlined,
.pipeline-ribbon .material-symbols-outlined {
  width: 16px;
  overflow: hidden;
  height: 16px;
  font-size: 16px;
  font-variation-settings:
    'FILL' 0,
    'wght' 400,
    'GRAD' 0,
    'opsz' 20;
  line-height: 1;
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

.refresh-button {
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 8px 10px;
  background: #ffffff;
  color: #1f2933;
  cursor: pointer;
}

.pipeline-ribbon {
  display: grid;
  gap: 12px;
  border: 1px solid #d7dee7;
  border-radius: 8px;
  padding: 8px;
  background: #ffffff;
}

.ribbon-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}

.ribbon-group button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 7px 10px;
  background: #ffffff;
  color: #1f2933;
  cursor: pointer;
  font-size: 13px;
}

.debugger-selectors {
  justify-content: flex-start;
}

.breakpoint-ribbon {
  justify-content: flex-end;
}

.ribbon-field {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #394b5f;
  font-size: 13px;
}

.ribbon-field select {
  min-width: 220px;
  max-width: 320px;
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 7px 8px;
  background: #ffffff;
  color: #1f2933;
}

.workspace {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.statusbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  border-bottom: 1px solid #d7dee7;
  padding-bottom: 10px;
  font-size: 14px;
}

.workspace-message {
  margin: 0;
  border-radius: 6px;
  padding: 10px 12px;
  background: #18222f;
  font-size: 13px;
}

.stage-preview header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
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

.editor-header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.editor-actions button,
.editor-panel button {
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 8px 10px;
  background: #ffffff;
  color: #1f2933;
  cursor: pointer;
}

.editor-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
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

.mask-controls {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.stage-preview {
  display: grid;
  gap: 10px;
  min-height: 0;
  border: 1px solid #d7dee7;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
}

.stage-preview-header {
  align-items: center;
  color: #394b5f;
}

.stage-preview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(260px, 1fr));
  gap: 12px;
}

.stage-preview-pane {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 8px;
  min-width: 0;
}

.stage-preview-pane header {
  align-items: center;
}

.stage-preview-pane header button {
  display: inline-grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  background: #ffffff;
  color: #1f2933;
  cursor: pointer;
}

.stage-preview-pane .material-symbols-outlined {
  width: 18px;
  overflow: hidden;
  height: 18px;
  font-size: 18px;
  font-variation-settings:
    'FILL' 0,
    'wght' 400,
    'GRAD' 0,
    'opsz' 20;
  line-height: 1;
}

.stage-preview-pane.expanded {
  position: fixed;
  z-index: 20;
  inset: 0;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  padding: 16px;
  background: #0f172a;
  color: #f8fafc;
}

.stage-preview-pane.expanded header {
  min-height: 40px;
}

.stage-preview-pane.expanded header button {
  border-color: #506070;
  background: #18222f;
  color: #f8fafc;
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

.stage-preview-pane.expanded .preview-surface {
  min-height: 0;
  width: 100%;
  height: 100%;
  border-color: #334155;
  background: #020617;
  color: #cbd5e1;
}

.mask-preview-frame {
  position: relative;
  display: inline-grid;
  max-width: 100%;
  max-height: 100%;
}

.mask-preview-frame.editable img {
  cursor: crosshair;
}

.preview-surface img {
  display: block;
  max-width: 100%;
  max-height: 360px;
  object-fit: contain;
}

.stage-preview-pane.expanded .preview-surface img {
  width: 100%;
  height: 100%;
  max-height: none;
}

.stage-preview-pane.expanded .mask-preview-frame {
  width: 100%;
  height: 100%;
}

.mask-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.mask-polygon {
  fill: rgb(0 0 0 / 30%);
  stroke: #f59e0b;
  stroke-width: 3;
  vector-effect: non-scaling-stroke;
}

.mask-draft-polygon {
  fill: rgb(0 0 0 / 30%);
  stroke: none;
}

.mask-draft-line {
  fill: none;
  stroke: #38bdf8;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.mask-polygon-point,
.mask-draft-point {
  fill: #38bdf8;
  stroke: #0f172a;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.preview-surface footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
  font-size: 12px;
}

@media (max-width: 900px) {
  .stage-preview-grid {
    grid-template-columns: 1fr;
  }
}

.error {
  color: #fecaca;
}

.status {
  color: #bbf7d0;
}

.vscode-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 100vh;
  background: #101820;
}

.vscode-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid #304157;
  padding: 12px 16px;
  background: #18222f;
  color: #f7fafc;
}

.vscode-header>div:first-child {
  display: grid;
  gap: 2px;
}

.vscode-header span {
  color: #cbd5df;
  font-size: 13px;
}

.vscode-actions,
.log-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.vscode-message {
  position: absolute;
  z-index: 2;
  inset: 12px auto auto 12px;
  margin: 0;
  border-radius: 6px;
  padding: 8px 16px;
  font-size: 13px;
  background: #18222f;
}

.vscode-stage {
  position: relative;
  display: grid;
  min-height: 0;
}

.vscode-frame {
  display: block;
  width: 100%;
  min-height: 0;
  height: 100%;
  border: 0;
  background: #1e1e1e;
}

.vscode-error {
  position: absolute;
  inset: 16px auto auto 16px;
  display: grid;
  gap: 4px;
  max-width: min(520px, calc(100% - 32px));
  border: 1px solid #b45309;
  border-radius: 8px;
  padding: 12px;
  background: #fffbeb;
  color: #78350f;
  box-shadow: 0 12px 24px rgb(15 23 42 / 18%);
}

.vscode-error span {
  font-size: 13px;
}

.log-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 100vh;
  background: #f4f6f8;
}

.log-workspace {
  display: grid;
  align-content: start;
  gap: 12px;
  min-height: 0;
  padding: 18px;
}

.log-error {
  margin: 0;
  border: 1px solid #fecaca;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fef2f2;
  color: #991b1b;
}

.log-filter {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin: 0;
  border: 0;
  padding: 0;
  color: #cbd5df;
  font-size: 13px;
}

.log-filter legend {
  padding: 0;
  color: #cbd5df;
}

.log-filter label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.log-table {
  display: grid;
  min-width: 0;
  overflow: auto;
  border: 1px solid #d7dee7;
  border-radius: 8px;
  background: #ffffff;
}

.log-row {
  display: grid;
  grid-template-columns: 180px 110px minmax(360px, 1fr);
  min-width: 720px;
  border-bottom: 1px solid #e5eaf0;
}

.log-row:last-child {
  border-bottom: 0;
}

.log-row span {
  min-width: 0;
  padding: 10px 12px;
  font-size: 13px;
}

.log-heading {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #eef2f6;
  color: #394b5f;
  font-weight: 700;
}

.log-time,
.log-level {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
}

.log-level {
  font-weight: 700;
}

.level-error,
.level-critical {
  color: #b91c1c;
}

.level-warning {
  color: #a16207;
}

.level-info {
  color: #1d4ed8;
}

.log-description {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.log-empty {
  padding: 18px;
  color: #627386;
  font-size: 14px;
}

@media (max-width: 820px) {

  .app-layout,
  .shell,
  .editor-grid {
    grid-template-columns: 1fr;
  }

  .app-sidebar {
    position: static;
    height: auto;
  }

  .pipeline-ribbon {
    align-items: stretch;
    flex-direction: column;
  }

  .breakpoint-ribbon {
    justify-content: flex-start;
  }

  .ribbon-field {
    align-items: stretch;
    flex-direction: column;
  }

  .ribbon-field select {
    width: 100%;
    max-width: none;
  }

  .vscode-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
