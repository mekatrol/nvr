import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'debugger',
      component: { template: '<div />' },
    },
    {
      path: '/editor',
      name: 'editor',
      component: { template: '<div />' },
    },
    {
      path: '/log',
      name: 'log',
      component: { template: '<div />' },
    },
  ],
})

export default router
