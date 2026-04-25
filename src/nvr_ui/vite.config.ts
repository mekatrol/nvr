import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  base: '/',
  build: {
    assetsDir: 'assets',
    emptyOutDir: true,
    outDir: '../nvr_web/web',
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8080',
    },
  },
  define: {
    __API_BASE_URL__: JSON.stringify(command === 'serve' ? '' : ''),
  },
  plugins: [vue(), vueDevTools()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
}))
