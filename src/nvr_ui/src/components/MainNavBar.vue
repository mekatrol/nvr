<script setup lang="ts">
const navItems = [
  { to: '/', label: 'Debugger', icon: 'bug_report' },
  { to: '/editor', label: 'Editor', icon: 'edit_note' },
  { to: '/log', label: 'Log', icon: 'article' },
] as const
</script>

<template>
  <nav class="main-nav-bar" aria-label="Primary navigation">
    <RouterLink v-for="item in navItems" :key="item.to" :to="item.to">
      <span class="material-symbols-outlined" aria-hidden="true">{{ item.icon }}</span>
      <span>{{ item.label }}</span>
    </RouterLink>
  </nav>
</template>

<style scoped>
.main-nav-bar {
  display: grid;
  gap: 6px;
}

.main-nav-bar a {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  border-radius: 6px;
  padding: 8px 10px;
  color: #cbd5df;
  text-decoration: none;
  font-size: 14px;
}

.main-nav-bar a:hover,
.main-nav-bar a.router-link-active {
  background: #223044;
  color: #ffffff;
}

.material-symbols-outlined {
  width: 18px;
  overflow: hidden;
  font-size: 18px;
  font-variation-settings:
    'FILL' 0,
    'wght' 400,
    'GRAD' 0,
    'opsz' 20;
  line-height: 1;
}

@media (max-width: 820px) {
  .main-nav-bar {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .main-nav-bar a {
    justify-content: center;
  }
}
</style>
