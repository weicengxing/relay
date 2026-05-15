<script setup>
import { computed, onMounted, ref } from 'vue';
import * as api from '../api';

const logs = ref([]);
const loading = ref(false);
const limit = ref(50);
const currentCursor = ref('');
const nextCursor = ref('');
const cursorStack = ref([]);
const hasMore = ref(false);
const pageNumber = computed(() => cursorStack.value.length + 1);
const canPrev = computed(() => cursorStack.value.length > 0 && !loading.value);
const canNext = computed(() => hasMore.value && !!nextCursor.value && !loading.value);

onMounted(() => {
  loadLogs('');
});

async function loadLogs(cursor) {
  loading.value = true;
  try {
    const data = await api.getLogs({ limit: limit.value, cursor });
    if (Array.isArray(data)) {
      logs.value = data.map(normalizeLog);
      hasMore.value = false;
      nextCursor.value = '';
      return;
    }
    logs.value = (data.items || []).map(normalizeLog);
    hasMore.value = Boolean(data.hasMore);
    nextCursor.value = data.nextCursor || '';
  } finally {
    loading.value = false;
  }
}

async function prevPage() {
  if (!canPrev.value) return;
  const previousCursor = cursorStack.value.pop() || '';
  currentCursor.value = previousCursor;
  await loadLogs(previousCursor);
}

async function nextPage() {
  if (!canNext.value) return;
  cursorStack.value.push(currentCursor.value);
  currentCursor.value = nextCursor.value;
  await loadLogs(currentCursor.value);
}

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

function formatCreatedAt(value) {
  const date = new Date(value || '');
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString();
}

function normalizeLog(log) {
  if (!log || typeof log !== 'object') return {};
  return {
    id: log.id,
    createdAt: log.createdAt ?? log.created_at,
    token: log.token ?? log.token_name,
    group: log.group ?? log.group_key,
    type: log.type ?? log.requestType ?? log.request_type,
    model: log.model,
    useTimeMs: log.useTimeMs ?? log.use_time_ms,
    firstTokenMs: log.firstTokenMs ?? log.first_token_ms,
    inputTokens: log.inputTokens ?? log.prompt_tokens,
    outputTokens: log.outputTokens ?? log.completion_tokens,
    cacheReadTokens: log.cacheReadTokens ?? log.cache_read_tokens,
    cacheCreationTokens: log.cacheCreationTokens ?? log.cache_creation_tokens,
    cost: log.cost,
    ip: log.ip,
    status: log.status,
    upstreamServiceId: log.upstreamServiceId ?? log.upstream_service_id,
  };
}

function isStreaming(log) {
  return Number(log.firstTokenMs || 0) < Number(log.useTimeMs || 0);
}

function displayModel(model) {
  const text = String(model || '').trim();
  if (!text) return '-';
  return text
    .replace(/[-_](?:20\d{2}-)?\d{1,2}-\d{1,2}$/, '')
    .replace(/(mini)\d{1,2}-\d{1,2}$/i, '$1');
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
              <th>类型</th>
              <th>模型</th>
              <th>用时/首字</th>
              <th>输入</th>
              <th>输出</th>
              <th>花费</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td class="td-muted">{{ formatCreatedAt(log.createdAt) }}</td>
              <td><span :class="tokenClass(log.token)">{{ log.token }}</span></td>
              <td><span class="pill type-pill">{{ log.type }}</span></td>
              <td><span class="model-pill">{{ displayModel(log.model) }}</span></td>
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
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="!loading && logs.length > 0" class="pager">
        <button class="pager-btn" type="button" :disabled="!canPrev" @click="prevPage">Prev</button>
        <span>Page {{ pageNumber }}</span>
        <button class="pager-btn" type="button" :disabled="!canNext" @click="nextPage">Next</button>
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

.pager {
  min-height: 52px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}

.pager span {
  min-width: 72px;
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

.pager-btn {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.pager-btn:hover:not(:disabled) {
  color: var(--primary);
  background: var(--primary-soft);
  border-color: var(--primary-glow);
}

.pager-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
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
  min-width: 860px;
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
.model-pill {
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

@media (max-width: 760px) {
  .page-head h1 {
    font-size: 24px;
  }
}
</style>
