import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    component: () => import('../components/AppLayout.vue'),
    children: [
      { path: '', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
      { path: 'api-keys', name: 'ApiKeys', component: () => import('../views/ApiKeys.vue') },
      { path: 'chat', name: 'Chat', component: () => import('../views/Chat.vue') },
      { path: 'logs', name: 'Logs', component: () => import('../views/Logs.vue') },
      { path: 'models', name: 'Models', component: () => import('../views/Models.vue') },
      { path: 'novels', name: 'Novels', component: () => import('../views/Novels.vue') },
      { path: 'recharge', name: 'Recharge', component: () => import('../views/Recharge.vue') },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.guest) return true;
  if (!auth.isLoggedIn) return { name: 'Login' };
  return true;
});

export default router;
