<script setup>
import { computed, onMounted, ref } from 'vue';
import * as api from '../api';

const logs = ref([]);
const loading = ref(false);

onMounted(async () => {
  loading.value = true;
  try {
    logs.value = await api.getLogs();
  } finally {
    loading.value = false;
  }
});

function formatTokens(value) {
  return new Intl.NumberFormat('en-US').format(Number(value || 0));
}

function formatCost(value) {
  return `$${Number(value || 0).toFixed(6)}`;
}

function formatSeconds(ms) {
  const seconds = Number(ms || 0) / 1000;
  if (seconds >= 10) return `${Math.round(seconds)} s`;
  const text = seconds >= 1 ? seconds.toFixed(1) : seconds.toFixed(2);
  return `${Number(text)} s`;
}

function isStreaming(log) {
  return Number(log.firstTokenMs || 0) < Number(log.useTimeMs || 0);
}

function detailLines(log) {
  return log.detailLines?.length ? log.detailLines : ['暂无详情'];
}

function tokenClass(token) {
  return token ? 'pill token-pill' : 'pill token-pill muted';
}

const emptyTitle = computed(() => (loading.value ? '加载中...' : '暂无请求日志'));
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>请求日志</h1>
      <p>查看每次代理请求的模型、用时、输入输出和费用</p>
    </header>

    <div class="card">
      <div v-if="loading" class="empty">
        <div class="loader"></div>
        <span>{{ emptyTitle }}</span>
      </div>

      <div v-else-if="logs.length === 0" class="empty">
        <div class="empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>
        <strong>暂无请求日志</strong>
        <span>开始使用 API 后，这里会显示请求明细</span>
      </div>

      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>时间</th>
              <th>令牌</th>
              <th>分组</th>
              <th>类型</th>
              <th>模型</th>
              <th>用时/首字</th>
              <th>输入</th>
              <th>输出</th>
              <th>花费</th>
              <th>IP</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td class="td-muted">{{ new Date(log.createdAt).toLocaleString() }}</td>
              <td><span :class="tokenClass(log.token)">{{ log.token }}</span></td>
              <td><code class="group-code">{{ log.group }}</code></td>
              <td><span class="pill type-pill">{{ log.type }}</span></td>
              <td><span class="model-pill">{{ log.model || '-' }}</span></td>
              <td>
                <div class="usage">
                  <span class="pill usage-pill">{{ formatSeconds(log.useTimeMs) }}</span>
                  <span class="pill usage-pill subtle">{{ formatSeconds(log.firstTokenMs) }}</span>
                  <span v-if="isStreaming(log)" class="pill stream-pill">流</span>
                </div>
              </td>
              <td class="num-cell">
                <strong>{{ formatTokens(log.inputTokens) }}</strong>
                <span v-if="log.cacheReadTokens" class="subline">缓存读 {{ formatTokens(log.cacheReadTokens) }}</span>
              </td>
              <td class="num-cell">
                <strong>{{ formatTokens(log.outputTokens) }}</strong>
                <span v-if="log.cacheCreationTokens" class="subline">缓存写 {{ formatTokens(log.cacheCreationTokens) }}</span>
              </td>
              <td class="td-cost">{{ formatCost(log.cost) }}</td>
              <td class="td-muted">{{ log.ip || '-' }}</td>
              <td class="detail-cell">
                <div v-for="line in detailLines(log)" :key="line">{{ line }}</div>
              </td>
            </tr>
          </tbody>
        </table>
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
.page-head h1 { font-size: 26px; font-weight: 800; letter-spacing: 0; }
.page-head p { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }

.card {
  background: var(--surface);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.table-wrap {
  overflow-x: auto;
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
  width: 28px;
  height: 28px;
  border: 2.5px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.table {
  width: 100%;
  min-width: 1320px;
  border-collapse: collapse;
}

.table th {
  text-align: left;
  padding: 12px 16px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}

.table td {
  padding: 14px 16px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.table tbody tr { transition: background var(--duration) var(--ease); }
.table tbody tr:hover { background: rgba(0, 0, 0, 0.01); }
.table tbody tr:last-child td { border-bottom: none; }

.td-muted { color: var(--text-muted); font-size: 12px; white-space: nowrap; }

.pill,
.model-pill,
.group-code {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.token-pill {
  background: #eef2ff;
  color: #4338ca;
}

.token-pill.muted {
  background: var(--bg);
  color: var(--text-muted);
}

.group-code {
  display: inline-block;
  background: #e0f2fe;
  color: #075985;
  font-family: 'SF Mono', monospace;
  font-weight: 600;
  max-width: 260px;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-all;
}

.type-pill {
  background: var(--success-soft);
  color: #065f46;
}

.model-pill {
  background: #dcfce7;
  color: #166534;
}

.usage {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.usage-pill {
  background: #dcfce7;
  color: #166534;
}

.usage-pill.subtle {
  background: #e2f0ff;
  color: #1d4ed8;
}

.stream-pill {
  background: #dbeafe;
  color: #1d4ed8;
}

.num-cell strong {
  display: block;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.subline {
  display: block;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.td-cost {
  font-family: 'SF Mono', monospace;
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
}

.detail-cell {
  min-width: 220px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 760px) {
  .page-head h1 {
    font-size: 24px;
  }
}
</style>
