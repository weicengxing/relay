<script setup>
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import * as api from '../api';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const email = ref('');
const password = ref('');
const error = ref('');
const loading = ref(false);

async function handleSubmit() {
  error.value = '';
  loading.value = true;
  try {
    await auth.login(email.value, password.value);
    router.push('/');
  } catch (e) {
    error.value = e.message || '登录失败';
  } finally {
    loading.value = false;
  }
}

function handleDcLogin() {
  const redirect = safeRedirectPath(route.query.redirect);
  const callbackPath = `/login?redirect=${encodeURIComponent(redirect)}`;
  window.location.href = api.dcLoginUrl(callbackPath);
}

function consumeDcLoginCallback() {
  const hash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : '';
  if (!hash) return;
  const params = new URLSearchParams(hash);
  if (params.get('dc_status') !== 'ok') return;
  const session = {
    token: params.get('token') || '',
    userId: params.get('userId') || '',
    email: params.get('email') || '',
    balance: params.get('balance') || '0',
  };
  if (!session.token || !session.userId) {
    error.value = '社区登录回调无效，请重试';
    return;
  }
  auth.loginWithSession(session);
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  const redirect = safeRedirectPath(route.query.redirect);
  router.push(redirect);
}

function safeRedirectPath(value) {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') ? value : '/';
}

onMounted(() => {
  consumeDcLoginCallback();
});
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-brand">
        <div class="brand-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        </div>
      </div>
      <h1>欢迎回来</h1>
      <p class="subtitle">登录你的 Relay 账户</p>

      <form @submit.prevent="handleSubmit" class="form">
        <transition name="fade">
          <div v-if="error" class="alert">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ error }}
          </div>
        </transition>

        <label class="field">
          <span class="field-label">邮箱</span>
          <input v-model="email" type="email" placeholder="your@qq.com" required />
        </label>

        <label class="field">
          <span class="field-label">密码</span>
          <input v-model="password" type="password" placeholder="输入密码" required />
        </label>

        <button type="submit" class="submit" :disabled="loading">
          <span v-if="loading" class="spin"></span>
          {{ loading ? '登录中...' : '登录' }}
        </button>
        <button type="button" class="dc-login" :disabled="loading" @click="handleDcLogin">
          dc.hhhl.cc 登录
        </button>
      </form>

      <p class="alt">请使用 dc.hhhl.cc 社区账号登录</p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  padding: 20px;
}

.auth-card {
  width: 100%;
  max-width: 380px;
  animation: cardIn 0.5s var(--ease-out);
}

@keyframes cardIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.auth-brand {
  margin-bottom: 32px;
}

.brand-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a78bfa 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.3);
}

h1 {
  font-size: 28px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: -0.5px;
  margin-top: 20px;
}

.subtitle {
  color: var(--text-secondary);
  font-size: 15px;
  margin-top: 6px;
}

.form {
  margin-top: 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.field input {
  padding: 12px 14px;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  outline: none;
  transition: all var(--duration) var(--ease);
  box-shadow: var(--shadow-xs);
}

.field input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}

.field input::placeholder {
  color: var(--text-muted);
}

.submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 13px;
  background: var(--text);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
  margin-top: 4px;
}

.submit:hover:not(:disabled) {
  background: #0f0f23;
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.submit:active:not(:disabled) {
  transform: translateY(0);
}

.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.dc-login {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  background: var(--surface);
  color: var(--text);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.dc-login:hover:not(:disabled) {
  border-color: var(--primary);
  box-shadow: var(--shadow-sm);
}

.dc-login:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spin {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.alert {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--danger-soft);
  color: var(--danger);
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
}

.alt {
  text-align: center;
  margin-top: 28px;
  font-size: 13px;
  color: var(--text-muted);
}

.alt a {
  color: var(--primary);
  font-weight: 600;
}
</style>
