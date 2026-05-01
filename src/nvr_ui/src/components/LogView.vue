<script setup lang="ts">
import { useNvrAppState } from '@/composables/useNvrAppState'

const {
  apiError,
  logEntries,
  selectedLogSeverities,
  isLoadingLogs,
  filteredLogEntries,
  logSeverityOptions,
  loadLogs,
  clearLogs,
} = useNvrAppState()
</script>

<template>
  <section class="log-shell">
    <header class="log-header">
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
</template>

<style scoped>
.log-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 100vh;
  background: #f4f6f8;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid #304157;
  padding: 12px 16px;
  background: #18222f;
  color: #f7fafc;
}

.log-header > div:first-child {
  display: grid;
  gap: 2px;
}

.log-header span {
  color: #cbd5df;
  font-size: 13px;
}

.log-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.log-actions button {
  border: 1px solid #506070;
  border-radius: 6px;
  padding: 8px 10px;
  background: #223044;
  color: #f7fafc;
  font-size: 13px;
  cursor: pointer;
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
  .log-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
