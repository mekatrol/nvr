export type Camera = {
  id: string
  name: string
  enabled: boolean
  pipeline_enabled: boolean
}

export type DebugSourceFile = {
  id: string
  name: string
  frame_interval_seconds: number | null
}

export type AppConfig = {
  debug_source_file: DebugSourceFile | null
}

export type Stage = {
  id: string
  enabled: boolean
  module?: string
  class_name?: string
  filename?: string | null
  pipeline?: string | null
  features?: string[]
  config: Record<string, unknown>
}

export type Pipeline = {
  id: string
  name?: string
  enabled: boolean
  stages: Stage[]
}

export type PipelineIntegrityIssue = {
  level: string
  message: string
}

export type PipelineIntegrity = {
  ok: boolean
  issues: PipelineIntegrityIssue[]
}

export type DebugRecord = {
  pipeline_id: string
  stage_id: string
  status: string
  input_shape: number[] | null
  output_shape: number[] | null
  input_preview: string | null
  output_preview: string | null
}

export type DebugState = {
  status: string
  cursor?: number
  total_steps?: number
  records?: DebugRecord[]
}

export type PipelinesResponse = {
  enabled: boolean
  integrity?: PipelineIntegrity
  frame_interval_seconds: number | string | null
  selected_pipeline_config_path?: string
  pipelines: Pipeline[]
}

export type LogEntry = {
  timestamp: string
  level: string
  description: string
}

export type LogSeverity = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

export type MaskPoint = {
  x: number
  y: number
}

export type MaskConfig = {
  polygons?: MaskPoint[][]
  [key: string]: unknown
}
