import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  ALLOW_POLYGONS_FEATURE,
  DEFAULT_PIPELINE_FRAME_INTERVAL_SECONDS,
  DEFAULT_VSCODE_WEB_URL,
  LOG_SEVERITY_OPTIONS,
  MATERIAL_ICONS,
} from '@/constants/app'
import { nvrApi } from '@/services/nvrApi'
import type {
  Camera,
  DebugRecord,
  DebugState,
  LogEntry,
  LogSeverity,
  MaskConfig,
  MaskPoint,
  Pipeline,
  PipelineIntegrity,
} from '@/types/nvr'

const cameras = ref<Camera[]>([])
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
const selectedLogSeverities = ref<LogSeverity[]>([...LOG_SEVERITY_OPTIONS])
const isLoadingLogs = ref(false)
const logRefreshTimer = ref<ReturnType<typeof setInterval> | null>(null)
const vscodeLoadFailed = ref(false)
const runLoopTimer = ref<ReturnType<typeof setInterval> | null>(null)
const isRunLoopActive = ref(false)
const isRunLoopTicking = ref(false)
const currentAction = ref('')
const maskPreviewImage = ref<HTMLImageElement | null>(null)
const maskDraftPolygon = ref<MaskPoint[]>([])
const expandedPreview = ref<'input' | 'output' | null>(null)
const ignoreNextMaskClick = ref(false)
const vscodeWebUrl = computed(() => import.meta.env.VITE_VSCODE_WEB_URL || DEFAULT_VSCODE_WEB_URL)
let isLifecycleMounted = false

export const useNvrAppState = () => {
  const route = useRoute()
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
    return stage.features?.includes(ALLOW_POLYGONS_FEATURE) ?? false
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

  const state = {
    cameras,
    selectedCameraId,
    pipelines,
    debugState,
    selectedBreakpoint,
    apiError,
    isLoadingCameras,
    pipelineConfigPipelines,
    selectedPipelineConfigPath,
    pipelineIntegrity,
    debugPipelineId,
    selectedPipelineId,
    selectedStageId,
    selectedStageConfigJson,
    deployStatus,
    logEntries,
    selectedLogSeverities,
    isLoadingLogs,
    vscodeLoadFailed,
    isRunLoopActive,
    currentAction,
    maskPreviewImage,
    maskDraftPolygon,
    expandedPreview,
    vscodeWebUrl,
    isEditorRoute,
    isLogRoute,
    selectedCamera,
    selectedDebugPipeline,
    selectedDebugPipelineStages,
    stagePreviewRecord,
    selectedStagePreviewRecord,
    hasPipelineIntegrityProblem,
    filteredLogEntries,
    isActionBusy,
    canRun,
    canStop,
    canStep,
    canEditPipelines,
    maskFrameWidth,
    maskFrameHeight,
    canDraftMask,
    hasMaskDraftArea,
    maskPolygons,
    canSetBreakpoint,
  }

  const actions = {
    loadCameras,
    loadPipelines,
    loadPipelineConfigPipelines,
    reloadPipelines,
    loadDebugState,
    loadLogs,
    clearLogs,
    runDebuggerCommand,
    stopDebuggerRun,
    startRunLoop,
    toggleBreakpoint,
    refreshCamera,
    withAction,
    generateExampleResizePipeline,
    deployPipelinesFromEditor,
    selectDebugPipeline,
    selectDebugStage,
    handleMaskPreviewClick,
    handleMaskPreviewDoubleClick,
    togglePreviewExpansion,
    maskPolygonPoints,
  }

  if (!isLifecycleMounted) {
    isLifecycleMounted = true
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
      isLifecycleMounted = false
    })
  }

  return { ...state, ...actions, logSeverityOptions: LOG_SEVERITY_OPTIONS, materialIcons: MATERIAL_ICONS }
}

const loadCameras = async (): Promise<void> => {
  isLoadingCameras.value = true
  try {
    apiError.value = ''
    cameras.value = await nvrApi.getCameras()
    const firstCamera = cameras.value[0]
    if (!selectedCameraId.value && firstCamera) {
      selectedCameraId.value = firstCamera.id
    }
  } catch (error) {
    setApiError(error)
    throw error
  } finally {
    isLoadingCameras.value = false
  }
}

const loadPipelines = async (): Promise<void> => {
  if (!selectedCameraId.value) return
  try {
    apiError.value = ''
    applyPipelineGraph(
      await nvrApi.getPipelines(selectedCameraId.value, selectedPipelineConfigPath.value),
    )
  } catch (error) {
    setApiError(error)
    throw error
  }
}

const applyPipelineGraph = (graph: { pipelines: Pipeline[]; integrity?: PipelineIntegrity }): void => {
  pipelines.value = graph.pipelines
  pipelineIntegrity.value = graph.integrity ?? { ok: true, issues: [] }
  syncDebugPipelineSelection()
}

const loadPipelineConfigPipelines = async (): Promise<void> => {
  try {
    apiError.value = ''
    const graph = await nvrApi.getPipelineConfigPipelines()
    pipelineIntegrity.value = graph.integrity ?? { ok: true, issues: [] }
    pipelineConfigPipelines.value = graph.pipelines
    if (!selectedPipelineId.value && pipelineConfigPipelines.value[0]) {
      selectPipeline(pipelineConfigPipelines.value[0].id)
    } else {
      refreshSelectedEditors()
    }
    syncDebugPipelineSelection()
  } catch (error) {
    setApiError(error)
    throw error
  }
}

const reloadPipelines = async (): Promise<void> => {
  await stopRunLoop(false)
  try {
    apiError.value = ''
    await nvrApi.reloadPipelines()
    await loadPipelines()
    await loadPipelineConfigPipelines()
    await loadDebugState()
    deployStatus.value = 'Pipelines reloaded from disk'
  } catch (error) {
    setApiError(error)
    throw error
  }
}

const loadDebugState = async (): Promise<void> => {
  if (!selectedCameraId.value) return
  try {
    apiError.value = ''
    debugState.value = await nvrApi.getDebugState(
      selectedCameraId.value,
      selectedPipelineConfigPath.value,
    )
  } catch (error) {
    setApiError(error)
    throw error
  }
}

const loadLogs = async (): Promise<void> => {
  isLoadingLogs.value = true
  try {
    apiError.value = ''
    logEntries.value = await nvrApi.getLogs()
  } catch (error) {
    setApiError(error)
    throw error
  } finally {
    isLoadingLogs.value = false
  }
}

const clearLogs = async (): Promise<void> => {
  try {
    apiError.value = ''
    logEntries.value = await nvrApi.clearLogs()
  } catch (error) {
    setApiError(error)
    throw error
  }
}

const runCommand = async (command: string): Promise<void> => {
  if (!selectedCameraId.value) return
  try {
    apiError.value = ''
    debugState.value = await nvrApi.runDebugCommand(
      selectedCameraId.value,
      selectedPipelineConfigPath.value,
      command,
    )
    await loadDebugState()
    syncSelectionToLatestDebugRecord()
  } catch (error) {
    setApiError(error)
    throw error
  }
}

const runDebuggerCommand = async (command: string): Promise<void> => {
  if (currentAction.value.length > 0) return
  await withAction(command, () => runCommand(command))
}

const stopDebuggerRun = async (): Promise<void> => {
  if (!isRunLoopActive.value || currentAction.value.length > 0) return
  await withAction('stop', () => stopRunLoop())
}

const startRunLoop = async (): Promise<void> => {
  if (isRunLoopActive.value || currentAction.value.length > 0) return
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
  }, DEFAULT_PIPELINE_FRAME_INTERVAL_SECONDS * 1000)
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
  if (currentAction.value.length > 0 || !selectedCameraId.value || !selectedBreakpoint.value) return
  currentAction.value = enabled ? 'set_breakpoint' : 'clear_breakpoint'
  try {
    apiError.value = ''
    const [pipelineId, stageId] = selectedBreakpoint.value.split(':')
    if (!pipelineId) return
    debugState.value = await nvrApi.setBreakpoint(
      selectedCameraId.value,
      selectedPipelineConfigPath.value,
      pipelineId,
      stageId || null,
      enabled,
    )
  } catch (error) {
    setApiError(error)
    throw error
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

const withAction = async <T>(action: string, task: () => Promise<T>): Promise<T | undefined> => {
  if (currentAction.value.length > 0) return undefined
  currentAction.value = action
  try {
    return await task()
  } finally {
    currentAction.value = ''
  }
}

const generateExampleResizePipeline = async (): Promise<void> => {
  try {
    apiError.value = ''
    const generated = await nvrApi.generateExampleResizePipeline()
    pipelineConfigPipelines.value = generated.pipelines
    selectPipeline('example-resize')
    deployStatus.value =
      'Example resize pipeline generated. Use Debugger to run it, or deploy pipelines when ready.'
  } catch (error) {
    setApiError(error)
    throw error
  }
}

const deployPipelinesFromEditor = async (): Promise<void> => {
  try {
    apiError.value = ''
    const deployed = await nvrApi.deployPipelines()
    pipelines.value = deployed.pipelines
    syncDebugPipelineSelection()
    deployStatus.value = 'Pipelines deployed and server config reloaded'
  } catch (error) {
    setApiError(error)
    throw error
  }
}

const selectPipeline = (pipelineId: string): void => {
  selectedPipelineId.value = pipelineId
  selectedStageId.value =
    pipelineConfigPipelines.value.find((pipeline) => pipeline.id === pipelineId)?.stages[0]?.id ?? ''
  refreshSelectedEditors()
}

const refreshSelectedEditors = (): void => {
  const stage = pipelineConfigPipelines.value
    .find((pipeline) => pipeline.id === selectedPipelineId.value)
    ?.stages.find((candidate) => candidate.id === selectedStageId.value)
  selectedStageConfigJson.value = formatJson(stage?.config ?? {})
  maskDraftPolygon.value = []
}

const selectDebugPipeline = (pipelineId: string): void => {
  if (!pipelineIntegrity.value.ok || !pipelineId) return
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
  if (!pipelineIntegrity.value.ok || pipelines.value.length === 0) {
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
  const shape = selectedStagePreviewShape()
  if (!shape.canDraft) return
  const image = maskPreviewImage.value
  if (!image) return
  const rect = image.getBoundingClientRect()
  const x = Math.round(((event.clientX - rect.left) / rect.width) * shape.width)
  const y = Math.round(((event.clientY - rect.top) / rect.height) * shape.height)
  maskDraftPolygon.value.push({
    x: clamp(x, 0, Math.max(0, shape.width - 1)),
    y: clamp(y, 0, Math.max(0, shape.height - 1)),
  })
}

const togglePreviewExpansion = (preview: 'input' | 'output'): void => {
  expandedPreview.value = expandedPreview.value === preview ? null : preview
}

const updateMaskConfig = (polygons: MaskPoint[][]): void => {
  const config = readMaskConfig()
  config.polygons = polygons
  selectedStageConfigJson.value = formatJson(config)
  const stage = pipelineConfigPipelines.value
    .find((pipeline) => pipeline.id === selectedPipelineId.value)
    ?.stages.find((candidate) => candidate.id === selectedStageId.value)
  if (stage && stage.features?.includes(ALLOW_POLYGONS_FEATURE)) {
    stage.config = config
  }
}

const commitMaskDraftPolygon = (): void => {
  if (polygonArea(maskDraftPolygon.value) <= 0) return
  updateMaskConfig([...readMaskPolygons(), [...maskDraftPolygon.value]])
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

const formatJson = (value: unknown): string => {
  return JSON.stringify(value ?? {}, null, 2)
}

const selectedStagePreviewShape = (): { canDraft: boolean; width: number; height: number } => {
  const record = findSelectedStagePreviewRecord()
  const stage = pipelineConfigPipelines.value
    .find((pipeline) => pipeline.id === selectedPipelineId.value)
    ?.stages.find((candidate) => candidate.id === selectedStageId.value)
  const width = record?.input_shape?.[1] ?? 0
  const height = record?.input_shape?.[0] ?? 0
  return {
    canDraft:
      Boolean(stage?.features?.includes(ALLOW_POLYGONS_FEATURE)) &&
      Boolean(record?.input_preview) &&
      width > 0 &&
      height > 0,
    width,
    height,
  }
}

const findSelectedStagePreviewRecord = (): DebugRecord | undefined => {
  const records = debugState.value.records ?? []
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
}

const setApiError = (error: unknown): void => {
  apiError.value = error instanceof Error ? error.message : 'Unexpected NVR web API error'
}
