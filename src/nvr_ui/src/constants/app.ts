import type { LogSeverity } from '@/types/nvr'

export const DEFAULT_PIPELINE_FRAME_INTERVAL_SECONDS = 0.5

export const ALLOW_POLYGONS_FEATURE = 'AllowPolygons'

export const LOG_SEVERITY_OPTIONS: LogSeverity[] = [
  'DEBUG',
  'INFO',
  'WARNING',
  'ERROR',
  'CRITICAL',
]

export const MATERIAL_ICONS = {
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

export const DEFAULT_VSCODE_WEB_URL =
  'http://127.0.0.1:8000/?folder=/home/dad/nvr/pipeline_config/pipelines'
