<script setup lang="ts">
import StagePreview from './StagePreview.vue'
import { useNvrAppState } from '@/composables/useNvrAppState'

const {
  cameras,
  selectedCameraId,
  pipelines,
  debugState,
  selectedBreakpoint,
  apiError,
  isLoadingCameras,
  pipelineIntegrity,
  deployStatus,
  debugPipelineId,
  selectedStageId,
  materialIcons,
  selectedCamera,
  selectedDebugPipeline,
  selectedDebugPipelineStages,
  hasPipelineIntegrityProblem,
  isActionBusy,
  isRunLoopActive,
  canRun,
  canStop,
  canStep,
  canSetBreakpoint,
  loadCameras,
  reloadPipelines,
  runDebuggerCommand,
  stopDebuggerRun,
  startRunLoop,
  toggleBreakpoint,
  refreshCamera,
  withAction,
  selectDebugPipeline,
  selectDebugStage,
} = useNvrAppState()
</script>

<template>
  <section class="shell">
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
            <select
              v-model="debugPipelineId"
              :disabled="hasPipelineIntegrityProblem || pipelines.length === 0"
              @change="selectDebugPipeline(debugPipelineId)"
            >
              <option v-if="pipelines.length === 0" value="">No pipelines loaded</option>
              <option v-for="pipeline in pipelines" :key="pipeline.id" :value="pipeline.id">
                {{ pipeline.name || pipeline.id }}
              </option>
            </select>
          </label>
          <label class="ribbon-field">
            <span>Stage</span>
            <select
              v-model="selectedStageId"
              :disabled="hasPipelineIntegrityProblem || selectedDebugPipelineStages.length === 0"
              @change="selectDebugStage(selectedStageId)"
            >
              <option v-if="selectedDebugPipelineStages.length === 0" value="">No stages loaded</option>
              <option v-for="stage in selectedDebugPipelineStages" :key="stage.id" :value="stage.id">
                {{ stage.id }}
              </option>
            </select>
          </label>
          <button
            class="refresh-button"
            :disabled="isActionBusy || isRunLoopActive"
            @click="withAction('refresh_cameras', () => loadCameras().then(refreshCamera))"
          >
            Refresh
          </button>
          <button
            class="refresh-button"
            :disabled="isActionBusy || isRunLoopActive"
            @click="withAction('reload_pipelines', reloadPipelines)"
          >
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
                <option
                  v-for="stage in pipeline.stages"
                  :key="`${pipeline.id}:${stage.id}`"
                  :value="`${pipeline.id}:${stage.id}`"
                >
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
        <span>{{ selectedCamera?.enabled ? 'Recorder enabled' : 'Recorder disabled' }}</span>
        <span>{{ selectedCamera?.pipeline_enabled ? 'Pipeline enabled' : 'Pipeline disabled' }}</span>
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

      <StagePreview />
    </section>
  </section>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  background: #f4f6f8;
}

.workspace {
  display: grid;
  gap: 16px;
  padding: 18px;
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

.refresh-button {
  border: 1px solid #b8c2cc;
  border-radius: 6px;
  padding: 8px 10px;
  background: #ffffff;
  color: #1f2933;
  cursor: pointer;
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

.error {
  color: #fecaca;
}

.status {
  color: #bbf7d0;
}

@media (max-width: 820px) {
  .shell {
    grid-template-columns: 1fr;
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
}
</style>
