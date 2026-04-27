<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MainNavBar from './components/MainNavBar.vue'
import PipelineFileTree from './components/PipelineFileTree.vue'

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

type PipelineFileTreeNode = {
  type: 'directory' | 'file'
  name: string
  path: string
  children: PipelineFileTreeNode[]
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
  integrity?: PipelineIntegrity
  frame_interval_seconds: number | string | null
  selected_pipeline_config_path?: string
  pipeline_file_tree?: PipelineFileTreeNode[]
  pipelines: Pipeline[]
  edges: Edge[]
}

type LogEntry = {
  timestamp: string
  level: string
  description: string
}

type LogSeverity = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

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
} as const

const cameras = ref<Camera[]>([])
const defaultPipelineFrameIntervalSeconds = 0.5
const selectedCameraId = ref('')
const pipelines = ref<Pipeline[]>([])
const edges = ref<Edge[]>([])
const debugState = ref<DebugState>({ status: 'idle', records: [] })
const metadata = ref<Record<string, unknown>>({})
const selectedBreakpoint = ref('')
const apiError = ref('')
const isLoadingCameras = ref(false)
const pipelineConfigEnabled = ref(true)
const pipelineConfigFrameIntervalSeconds = ref(String(defaultPipelineFrameIntervalSeconds))
const pipelineConfigPipelines = ref<Pipeline[]>([])
const pipelineConfigEdges = ref<Edge[]>([])
const pipelineFileTree = ref<PipelineFileTreeNode[]>([])
const selectedPipelineConfigPath = ref('')
const pipelineIntegrity = ref<PipelineIntegrity>({ ok: true, issues: [] })
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

const latestRecord = computed(() => debugState.value.records?.at(-1))
const hasPipelineIntegrityProblem = computed(() => !pipelineIntegrity.value.ok)

const filteredLogEntries = computed(() => {
  const selectedLevels = new Set(selectedLogSeverities.value)
  return logEntries.value.filter((entry) => selectedLevels.has(entry.level as LogSeverity))
})

const visiblePipelines = computed(() => {
  if (!debugPipelineId.value) return pipelines.value
  return pipelines.value.filter((pipeline) => pipeline.id === debugPipelineId.value)
})

const selectedPipelinesPipeline = computed(() =>
  pipelineConfigPipelines.value.find((pipeline) => pipeline.id === selectedPipelineId.value),
)

const selectedPipelinesStage = computed(() =>
  selectedPipelinesPipeline.value?.stages.find((stage) => stage.id === selectedStageId.value),
)

const isActionBusy = computed(() => currentAction.value.length > 0)
const hasSelectedCamera = computed(() => selectedCameraId.value.length > 0)
const hasPipelinesPipeline = computed(() => Boolean(selectedPipelinesPipeline.value))
const hasPipelinesStage = computed(() => Boolean(selectedPipelinesStage.value))
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
const canApplyPipeline = computed(() => canEditPipelines.value && hasPipelinesPipeline.value)
const canApplyStage = computed(() => canEditPipelines.value && hasPipelinesStage.value)
const canAddEdge = computed(
  () => canEditPipelines.value && pipelineConfigPipelines.value.length >= 2,
)
const canSetBreakpoint = computed(
  () =>
    hasSelectedCamera.value &&
    !hasPipelineIntegrityProblem.value &&
    selectedBreakpoint.value.length > 0 &&
    !isRunLoopActive.value &&
    !isActionBusy.value,
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
  const pathQuery = pipelineConfigPathQuery()
  const graph = await getJson<{
    pipelines: Pipeline[]
    edges: Edge[]
    integrity?: PipelineIntegrity
  }>(
    `/api/pipelines?camera_id=${encodeURIComponent(selectedCameraId.value)}${pathQuery}`,
  )
  applyPipelineGraph(graph)
}

function applyPipelineGraph(graph: {
  pipelines: Pipeline[]
  edges: Edge[]
  integrity?: PipelineIntegrity
}) {
  pipelines.value = graph.pipelines
  edges.value = graph.edges
  pipelineIntegrity.value = graph.integrity ?? { ok: true, issues: [] }
}

async function loadPipelineConfigPipelines() {
  const graph = await getJson<PipelinesResponse>('/api/pipeline_config/pipelines')
  pipelineConfigEnabled.value = graph.enabled
  pipelineConfigFrameIntervalSeconds.value = String(
    graph.frame_interval_seconds ?? defaultPipelineFrameIntervalSeconds,
  )
  pipelineIntegrity.value = graph.integrity ?? { ok: true, issues: [] }
  pipelineFileTree.value = graph.pipeline_file_tree ?? []
  pipelineConfigPipelines.value = graph.pipelines
  pipelineConfigEdges.value = graph.edges
  if (!selectedPipelineId.value && pipelineConfigPipelines.value[0]) {
    selectPipeline(pipelineConfigPipelines.value[0].id)
  } else {
    refreshSelectedEditors()
  }
}

async function reloadPipelines() {
  await stopRunLoop(false)
  await postJson<{ pipelines: Pipeline[]; edges: Edge[]; integrity?: PipelineIntegrity }>(
    '/api/pipelines/reload',
    {},
  )
  await loadPipelines()
  await loadPipelineConfigPipelines()
  await loadDebugState()
  deployStatus.value = 'Pipelines reloaded'
}

async function loadDebugState() {
  if (!selectedCameraId.value) return
  const pathQuery = pipelineConfigPathQuery()
  debugState.value = await getJson<DebugState>(
    `/api/debug/state?camera_id=${encodeURIComponent(selectedCameraId.value)}${pathQuery}`,
  )
  const payload = await getJson<{ metadata: Record<string, unknown> }>(
    `/api/debug/metadata?camera_id=${encodeURIComponent(selectedCameraId.value)}${pathQuery}`,
  )
  metadata.value = payload.metadata
}

async function loadLogs() {
  isLoadingLogs.value = true
  try {
    const payload = await getJson<{ entries: LogEntry[] }>('/api/logs?limit=500')
    logEntries.value = payload.entries
  } finally {
    isLoadingLogs.value = false
  }
}

async function clearLogs() {
  const payload = await postJson<{ entries: LogEntry[] }>('/api/logs/clear', {})
  logEntries.value = payload.entries
}

async function runCommand(command: string) {
  if (!selectedCameraId.value) return
  debugState.value = await postJson<DebugState>('/api/debug/command', {
    camera_id: selectedCameraId.value,
    pipeline_config_path: selectedPipelineConfigPath.value,
    command,
  })
  await loadDebugState()
}

async function runDebuggerCommand(command: string) {
  if (isActionBusy.value) return
  await withAction(command, () => runCommand(command))
}

async function stopDebuggerRun() {
  if (!canStop.value) return
  await withAction('stop', () => stopRunLoop())
}

async function startRunLoop() {
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

async function runLoopTick() {
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

async function stopRunLoop(sendPause = true) {
  isRunLoopActive.value = false
  if (runLoopTimer.value) {
    clearInterval(runLoopTimer.value)
    runLoopTimer.value = null
  }
  if (sendPause && selectedCameraId.value) {
    await runCommand('pause').catch(() => undefined)
  }
}

async function toggleBreakpoint(enabled: boolean) {
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

async function refreshCamera() {
  await stopRunLoop(false)
  try {
    selectedPipelineConfigPath.value = ''
    showPipelineIndex()
    await loadPipelines()
    await loadDebugState()
    await loadPipelineConfigPipelines()
  } catch {
    return
  }
}

async function savePipelineConfigPipelines() {
  deployStatus.value = ''
  const validationError = validatePipelinesPipelineReferences()
  if (validationError) {
    apiError.value = validationError
    return
  }
  const saved = await postJson<PipelinesResponse>(
    '/api/pipeline_config/pipelines',
    toPipelinesPayload(),
  )
  pipelineConfigPipelines.value = saved.pipelines
  pipelineConfigEdges.value = saved.edges
  pipelineFileTree.value = saved.pipeline_file_tree ?? pipelineFileTree.value
  refreshSelectedEditors()
  deployStatus.value = 'Pipelines saved'
}

async function withAction<T>(action: string, task: () => Promise<T>): Promise<T | undefined> {
  if (isActionBusy.value) return undefined
  currentAction.value = action
  try {
    return await task()
  } finally {
    currentAction.value = ''
  }
}

async function deployPipelineConfigPipelines() {
  await savePipelineConfigPipelines()
  const deployed = await postJson<PipelinesResponse>('/api/pipeline_config/pipelines/deploy', {})
  pipelines.value = deployed.pipelines
  edges.value = deployed.edges
  pipelineFileTree.value = deployed.pipeline_file_tree ?? pipelineFileTree.value
  await loadDebugState()
  deployStatus.value = 'Pipelines deployed and server config reloaded'
}

async function generateExampleResizePipeline() {
  const generated = await postJson<PipelinesResponse>('/api/pipelines/examples/resize', {})
  pipelineConfigEnabled.value = generated.enabled
  pipelineConfigFrameIntervalSeconds.value = String(
    generated.frame_interval_seconds ?? defaultPipelineFrameIntervalSeconds,
  )
  pipelineFileTree.value = generated.pipeline_file_tree ?? []
  pipelineConfigPipelines.value = generated.pipelines
  pipelineConfigEdges.value = generated.edges
  selectPipeline('example-resize')
  deployStatus.value =
    'Example resize pipeline generated. Use Debugger to run it, or deploy pipelines when ready.'
}

async function deployPipelinesFromEditor() {
  const deployed = await postJson<PipelinesResponse>('/api/pipeline_config/pipelines/deploy', {})
  pipelines.value = deployed.pipelines
  edges.value = deployed.edges
  pipelineFileTree.value = deployed.pipeline_file_tree ?? pipelineFileTree.value
  deployStatus.value = 'Pipelines deployed and server config reloaded'
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
    apiError.value = await responseErrorMessage(response)
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
    apiError.value = await responseErrorMessage(response)
    throw new Error(apiError.value)
  }
  return response.json() as Promise<T>
}

async function responseErrorMessage(response: Response) {
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

function formatJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

function addPipeline() {
  const baseId = uniqueId(
    'pipeline',
    pipelineConfigPipelines.value.map((pipeline) => pipeline.id),
  )
  pipelineConfigPipelines.value.push({
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
  pipelineConfigPipelines.value = pipelineConfigPipelines.value.filter(
    (pipeline) => pipeline.id !== pipelineId,
  )
  pipelineConfigEdges.value = pipelineConfigEdges.value.filter(
    (edge) => edge.from !== pipelineId && edge.to !== pipelineId,
  )
  selectedPipelineId.value = pipelineConfigPipelines.value[0]?.id ?? ''
  selectedStageId.value = ''
  if (debugPipelineId.value === pipelineId) {
    showPipelineIndex()
  }
  refreshSelectedEditors()
}

function addStage() {
  if (!selectedPipelinesPipeline.value) return
  const baseId = uniqueId(
    'stage',
    selectedPipelinesPipeline.value.stages.map((stage) => stage.id),
  )
  selectedPipelinesPipeline.value.stages.push({
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
  const pipeline = pipelineConfigPipelines.value.find((candidate) => candidate.id === pipelineId)
  if (!pipeline || !stageId) return
  pipeline.stages = pipeline.stages.filter((stage) => stage.id !== stageId)
  if (selectedPipelineId.value === pipelineId && selectedStageId.value === stageId) {
    selectedStageId.value = pipeline.stages[0]?.id ?? ''
  }
  refreshSelectedEditors()
}

function selectPipeline(pipelineId: string) {
  selectedPipelineId.value = pipelineId
  selectedStageId.value = selectedPipelinesPipeline.value?.stages[0]?.id ?? ''
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
  const pipeline = selectedPipelinesPipeline.value
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
  for (const edge of pipelineConfigEdges.value) {
    if (edge.from === oldId) edge.from = nextId
    if (edge.to === oldId) edge.to = nextId
  }
  selectedPipelineId.value = nextId
}

async function applyStageEdits() {
  if (isActionBusy.value) return
  const stage = selectedPipelinesStage.value
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
  currentAction.value = 'apply_stage'
  try {
    await stopRunLoop(false)
    await savePipelineConfigPipelines()
    await loadPipelines()
    if (selectedCameraId.value && !hasPipelineIntegrityProblem.value) {
      await runCommand('run')
    } else {
      await loadDebugState()
    }
    deployStatus.value = 'Stage applied and debugger refreshed'
  } finally {
    currentAction.value = ''
  }
}

function addEdge() {
  if (pipelineConfigPipelines.value.length < 2) return
  const sourcePipeline = pipelineConfigPipelines.value[0]
  const targetPipeline = pipelineConfigPipelines.value[1]
  if (!sourcePipeline || !targetPipeline) return
  const from = sourcePipeline.id
  const to = targetPipeline.id
  pipelineConfigEdges.value.push({ from, to })
}

function deleteEdge(index: number) {
  pipelineConfigEdges.value.splice(index, 1)
}

function refreshSelectedEditors() {
  const pipeline = selectedPipelinesPipeline.value
  selectedPipelineIdEdit.value = pipeline?.id ?? ''
  selectedPipelineNameEdit.value = pipeline?.name ?? ''
  selectedPipelineRequiredInputs.value = pipeline?.required_inputs.join(', ') ?? ''
  const stage = selectedPipelinesStage.value
  selectedStageIdEdit.value = stage?.id ?? ''
  selectedStageModule.value = stage?.module ?? ''
  selectedStageClassName.value = stage?.class_name ?? ''
  selectedStageFilename.value = stage?.filename ?? ''
  selectedStagePipeline.value = stage?.pipeline ?? ''
  selectedStageConfigJson.value = formatJson(stage?.config ?? {})
}

function toPipelinesPayload() {
  const interval = Number(pipelineConfigFrameIntervalSeconds.value)
  return {
    enabled: pipelineConfigEnabled.value,
    frame_interval_seconds: Number.isFinite(interval)
      ? interval
      : pipelineConfigFrameIntervalSeconds.value,
    pipelines: pipelineConfigPipelines.value.map((pipeline) => ({
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
    edges: pipelineConfigEdges.value,
  }
}

function stageSummary(stage: Stage) {
  if (stage.pipeline) return `pipeline: ${stage.pipeline}`
  if (stage.filename) return stage.filename
  return stage.class_name || stage.module || 'stage'
}

function openPipelineDebug(pipelineId: string) {
  if (hasPipelineIntegrityProblem.value) return
  debugPipelineId.value = pipelineId
  selectedPipelineId.value = pipelineId
  currentView.value = 'debug'
  refreshSelectedEditors()
}

function openStageDebug(pipelineId: string, stageId: string) {
  if (hasPipelineIntegrityProblem.value) return
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

async function openPipelineConfigFile(path: string) {
  if (!isYamlPath(path)) return
  await stopRunLoop(false)
  selectedPipelineConfigPath.value = path === 'pipelines.yaml' ? '' : path
  showPipelineIndex()
  await loadPipelines()
  await loadDebugState()
}

function pipelineConfigPathQuery() {
  if (!selectedPipelineConfigPath.value) return ''
  return `&pipeline_config_path=${encodeURIComponent(selectedPipelineConfigPath.value)}`
}

function isYamlPath(path: string) {
  return /\.(ya?ml)$/i.test(path)
}

function startLogRefresh() {
  if (logRefreshTimer.value) return
  loadLogs().catch(() => undefined)
  logRefreshTimer.value = setInterval(() => {
    loadLogs().catch(() => undefined)
  }, 3000)
}

function stopLogRefresh() {
  if (!logRefreshTimer.value) return
  clearInterval(logRefreshTimer.value)
  logRefreshTimer.value = null
}

function validatePipelinesPipelineReferences() {
  const pipelineIds = new Set(pipelineConfigPipelines.value.map((pipeline) => pipeline.id))
  const downstream = new Map<string, string[]>()
  for (const pipeline of pipelineConfigPipelines.value) {
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

  for (const pipeline of pipelineConfigPipelines.value) {
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
            <button
              :disabled="!canEditPipelines"
              @click="withAction('example_resize', generateExampleResizePipeline)"
            >
              Example Resize
            </button>
            <button
              :disabled="!canEditPipelines"
              @click="withAction('deploy_pipelines', deployPipelinesFromEditor)"
            >
              Deploy Pipelines
            </button>
            <a :href="vscodeWebUrl" target="_blank" rel="noreferrer">Open</a>
          </div>
        </header>
        <section class="vscode-stage">
          <p v-if="apiError" class="vscode-message error">{{ apiError }}</p>
          <p v-if="deployStatus" class="vscode-message status">{{ deployStatus }}</p>
          <iframe
            class="vscode-frame"
            :src="vscodeWebUrl"
            title="VS Code Web editor"
            allow="clipboard-read; clipboard-write"
            @load="vscodeLoadFailed = false"
            @error="vscodeLoadFailed = true"
          ></iframe>
          <div v-if="vscodeLoadFailed" class="vscode-error">
            <strong>VS Code Web is not available.</strong>
            <span
              >Start it with code serve-web --host 127.0.0.1 --port 8000 --without-connection-token
              --accept-server-license-terms --default-folder /home/dad/nvr/pipeline_config, then
              reload this view.</span
            >
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
            <div
              v-for="(entry, index) in filteredLogEntries"
              :key="`${entry.timestamp}-${index}`"
              class="log-row"
              role="row"
            >
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
          <button
            class="refresh-button"
            :disabled="isActionBusy || isRunLoopActive"
            @click="withAction('refresh_cameras', () => loadCameras().then(refreshCamera))"
          >
            Refresh Cameras
          </button>
          <div class="camera-state">
            <span>{{ selectedCamera?.enabled ? 'Recorder enabled' : 'Recorder disabled' }}</span>
            <span>{{
              selectedCamera?.pipeline_enabled ? 'Pipeline enabled' : 'Pipeline disabled'
            }}</span>
          </div>
          <section v-if="hasPipelineIntegrityProblem" class="pipeline-integrity">
            <strong>Pipeline integrity problem</strong>
            <span v-for="(issue, index) in pipelineIntegrity.issues" :key="index">
              {{ issue.message }}
            </span>
          </section>

          <section class="tree-panel">
            <header>
              <strong>Pipeline Tree</strong>
              <button
                title="Add pipeline"
                :disabled="!canEditPipelines"
                @click="addPipelineFromTree"
              >
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.plus }}
                </span>
              </button>
            </header>
            <div class="tree">
              <div
                v-if="pipelineFileTree.length === 0 && pipelineConfigPipelines.length === 0"
                class="tree-empty"
              >
                No pipelines
              </div>
              <PipelineFileTree
                v-if="pipelineFileTree.length > 0"
                :nodes="pipelineFileTree"
                @open-yaml="openPipelineConfigFile"
              />
              <div
                v-for="pipeline in pipelineConfigPipelines"
                :key="pipeline.id"
                class="tree-branch"
              >
                <div
                  class="tree-row"
                  :class="{ selected: pipeline.id === selectedPipelineId && !selectedStageId }"
                  @click="selectPipeline(pipeline.id)"
                  @dblclick="openPipelineDebug(pipeline.id)"
                >
                  <span class="tree-icon">
                    <span class="material-symbols-outlined" aria-hidden="true">
                      {{ materialIcons.pipeline }}
                    </span>
                  </span>
                  <span class="tree-label">{{ pipeline.name || pipeline.id }}</span>
                  <button
                    title="Add stage"
                    :disabled="!canEditPipelines"
                    @click.stop="addStageToPipeline(pipeline.id)"
                  >
                    <span class="material-symbols-outlined" aria-hidden="true">
                      {{ materialIcons.plus }}
                    </span>
                  </button>
                  <button
                    title="Remove pipeline"
                    :disabled="!canEditPipelines"
                    @click.stop="deletePipeline(pipeline.id)"
                  >
                    <span class="material-symbols-outlined" aria-hidden="true">
                      {{ materialIcons.trash }}
                    </span>
                  </button>
                </div>
                <div class="tree-children">
                  <div
                    v-for="stage in pipeline.stages"
                    :key="stage.id"
                    class="tree-row stage"
                    :class="{
                      selected: pipeline.id === selectedPipelineId && stage.id === selectedStageId,
                    }"
                    @click="selectStageInPipeline(pipeline.id, stage.id)"
                    @dblclick="openStageDebug(pipeline.id, stage.id)"
                  >
                    <span class="tree-icon">
                      <span class="material-symbols-outlined" aria-hidden="true">
                        {{
                          stage.pipeline
                            ? materialIcons.link
                            : stage.filename
                              ? materialIcons.file
                              : materialIcons.stage
                        }}
                      </span>
                    </span>
                    <span class="tree-label">{{ stage.id }}</span>
                    <button
                      title="Remove stage"
                      :disabled="!canEditPipelines"
                      @click.stop="deleteStage(pipeline.id, stage.id)"
                    >
                      <span class="material-symbols-outlined" aria-hidden="true">
                        {{ materialIcons.trash }}
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <p v-if="apiError" class="error">{{ apiError }}</p>
          <p v-if="deployStatus" class="status">{{ deployStatus }}</p>
        </aside>

        <section v-if="currentView === 'index'" class="workspace">
          <section class="pipeline-ribbon" aria-label="Pipeline debugger controls">
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
              <button
                :disabled="!canStep"
                title="Step stage"
                @click="runDebuggerCommand('step_over_stage')"
              >
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.stepStage }}
                </span>
                <span>Step Stage</span>
              </button>
              <button
                :disabled="!canStep"
                title="Step pipeline"
                @click="runDebuggerCommand('step_over_pipeline')"
              >
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
              <button
                :disabled="!canSetBreakpoint"
                title="Set breakpoint"
                @click="toggleBreakpoint(true)"
              >
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.breakpoint }}
                </span>
                <span>Set</span>
              </button>
              <button
                :disabled="!canSetBreakpoint"
                title="Clear breakpoint"
                @click="toggleBreakpoint(false)"
              >
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.clearBreakpoint }}
                </span>
                <span>Clear</span>
              </button>
            </div>
          </section>

          <header class="statusbar">
            <span>Pipelines</span>
            <span>{{ pipelines.length }} configured</span>
          </header>

          <section v-if="hasPipelineIntegrityProblem" class="workspace-integrity">
            <strong>Pipeline integrity problem</strong>
            <span v-for="(issue, index) in pipelineIntegrity.issues" :key="index">
              {{ issue.message }}
            </span>
          </section>

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
              <div class="pipeline-card-actions">
                <button
                  :disabled="hasPipelineIntegrityProblem"
                  @click="openPipelineDebug(pipeline.id)"
                >
                  View
                </button>
                <button
                  :disabled="isActionBusy"
                  @click="withAction('reload_pipelines', reloadPipelines)"
                >
                  Reload
                </button>
              </div>
            </article>
          </section>
        </section>

        <section v-else class="workspace">
          <section class="pipeline-ribbon" aria-label="Pipeline debugger controls">
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
              <button
                :disabled="!canStep"
                title="Step stage"
                @click="runDebuggerCommand('step_over_stage')"
              >
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.stepStage }}
                </span>
                <span>Step Stage</span>
              </button>
              <button
                :disabled="!canStep"
                title="Step pipeline"
                @click="runDebuggerCommand('step_over_pipeline')"
              >
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
              <button
                :disabled="!canSetBreakpoint"
                title="Set breakpoint"
                @click="toggleBreakpoint(true)"
              >
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.breakpoint }}
                </span>
                <span>Set</span>
              </button>
              <button
                :disabled="!canSetBreakpoint"
                title="Clear breakpoint"
                @click="toggleBreakpoint(false)"
              >
                <span class="material-symbols-outlined" aria-hidden="true">
                  {{ materialIcons.clearBreakpoint }}
                </span>
                <span>Clear</span>
              </button>
            </div>
          </section>

          <header class="statusbar">
            <button @click="showPipelineIndex">Pipelines</button>
            <span v-if="hasPipelineIntegrityProblem"
              >Debugging blocked: pipeline integrity problem</span
            >
            <span v-else>Status: {{ debugState.status }}</span>
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
              <strong>Pipeline Configuration</strong>
              <div class="editor-actions">
                <button
                  :disabled="!canEditPipelines"
                  @click="withAction('reload_pipelines', loadPipelineConfigPipelines)"
                >
                  Reload Pipelines
                </button>
                <button
                  :disabled="!canEditPipelines"
                  @click="withAction('save_pipelines', savePipelineConfigPipelines)"
                >
                  Save Pipelines
                </button>
                <button
                  :disabled="!canEditPipelines"
                  @click="withAction('deploy_pipelines', deployPipelineConfigPipelines)"
                >
                  Deploy
                </button>
              </div>
            </header>

            <div class="editor-grid">
              <section class="editor-panel">
                <header>
                  <strong>Pipelines</strong>
                  <button :disabled="!canEditPipelines" @click="addPipeline">Add</button>
                </header>
                <label class="inline-field">
                  <span>Enabled</span>
                  <input v-model="pipelineConfigEnabled" type="checkbox" />
                </label>
                <label class="field light">
                  <span>Frame interval seconds</span>
                  <input
                    v-model="pipelineConfigFrameIntervalSeconds"
                    type="text"
                    inputmode="decimal"
                  />
                </label>
                <button
                  v-for="pipeline in pipelineConfigPipelines"
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
                  <button :disabled="!canApplyPipeline" @click="deleteSelectedPipeline">
                    Delete
                  </button>
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
                  <input
                    v-if="selectedPipelinesPipeline"
                    v-model="selectedPipelinesPipeline.enabled"
                    type="checkbox"
                  />
                </label>
                <label class="field light">
                  <span>Required inputs</span>
                  <input v-model="selectedPipelineRequiredInputs" type="text" />
                </label>
                <button :disabled="!canApplyPipeline" @click="applyPipelineEdits">
                  Apply Pipeline
                </button>

                <header>
                  <strong>Stages</strong>
                  <button :disabled="!canApplyPipeline" @click="addStage">Add</button>
                </header>
                <button
                  v-for="stage in selectedPipelinesPipeline?.stages ?? []"
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
                  <button :disabled="!canApplyStage" @click="deleteSelectedStage">Delete</button>
                </header>
                <label class="field light">
                  <span>ID</span>
                  <input v-model="selectedStageIdEdit" type="text" />
                </label>
                <label class="inline-field">
                  <span>Enabled</span>
                  <input
                    v-if="selectedPipelinesStage"
                    v-model="selectedPipelinesStage.enabled"
                    type="checkbox"
                  />
                </label>
                <label class="field light">
                  <span>Filename</span>
                  <input v-model="selectedStageFilename" type="text" />
                </label>
                <label class="field light">
                  <span>Pipeline reference</span>
                  <select v-model="selectedStagePipeline">
                    <option value=""></option>
                    <option
                      v-for="pipeline in pipelineConfigPipelines"
                      :key="pipeline.id"
                      :value="pipeline.id"
                    >
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
                <button :disabled="!canApplyStage" @click="applyStageEdits">Apply Stage</button>
              </section>

              <section class="editor-panel">
                <header>
                  <strong>Edges</strong>
                  <button :disabled="!canAddEdge" @click="addEdge">Add</button>
                </header>
                <div v-for="(edge, index) in pipelineConfigEdges" :key="index" class="edge-row">
                  <select v-model="edge.from">
                    <option
                      v-for="pipeline in pipelineConfigPipelines"
                      :key="pipeline.id"
                      :value="pipeline.id"
                    >
                      {{ pipeline.id }}
                    </option>
                  </select>
                  <select v-model="edge.to">
                    <option
                      v-for="pipeline in pipelineConfigPipelines"
                      :key="pipeline.id"
                      :value="pipeline.id"
                    >
                      {{ pipeline.id }}
                    </option>
                  </select>
                  <button :disabled="!canEditPipelines" @click="deleteEdge(index)">Delete</button>
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

.refresh-button,
.stage-row {
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 8px 10px;
  background: #ffffff;
  color: #1f2933;
  cursor: pointer;
}

.pipeline-ribbon {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
.pipeline-card-actions button {
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

.pipeline-card-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
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

.vscode-header > div:first-child {
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
  .details,
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
