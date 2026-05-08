<script setup>
import { computed, onBeforeUnmount, ref } from 'vue';
import { useRouter } from 'vue-router';
import { sendRegisterCode } from '../api';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const router = useRouter();

const email = ref('');
const password = ref('');
const confirmPassword = ref('');
const verificationCode = ref('');
const error = ref('');
const loading = ref(false);
const sendingCode = ref(false);
const showPassword = ref(false);
const showConfirmPassword = ref(false);
const countdown = ref(0);
let timer = null;

const canSendCode = computed(() => /^[1-9][0-9]{4,11}@qq\.com$/.test(email.value));

function startCountdown(seconds) {
  countdown.value = seconds;
  clearInterval(timer);
  timer = setInterval(() => {
    countdown.value -= 1;
    if (countdown.value <= 0) {
      clearInterval(timer);
      timer = null;
    }
  }, 1000);
}

async function handleSendCode() {
  error.value = '';
  if (!canSendCode.value) {
    error.value = '请先填写纯数字 QQ 邮箱';
    return;
  }
  sendingCode.value = true;
  try {
    await sendRegisterCode(email.value);
    startCountdown(60);
  } catch (e) {
    error.value = e.message || '验证码发送失败';
  } finally {
    sendingCode.value = false;
  }
}

async function handleSubmit() {
  error.value = '';
  if (password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致';
    return;
  }
  if (!verificationCode.value) {
    error.value = '请输入验证码';
    return;
  }
  loading.value = true;
  try {
    await auth.register(email.value, password.value, verificationCode.value);
    router.push('/');
  } catch (e) {
    error.value = e.message || '注册失败';
  } finally {
    loading.value = false;
  }
}

onBeforeUnmount(() => {
  clearInterval(timer);
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
      <h1>创建账号</h1>
      <p class="subtitle">仅支持纯数字 QQ 邮箱注册</p>

      <form class="form" @submit.prevent="handleSubmit">
        <transition name="fade">
          <div v-if="error" class="alert">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ error }}
          </div>
        </transition>

        <label class="field">
          <span class="field-label">QQ 邮箱</span>
          <div class="inline-row">
            <input v-model="email" type="email" placeholder="123456789@qq.com" required />
            <button
              type="button"
              class="code-btn"
              :class="{ 'code-btn-counting': countdown > 0 }"
              :disabled="sendingCode || countdown > 0 || !canSendCode"
              @click="handleSendCode"
            >
              <span v-if="sendingCode" class="spin spin-sm"></span>
              <svg v-else-if="countdown <= 0" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
              <span>{{ sendingCode ? '发送中' : countdown > 0 ? `${countdown}s` : '获取验证码' }}</span>
            </button>
          </div>
          <span class="hint">邮箱必须是 6 位以上纯数字 QQ 号</span>
        </label>

        <label class="field">
          <span class="field-label">验证码</span>
          <div class="code-input-wrapper">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            <input v-model="verificationCode" inputmode="numeric" maxlength="6" placeholder="输入 6 位验证码" required />
          </div>
        </label>

        <label class="field">
          <span class="field-label">密码</span>
          <div class="code-input-wrapper">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            <input v-model="password" :type="showPassword ? 'text' : 'password'" placeholder="至少 8 位" minlength="8" required />
            <button type="button" class="toggle-pwd" @click="showPassword = !showPassword" tabindex="-1">
              <svg v-if="showPassword" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
          </div>
        </label>

        <label class="field">
          <span class="field-label">确认密码</span>
          <div class="code-input-wrapper">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/></svg>
            <input v-model="confirmPassword" :type="showConfirmPassword ? 'text' : 'password'" placeholder="再次输入密码" required />
            <button type="button" class="toggle-pwd" @click="showConfirmPassword = !showConfirmPassword" tabindex="-1">
              <svg v-if="showConfirmPassword" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
          </div>
        </label>

        <button type="submit" class="submit" :disabled="loading">
          <span v-if="loading" class="spin"></span>
          {{ loading ? '注册中...' : '创建账号' }}
        </button>
      </form>

      <p class="alt">已有账号？<router-link to="/login">去登录</router-link></p>
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
  max-width: 400px;
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
  font-size: 14px;
  margin-top: 6px;
}

.form {
  margin-top: 28px;
  display: flex;
  flex-direction: column;
  gap: 18px;
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

.inline-row {
  display: flex;
  gap: 10px;
}

.inline-row input {
  flex: 1;
  min-width: 0;
  padding: 12px 14px;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  outline: none;
  transition: all var(--duration) var(--ease);
  box-shadow: var(--shadow-xs);
}

.inline-row input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}

.inline-row input::placeholder {
  color: var(--text-muted);
}

.code-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 16px;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
  cursor: pointer;
  white-space: nowrap;
  transition: all var(--duration) var(--ease);
  box-shadow: var(--shadow-xs);
  flex-shrink: 0;
}

.code-btn:hover:not(:disabled) {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.code-btn:disabled {
  color: var(--text-muted);
  cursor: not-allowed;
}

.code-btn-counting {
  color: var(--text-muted);
  border-color: var(--border);
}

.code-input-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 14px;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  transition: all var(--duration) var(--ease);
  box-shadow: var(--shadow-xs);
}

.code-input-wrapper:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}

.code-input-wrapper svg {
  color: var(--text-muted);
  flex-shrink: 0;
  transition: color var(--duration) var(--ease);
}

.code-input-wrapper:focus-within svg {
  color: var(--primary);
}

.code-input-wrapper input {
  flex: 1;
  padding: 12px 0;
  border: none;
  background: transparent;
  font-size: 14px;
  outline: none;
}

.toggle-pwd {
  display: flex;
  align-items: center;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--text-muted);
  transition: color var(--duration) var(--ease);
  flex-shrink: 0;
}

.toggle-pwd:hover {
  color: var(--primary);
}

.code-input-wrapper input::placeholder {
  color: var(--text-muted);
}

.hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: -2px;
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

.spin {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.spin-sm {
  width: 14px;
  height: 14px;
  border-width: 1.5px;
  border-color: var(--text-muted);
  border-top-color: var(--primary);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

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
