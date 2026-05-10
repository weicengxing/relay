<script setup>
import { ref, onMounted } from 'vue';
import * as api from '../api';
import OpenAIIcon from '../components/OpenAIIcon.vue';
import XiaomiIcon from '../components/XiaomiIcon.vue';

const models = ref([]);
const loading = ref(false);
const error = ref('');

onMounted(async () => {
  loading.value = true;
  error.value = '';
  try {
    const data = await api.getModels();
    models.value = data || [];
  } catch (err) {
    error.value = err.message || '模型目录加载失败';
    models.value = [];
  } finally {
    loading.value = false;
  }
});

function price(value) {
  const number = Number(value || 0);
  return `$${number.toFixed(4)} / 1M Tokens`;
}

function isXiaomi(model) {
  return String(model?.provider || '').toLowerCase() === 'xiaomi';
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>模型目录</h1>
      <p>当前可用于中转服务的模型与计费价格。</p>
    </header>

    <div v-if="loading" class="empty">
      <div class="loader"></div>
      <span>加载中...</span>
    </div>

    <div v-else-if="error" class="empty">
      <span>{{ error }}</span>
    </div>

    <div v-else-if="!models.length" class="empty">
      <span>暂无可用模型</span>
    </div>

    <div v-else class="grid">
      <article v-for="m in models" :key="m.id" class="model-card">
        <div class="model-top">
          <div class="model-badge" :class="{ 'xiaomi-badge': isXiaomi(m) }">
            <XiaomiIcon v-if="isXiaomi(m)" />
            <OpenAIIcon v-else />
          </div>

          <div class="model-main">
            <div class="model-provider">{{ m.provider || 'OpenAI' }}</div>
            <h3>{{ m.name }}</h3>
            <div class="price-list">
              <p><span>输入价格</span><strong>{{ price(m.inputPrice) }}</strong></p>
              <p><span>输出价格</span><strong>{{ price(m.outputPrice) }}</strong></p>
              <p><span>缓存读取</span><strong>{{ price(m.cachedInputPrice) }}</strong></p>
              <p><span>缓存创建</span><strong>{{ price(m.cacheCreationPrice) }}</strong></p>
            </div>
          </div>
        </div>

        <div class="model-bottom">
          <span class="billing">按量计费</span>
          <div class="tags">
            <span v-for="tag in m.tags" :key="tag" class="tag" :class="`tag-${tag}`">{{ tag }}</span>
          </div>
        </div>
      </article>
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

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 56px 20px;
  gap: 10px;
  color: var(--text-muted);
}

.loader {
  width: 28px;
  height: 28px;
  border: 2.5px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.model-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 18px 20px 14px;
  box-shadow: var(--shadow-card);
  transition: transform var(--duration) var(--ease), box-shadow var(--duration) var(--ease);
}

.model-card:hover {
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-2px);
}

.model-top {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.model-badge {
  width: 52px;
  height: 52px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #111827;
  color: #fff;
  border: 1px solid rgba(17, 24, 39, 0.08);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
  flex-shrink: 0;
}

.model-badge svg {
  width: 31px;
  height: 31px;
}

.xiaomi-badge {
  background: #ff6900;
  border-color: rgba(255, 105, 0, 0.22);
  box-shadow: 0 8px 18px rgba(255, 105, 0, 0.18);
}

.xiaomi-badge svg {
  width: 52px;
  height: 52px;
}

.model-main { min-width: 0; flex: 1; }

.model-provider {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 2px;
}

.model-main h3 {
  font-size: 21px;
  font-weight: 800;
  margin-bottom: 10px;
  letter-spacing: 0;
}

.price-list {
  display: grid;
  gap: 5px;
}

.price-list p {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.price-list strong {
  color: var(--text);
  font-weight: 700;
  text-align: right;
  white-space: nowrap;
}

.model-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 26px;
}

.billing {
  padding: 4px 10px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.tags {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  padding: 4px 10px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #075985;
  font-size: 12px;
  font-weight: 600;
}

.tag-gpt5,
.tag-gpt-5 { background: #dcfce7; color: #166534; }
.tag-reasoning,
.tag-coding { background: #fef3c7; color: #92400e; }
.tag-mini { background: #fce7f3; color: #9d174d; }

@media (max-width: 700px) {
  .grid { grid-template-columns: 1fr; }
  .model-top { gap: 12px; }
  .price-list p { flex-direction: column; gap: 0; }
  .price-list strong { text-align: left; }
  .model-bottom { align-items: flex-start; flex-direction: column; }
}
</style>
