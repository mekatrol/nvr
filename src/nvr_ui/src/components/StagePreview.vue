<template>
  <section class="stage-preview" aria-label="Stage image preview">
    <header class="stage-preview-header">
      <strong>Stage Preview</strong>
      <span>{{ stagePreviewRecord?.pipeline_id }} / {{ stagePreviewRecord?.stage_id }}</span>
    </header>
    <div class="stage-preview-grid">
      <article class="stage-preview-pane" :class="{ expanded: expandedPreview === 'input' }">
        <header>
          <strong>Entering Stage</strong>
          <button
            :disabled="!stagePreviewRecord?.input_preview"
            :title="expandedPreview === 'input' ? 'Collapse input preview' : 'Expand input preview'"
            @click="togglePreviewExpansion('input')"
          >
            <span class="material-symbols-outlined" aria-hidden="true">
              {{ expandedPreview === 'input' ? materialIcons.collapse : materialIcons.expand }}
            </span>
          </button>
        </header>
        <div class="preview-surface">
          <div
            v-if="stagePreviewRecord?.input_preview"
            class="mask-preview-frame"
            :class="{ editable: canDraftMask }"
          >
            <img
              ref="maskPreviewImage"
              :src="stagePreviewRecord.input_preview"
              alt="Stage input preview"
              @click="handleMaskPreviewClick"
              @dblclick="handleMaskPreviewDoubleClick"
            />
            <svg
              v-if="maskFrameWidth > 0 && maskFrameHeight > 0"
              class="mask-overlay"
              :viewBox="`0 0 ${maskFrameWidth} ${maskFrameHeight}`"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <polygon
                v-for="(polygon, index) in maskPolygons"
                :key="`mask-${index}`"
                :points="maskPolygonPoints(polygon)"
                class="mask-polygon"
              />
              <template v-for="(polygon, polygonIndex) in maskPolygons" :key="`points-${polygonIndex}`">
                <circle
                  v-for="(point, pointIndex) in polygon"
                  :key="`point-${polygonIndex}-${pointIndex}`"
                  :cx="point.x"
                  :cy="point.y"
                  :r="Math.max(3, Math.round(maskFrameWidth / 160))"
                  class="mask-polygon-point"
                />
              </template>
              <polygon
                v-if="hasMaskDraftArea"
                :points="maskPolygonPoints(maskDraftPolygon)"
                class="mask-draft-polygon"
              />
              <polyline
                v-if="maskDraftPolygon.length > 0"
                :points="maskPolygonPoints(maskDraftPolygon)"
                class="mask-draft-line"
              />
              <circle
                v-for="(point, index) in maskDraftPolygon"
                :key="`draft-${index}`"
                :cx="point.x"
                :cy="point.y"
                :r="Math.max(3, Math.round(maskFrameWidth / 160))"
                class="mask-draft-point"
              />
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
          <button
            :disabled="!stagePreviewRecord?.output_preview"
            :title="expandedPreview === 'output' ? 'Collapse output preview' : 'Expand output preview'"
            @click="togglePreviewExpansion('output')"
          >
            <span class="material-symbols-outlined" aria-hidden="true">
              {{ expandedPreview === 'output' ? materialIcons.collapse : materialIcons.expand }}
            </span>
          </button>
        </header>
        <div class="preview-surface">
          <img
            v-if="stagePreviewRecord?.output_preview"
            :src="stagePreviewRecord.output_preview"
            alt="Stage output preview"
          />
          <span v-else>No output preview available</span>
          <footer>
            <span>Output {{ stagePreviewRecord?.output_shape ?? [] }}</span>
          </footer>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useNvrAppState } from '@/composables/useNvrAppState'

const {
  materialIcons,
  stagePreviewRecord,
  expandedPreview,
  maskPreviewImage,
  canDraftMask,
  maskFrameWidth,
  maskFrameHeight,
  maskPolygons,
  maskDraftPolygon,
  hasMaskDraftArea,
  togglePreviewExpansion,
  handleMaskPreviewClick,
  handleMaskPreviewDoubleClick,
  maskPolygonPoints,
} = useNvrAppState()
</script>

<style scoped>
.stage-preview {
  display: grid;
  gap: 10px;
  min-height: 0;
  border: 1px solid #d7dee7;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
}

.stage-preview header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
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
</style>
