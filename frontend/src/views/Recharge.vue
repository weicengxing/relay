<script setup>
import { ref } from 'vue';
import * as api from '../api';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const amount = ref('');
const remark = ref('');
const loading = ref(false);
const success = ref(false);
const error = ref('');
const presets = [10, 50, 100, 500];

async function handleSubmit() {
  error.value = '';
  const val = parseFloat(amount.value);
  if (!val || val <= 0) { error.value = '请输入有效的充值金额'; return; }
  loading.value = true;
  try {
    await api.createRecharge(val, remark.value);
    success.value = true;
    amount.value = '';
    remark.value = '';
  } catch (e) {
    error.value = e.message || '充值失败';
  } finally { loading.value = false; }
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>充值</h1>
      <p>为你的账户充值以使用更多服务</p>
    </header>

    <div class="layout">
      <div class="card main-card">
        <div class="balance-strip">
          <div>
            <div class="bal-label">当前余额</div>
            <div class="bal-value">{{ auth.balance.toFixed(2) }}</div>
          </div>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><rect x="1" y="4" width="22" height="16" rx="3"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
        </div>

        <transition name="fade" mode="out-in">
          <div v-if="success" class="success-box">
            <div class="success-icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            </div>
            <h3>充值申请已提交</h3>
            <p>等待管理员审核，审核通过后余额会自动更新</p>
            <button class="btn-submit" @click="success = false">继续充值</button>
          </div>

          <form v-else @submit.prevent="handleSubmit" class="form">
            <transition name="fade">
              <div v-if="error" class="alert">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                {{ error }}
              </div>
            </transition>

            <label class="field">
              <span class="field-label">充值金额</span>
              <div class="presets">
                <button v-for="p in presets" :key="p" type="button" class="preset" :class="{ active: amount === String(p) }" @click="amount = String(p)">{{ p }}</button>
              </div>
              <div class="amount-box">
                <span class="currency">¥</span>
                <input v-model="amount" type="number" min="1" step="0.01" placeholder="自定义金额" />
              </div>
            </label>

            <label class="field">
              <span class="field-label">备注（可选）</span>
              <input v-model="remark" placeholder="添加备注" class="text-input" />
            </label>

            <button type="submit" class="btn-submit" :disabled="loading">
              <span v-if="loading" class="spin"></span>
              {{ loading ? '提交中...' : '提交充值' }}
            </button>
          </form>
        </transition>
      </div>

      <div class="card side-card">
        <h3>充值说明</h3>
        <ul>
          <li>充值申请提交后需要管理员审核</li>
          <li>审核通过后余额会自动更新</li>
          <li>如有问题请联系管理员</li>
          <li>支持自定义金额充值</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { animation: pageIn 0.4s var(--ease-out); }

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-head { margin-bottom: 24px; }
.page-head h1 { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }
.page-head p { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }

.layout {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 20px;
  align-items: start;
}

.card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.balance-strip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 28px 28px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a78bfa 100%);
  color: #fff;
}

.bal-label {
  font-size: 12px;
  font-weight: 600;
  opacity: 0.7;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.bal-value {
  font-size: 36px;
  font-weight: 800;
  letter-spacing: -1px;
  line-height: 1;
}

.success-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 28px;
  text-align: center;
}

.success-icon { color: var(--success); margin-bottom: 16px; }
.success-box h3 { font-size: 18px; font-weight: 700; margin-bottom: 6px; }
.success-box p { color: var(--text-secondary); font-size: 13px; margin-bottom: 24px; }

.form {
  padding: 28px;
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

.presets {
  display: flex;
  gap: 8px;
}

.preset {
  flex: 1;
  padding: 10px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
  color: var(--text);
}

.preset:hover {
  border-color: var(--primary-glow);
  background: var(--primary-soft);
}

.preset.active {
  background: var(--text);
  color: #fff;
  border-color: var(--text);
}

.amount-box {
  display: flex;
  align-items: center;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  transition: all var(--duration) var(--ease);
  background: var(--surface);
}

.amount-box:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}

.currency {
  padding: 0 14px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-muted);
}

.amount-box input {
  flex: 1;
  padding: 12px 14px 12px 0;
  border: none;
  background: transparent;
  font-size: 15px;
  outline: none;
}

.amount-box input::placeholder { color: var(--text-muted); }

.text-input {
  padding: 11px 14px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  outline: none;
  transition: all var(--duration) var(--ease);
  background: var(--surface);
}

.text-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}

.btn-submit {
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
}

.btn-submit:hover:not(:disabled) { background: #0f0f23; transform: translateY(-1px); box-shadow: var(--shadow-md); }
.btn-submit:disabled { opacity: 0.6; cursor: not-allowed; }

.spin {
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
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

.side-card {
  padding: 24px;
}

.side-card h3 {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 16px;
}

.side-card ul {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.side-card li {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  padding-left: 16px;
  position: relative;
}

.side-card li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--primary);
  opacity: 0.4;
}

@media (max-width: 768px) {
  .layout { grid-template-columns: 1fr; }
}
</style>
