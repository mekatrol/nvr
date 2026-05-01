<script setup lang="ts">
import { useNvrAppState } from '@/composables/useNvrAppState'

const {
  apiError,
  deployStatus,
  canEditPipelines,
  vscodeWebUrl,
  vscodeLoadFailed,
  withAction,
  generateExampleResizePipeline,
  deployPipelinesFromEditor,
} = useNvrAppState()
</script>

<template>
  <section class="vscode-shell">
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
        <span>
          Start it with code serve-web --host 127.0.0.1 --port 8000 --without-connection-token
          --accept-server-license-terms --default-folder /home/dad/nvr/pipeline_config, then
          reload this view.
        </span>
      </div>
    </section>
  </section>
</template>

<style scoped>
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

.vscode-header a,
.vscode-header button {
  border: 1px solid #506070;
  border-radius: 6px;
  padding: 8px 10px;
  background: #223044;
  color: #f7fafc;
  text-decoration: none;
  font-size: 13px;
  cursor: pointer;
}

.vscode-actions {
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
  color: #78350f;
  font-size: 13px;
}

.error {
  color: #fecaca;
}

.status {
  color: #bbf7d0;
}

@media (max-width: 820px) {
  .vscode-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
