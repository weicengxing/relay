<script setup>
import { ref, onMounted } from 'vue';
import * as api from '../api';

const keys = ref([]);
const loading = ref(false);
const showCreate = ref(false);
const newKeyName = ref('');
const newKey = ref(null);
const visibleKeyIds = ref(new Set());
const copiedKeyId = ref(null);
const createError = ref('');

onMounted(async () => {
  loading.value = true;
  try {
    keys.value = await api.getApiKeys();
  } finally {
    loading.value = false;
  }
});

async function handleCreate() {
  const name = newKeyName.value.trim();
  if (!name) return;
  createError.value = '';
  if (keys.value.some(k => String(k.name || '').trim().toLowerCase() === name.toLowerCase())) {
    createError.value = '密钥名称已存在';
    return;
  }
  try {
    const result = await api.createApiKey(name);
    newKey.value = result;
    keys.value.push(result);
    newKeyName.value = '';
    showCreate.value = false;
  } catch (error) {
    createError.value = error.message || '创建失败';
  }
}

async function handleRevoke(id) {
  await api.revokeApiKey(id);
  keys.value = keys.value.filter(k => k.id !== id);
}

function isKeyVisible(id) {
  return visibleKeyIds.value.has(id);
}

function toggleKeyVisibility(id) {
  const next = new Set(visibleKeyIds.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  visibleKeyIds.value = next;
}

function displayKey(key, id) {
  if (!key || isKeyVisible(id)) {
    return key || '';
  }
  if (key.length <= 22) {
    return `${key.slice(0, 8)}...`;
  }
  return `${key.slice(0, 12)}...${key.slice(-6)}`;
}

async function copyKey(key, id) {
  if (!key) return;
  await navigator.clipboard.writeText(key);
  copiedKeyId.value = id;
  window.setTimeout(() => {
    if (copiedKeyId.value === id) {
      copiedKeyId.value = null;
    }
  }, 1200);
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>API 密钥</h1>
        <p>管理用于访问中转服务的密钥。</p>
      </div>
      <button class="btn-primary" @click="showCreate = true">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        新建密钥
      </button>
    </header>

    <transition name="fade">
      <div v-if="newKey" class="toast">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        <span>密钥已创建：</span>
        <code>{{ newKey.key }}</code>
        <button @click="newKey = null">&times;</button>
      </div>
    </transition>

    <transition name="fade">
      <div v-if="showCreate" class="create-bar">
        <input v-model="newKeyName" placeholder="密钥名称，例如：生产环境" class="create-input" />
        <button class="btn-primary" @click="handleCreate">创建</button>
        <button class="btn-ghost" @click="showCreate = false">取消</button>
        <span v-if="createError" class="create-error">{{ createError }}</span>
      </div>
    </transition>

    <div class="card">
      <div v-if="loading" class="empty">
        <div class="loader"></div>
        <span>加载中...</span>
      </div>
      <div v-else-if="keys.length === 0" class="empty">
        <div class="empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78Zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
        </div>
        <strong>暂无 API 密钥</strong>
        <span>点击上方按钮创建你的第一枚密钥。</span>
      </div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>名称</th>
            <th>密钥</th>
            <th>状态</th>
            <th>创建时间</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="k in keys" :key="k.id">
            <td class="td-name">{{ k.name }}</td>
            <td class="td-key">
              <div class="key-cell">
                <code :title="isKeyVisible(k.id) ? k.key : ''">{{ displayKey(k.key, k.id) }}</code>
                <div class="key-actions">
                  <button
                    class="icon-btn"
                    :class="{ copied: copiedKeyId === k.id }"
                    type="button"
                    title="复制密钥"
                    aria-label="复制密钥"
                    @click="copyKey(k.key, k.id)"
                  >
                    <svg v-if="copiedKeyId === k.id" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                      <path d="M20 6 9 17l-5-5"/>
                    </svg>
                    <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="9" y="9" width="13" height="13" rx="2"/>
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                  </button>
                  <button
                    class="icon-btn"
                    type="button"
                    :title="isKeyVisible(k.id) ? '隐藏密钥' : '显示密钥'"
                    :aria-label="isKeyVisible(k.id) ? '隐藏密钥' : '显示密钥'"
                    @click="toggleKeyVisibility(k.id)"
                  >
                    <svg v-if="isKeyVisible(k.id)" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="m2 2 20 20"/>
                      <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/>
                      <path d="M9.9 4.2A10.8 10.8 0 0 1 12 4c5 0 9 4.5 10 8a11.8 11.8 0 0 1-2.3 3.8"/>
                      <path d="M6.1 6.1C4.1 7.5 2.7 9.6 2 12c1 3.5 5 8 10 8 1.5 0 2.8-.4 4-1"/>
                    </svg>
                    <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M2 12s4-8 10-8 10 8 10 8-4 8-10 8S2 12 2 12Z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                  </button>
                </div>
              </div>
            </td>
            <td><span class="pill" :class="k.status">{{ k.status }}</span></td>
            <td class="td-muted">{{ new Date(k.createdAt).toLocaleDateString() }}</td>
            <td><button class="btn-danger-sm" @click="handleRevoke(k.id)">吊销</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.page { animation: pageIn 0.4s var(--ease-out); }

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  gap: 16px;
}

.page-head h1 { font-size: 26px; font-weight: 800; letter-spacing: 0; }
.page-head p { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  background: var(--text);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
  white-space: nowrap;
}

.btn-primary:hover { background: #0f0f23; transform: translateY(-1px); box-shadow: var(--shadow-md); }

.btn-ghost {
  padding: 10px 18px;
  background: transparent;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.btn-ghost:hover { background: var(--primary-soft); border-color: var(--primary-glow); }

.btn-danger-sm {
  padding: 6px 14px;
  background: var(--danger-soft);
  color: var(--danger);
  border: none;
  border-radius: var(--radius-xs);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.btn-danger-sm:hover { background: #fef2f2; }

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--success-soft);
  border-radius: var(--radius-sm);
  margin-bottom: 16px;
  font-size: 13px;
  color: #065f46;
}

.toast code {
  background: rgba(0,0,0,0.05);
  padding: 3px 8px;
  border-radius: 6px;
  font-family: 'SF Mono', monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
  word-break: break-all;
}

.toast button {
  margin-left: auto;
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: inherit;
  opacity: 0.5;
}

.create-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.create-input {
  flex: 1;
  padding: 10px 14px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  outline: none;
  transition: all var(--duration) var(--ease);
  background: var(--surface);
}

.create-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}

.create-error {
  color: var(--danger);
  font-size: 13px;
  font-weight: 600;
}

.card {
  background: var(--surface);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 56px 20px;
  gap: 10px;
  color: var(--text-muted);
}

.empty-icon { opacity: 0.3; margin-bottom: 4px; }
.empty strong { font-size: 15px; color: var(--text-secondary); }
.empty span { font-size: 13px; }

.loader {
  width: 28px; height: 28px;
  border: 2.5px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.table {
  width: 100%;
  border-collapse: collapse;
}

.table th {
  text-align: left;
  padding: 12px 20px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}

.table td {
  padding: 14px 20px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
}

.table tbody tr { transition: background var(--duration) var(--ease); }
.table tbody tr:hover { background: rgba(0,0,0,0.01); }
.table tbody tr:last-child td { border-bottom: none; }

.td-name { font-weight: 600; }
.td-key { max-width: 560px; }

.key-cell {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto;
  align-items: center;
  gap: 8px;
}

.key-cell code {
  min-width: 0;
}

.key-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.icon-btn {
  width: 28px;
  height: 28px;
  display: inline-grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--text-muted);
  background: transparent;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.icon-btn:hover {
  color: var(--primary);
  background: var(--primary-soft);
  border-color: var(--primary-glow);
}

.icon-btn.copied {
  color: #047857;
  background: var(--success-soft);
}

.table code {
  background: var(--bg);
  padding: 3px 8px;
  border-radius: 6px;
  font-family: 'SF Mono', monospace;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-all;
}

.td-muted { color: var(--text-muted); font-size: 12px; }

.pill {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.pill.active { background: var(--success-soft); color: #065f46; }
.pill.revoked { background: var(--danger-soft); color: #991b1b; }

@media (max-width: 760px) {
  .page-head,
  .create-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .table {
    min-width: 720px;
  }

  .card {
    overflow-x: auto;
  }
}
</style>
