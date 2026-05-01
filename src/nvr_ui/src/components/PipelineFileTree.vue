<template>
  <div class="pipeline-file-tree" :style="{ '--depth': depth ?? 0 }">
    <div v-for="node in nodes" :key="node.path" class="pipeline-file-node">
      <div
        class="pipeline-file-row"
        :class="{ selectable: isYamlFile(node) }"
        :title="node.path"
        @dblclick="openNode(node)"
      >
        <span class="material-symbols-outlined" aria-hidden="true">
          {{ fileIcon(node) }}
        </span>
        <span class="pipeline-file-label">{{ node.name }}</span>
      </div>
      <PipelineFileTree
        v-if="node.children.length > 0"
        :nodes="node.children"
        :depth="(depth ?? 0) + 1"
        @open-yaml="emit('openYaml', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
type PipelineFileTreeNode = {
  type: 'directory' | 'file'
  name: string
  path: string
  children: PipelineFileTreeNode[]
}

defineProps<{
  nodes: PipelineFileTreeNode[]
  depth?: number
}>()

const emit = defineEmits<{
  openYaml: [path: string]
}>()

function fileIcon(node: PipelineFileTreeNode) {
  if (node.type === 'directory') return 'folder'
  if (node.name.endsWith('.py')) return 'code'
  return 'description'
}

function isYamlFile(node: PipelineFileTreeNode) {
  return node.type === 'file' && /\.(ya?ml)$/i.test(node.name)
}

function openNode(node: PipelineFileTreeNode) {
  if (isYamlFile(node)) {
    emit('openYaml', node.path)
  }
}
</script>

<style scoped>
.pipeline-file-tree {
  display: grid;
  gap: 2px;
}

.pipeline-file-node {
  display: grid;
  gap: 2px;
}

.pipeline-file-row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 6px;
  min-height: 28px;
  margin-left: calc(var(--depth) * 18px);
  border-radius: 6px;
  padding: 2px 4px;
  color: #e6edf5;
}

.pipeline-file-row:hover {
  background: #26364a;
}

.pipeline-file-row.selectable {
  cursor: pointer;
}

.material-symbols-outlined {
  width: 16px;
  height: 16px;
  overflow: hidden;
  color: #a9c7ef;
  font-size: 16px;
  font-variation-settings:
    'FILL' 0,
    'wght' 400,
    'GRAD' 0,
    'opsz' 20;
  line-height: 1;
}

.pipeline-file-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
</style>
