<script setup lang="ts">
import DebuggerView from './components/DebuggerView.vue'
import EditorView from './components/EditorView.vue'
import LogView from './components/LogView.vue'
import MainNavBar from './components/MainNavBar.vue'
import { useNvrAppState } from './composables/useNvrAppState'

const { isEditorRoute, isLogRoute } = useNvrAppState()
</script>

<template>
  <div class="app-layout">
    <aside class="app-sidebar">
      <div class="app-brand">NVR</div>
      <MainNavBar />
    </aside>

    <main class="app-content">
      <EditorView v-if="isEditorRoute" />
      <LogView v-else-if="isLogRoute" />
      <DebuggerView v-else />
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

:global(button),
:global(select),
:global(input),
:global(textarea) {
  font: inherit;
}

:global(button:disabled) {
  border-color: #cbd5df;
  background: #eef2f6;
  color: #718096;
  cursor: not-allowed;
  opacity: 0.55;
}

:global(button:disabled .material-symbols-outlined) {
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

@media (max-width: 820px) {
  .app-layout {
    grid-template-columns: 1fr;
  }

  .app-sidebar {
    position: static;
    height: auto;
  }
}
</style>
