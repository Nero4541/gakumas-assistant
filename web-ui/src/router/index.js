// Composables
import {createRouter, createWebHistory} from 'vue-router'
import default_layout from '@/layouts/default.vue'


const routes = [
  {
    path: '/',
    name: "Default_Layout",
    component: default_layout,
  },
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes,
})

export default router
