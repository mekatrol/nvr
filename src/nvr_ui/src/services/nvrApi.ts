import { getJson, postJson } from './apiClient'
import type { Camera, DebugState, LogEntry, Pipeline, PipelineIntegrity, PipelinesResponse } from '@/types/nvr'

type PipelineGraphResponse = {
  pipelines: Pipeline[]
  integrity?: PipelineIntegrity
}

export const nvrApi = {
  getCameras: async (): Promise<Camera[]> => {
    const payload = await getJson<{ cameras: Camera[] }>('/api/cameras')
    return payload.cameras
  },

  getPipelines: (cameraId: string, pipelineConfigPath: string): Promise<PipelineGraphResponse> => {
    const query = pipelineConfigQuery(pipelineConfigPath)
    return getJson<PipelineGraphResponse>(`/api/pipelines?camera_id=${encodeURIComponent(cameraId)}${query}`)
  },

  getPipelineConfigPipelines: (): Promise<PipelinesResponse> => {
    return getJson<PipelinesResponse>('/api/pipeline_config/pipelines')
  },

  reloadPipelines: (): Promise<PipelineGraphResponse> => {
    return postJson<PipelineGraphResponse>('/api/pipelines/reload', {})
  },

  getDebugState: (cameraId: string, pipelineConfigPath: string): Promise<DebugState> => {
    const query = pipelineConfigQuery(pipelineConfigPath)
    return getJson<DebugState>(`/api/debug/state?camera_id=${encodeURIComponent(cameraId)}${query}`)
  },

  getLogs: async (limit = 500): Promise<LogEntry[]> => {
    const payload = await getJson<{ entries: LogEntry[] }>(`/api/logs?limit=${limit}`)
    return payload.entries
  },

  clearLogs: async (): Promise<LogEntry[]> => {
    const payload = await postJson<{ entries: LogEntry[] }>('/api/logs/clear', {})
    return payload.entries
  },

  runDebugCommand: (
    cameraId: string,
    pipelineConfigPath: string,
    command: string,
  ): Promise<DebugState> => {
    return postJson<DebugState>('/api/debug/command', {
      camera_id: cameraId,
      pipeline_config_path: pipelineConfigPath,
      command,
    })
  },

  setBreakpoint: (
    cameraId: string,
    pipelineConfigPath: string,
    pipelineId: string,
    stageId: string | null,
    enabled: boolean,
  ): Promise<DebugState> => {
    return postJson<DebugState>('/api/debug/breakpoints', {
      camera_id: cameraId,
      pipeline_config_path: pipelineConfigPath,
      pipeline_id: pipelineId,
      stage_id: stageId,
      enabled,
    })
  },

  generateExampleResizePipeline: (): Promise<PipelinesResponse> => {
    return postJson<PipelinesResponse>('/api/pipelines/examples/resize', {})
  },

  deployPipelines: (): Promise<PipelinesResponse> => {
    return postJson<PipelinesResponse>('/api/pipeline_config/pipelines/deploy', {})
  },
}

const pipelineConfigQuery = (pipelineConfigPath: string): string => {
  if (!pipelineConfigPath) return ''
  return `&pipeline_config_path=${encodeURIComponent(pipelineConfigPath)}`
}
