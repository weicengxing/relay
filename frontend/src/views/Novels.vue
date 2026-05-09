<script setup>
import { computed, onMounted, ref } from 'vue';
import * as api from '../api';

const novels = ref([]);
const ranking = ref([]);
const selectedNovel = ref(null);
const loading = ref(false);
const detailLoading = ref(false);
const rankingLoading = ref(false);
const uploading = ref(false);
const ratingSaving = ref(false);
const showUpload = ref(false);
const uploadError = ref('');
const readerError = ref('');
const boardMode = ref('score');
const boardLimit = ref(20);
const pageTab = ref('read');
const uploadedFileName = ref('');
const searchQuery = ref('');

const form = ref({
  title: '',
  author: '',
  content: '',
});

const boardModes = [
  { label: '评分榜', value: 'score' },
  { label: '新书榜', value: 'new' },
  { label: '我评过', value: 'mine' },
];

const boardLimits = [
  { label: 'Top 10', value: 10 },
  { label: 'Top 20', value: 20 },
  { label: '全部', value: 100 },
];

const selectedTitle = computed(() => selectedNovel.value?.title || '选择一本小说开始阅读');
const selectedAuthor = computed(() => selectedNovel.value?.author || '匿名作者');
const totalNovels = computed(() => novels.value.length);
const totalRatings = computed(() => novels.value.reduce((sum, item) => sum + Number(item.ratingCount || 0), 0));
const topScore = computed(() => {
  const best = ranking.value.find((item) => item.ratingCount > 0);
  return best ? Number(best.averageRating || 0).toFixed(1) : '0.0';
});

const filteredNovels = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return novels.value;
  return novels.value.filter(
    (n) => n.title?.toLowerCase().includes(q) || n.author?.toLowerCase().includes(q),
  );
});

const boardItems = computed(() => {
  let source = [];
  if (boardMode.value === 'score') {
    source = ranking.value;
  } else if (boardMode.value === 'new') {
    source = [...novels.value].sort((a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0));
  } else {
    source = novels.value.filter((item) => item.myRating);
  }
  return source.slice(0, boardLimit.value).map((item, index) => ({ ...item, rank: index + 1 }));
});

onMounted(async () => {
  await Promise.all([loadNovels(), loadRanking()]);
});

async function loadNovels() {
  loading.value = true;
  try {
    novels.value = await api.getNovels();
    if (!selectedNovel.value && novels.value.length) {
      await openNovel(novels.value[0].id);
    }
  } finally {
    loading.value = false;
  }
}

async function loadRanking() {
  rankingLoading.value = true;
  try {
    ranking.value = await api.getNovelRanking(100);
  } finally {
    rankingLoading.value = false;
  }
}

async function refreshAll() {
  await Promise.all([loadNovels(), loadRanking()]);
}

async function openNovel(id) {
  detailLoading.value = true;
  readerError.value = '';
  try {
    selectedNovel.value = await api.getNovel(id);
  } catch (error) {
    readerError.value = error.message || '小说加载失败';
  } finally {
    detailLoading.value = false;
  }
}

async function openFromBoard(item) {
  await openNovel(item.id);
  document.querySelector('.reader')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function handleFileUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!form.value.title.trim()) {
    form.value.title = file.name.replace(/\.[^.]+$/, '');
  }
  form.value.content = await file.text();
  uploadedFileName.value = file.name;
}

function triggerFileInput() {
  document.getElementById('novel-file-input')?.click();
}

async function submitNovel() {
  const payload = {
    title: form.value.title.trim(),
    author: form.value.author.trim(),
    content: form.value.content.trim(),
  };
  if (!payload.title || !payload.content) {
    uploadError.value = '请填写标题并上传或粘贴正文';
    return;
  }

  uploading.value = true;
  uploadError.value = '';
  try {
    const created = await api.createNovel(payload);
    form.value = { title: '', author: '', content: '' };
    showUpload.value = false;
    selectedNovel.value = created;
    await refreshAll();
  } catch (error) {
    uploadError.value = error.message || '上传失败';
  } finally {
    uploading.value = false;
  }
}

async function rate(score) {
  if (!selectedNovel.value || ratingSaving.value) return;
  const prev = selectedNovel.value.myRating;
  selectedNovel.value = { ...selectedNovel.value, myRating: score };
  ratingSaving.value = true;
  try {
    const updated = await api.rateNovel(selectedNovel.value.id, score);
    selectedNovel.value = updated;
    patchSummary(updated);
    loadRanking();
  } catch (error) {
    selectedNovel.value = { ...selectedNovel.value, myRating: prev };
    readerError.value = error.message || '评分保存失败';
  } finally {
    ratingSaving.value = false;
  }
}

function patchSummary(updated) {
  novels.value = novels.value.map((item) =>
    item.id === updated.id
      ? {
          ...item,
          averageRating: updated.averageRating,
          ratingCount: updated.ratingCount,
          myRating: updated.myRating,
        }
      : item,
  );
}

function ratingText(item) {
  if (!item || !item.ratingCount) return '暂无评分';
  return `${Number(item.averageRating || 0).toFixed(1)} / 5`;
}

function formatDate(value) {
  if (!value) return '';
  return new Date(value).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

function shortNumber(value) {
  const number = Number(value || 0);
  if (number >= 10000) return `${(number / 10000).toFixed(1)}万`;
  if (number >= 1000) return `${(number / 1000).toFixed(1)}K`;
  return String(number);
}

function coverGradient(index) {
  const gradients = [
    'linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)',
    'linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)',
    'linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%)',
    'linear-gradient(135deg, #e0c3fc 0%, #8ec5fc 100%)',
    'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
  ];
  return gradients[index % gradients.length];
}

function rankClass(rank) {
  if (rank === 1) return 'rank-1';
  if (rank === 2) return 'rank-2';
  if (rank === 3) return 'rank-3';
  return '';
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h2>小说广场</h2>
        <p>上传小说、一起阅读，并用评分把好作品推到榜首。</p>
      </div>
      <div class="page-tabs">
        <button
          type="button"
          class="page-tab"
          :class="{ active: pageTab === 'read' }"
          @click="pageTab = 'read'"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H21"/>
            <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5z"/>
          </svg>
          阅读小说
        </button>
        <button
          type="button"
          class="page-tab"
          :class="{ active: pageTab === 'ranking' }"
          @click="pageTab = 'ranking'"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27Z"/>
          </svg>
          排行榜
        </button>
      </div>
    </header>

    <!-- 阅读小说 -->
    <div v-show="pageTab === 'read'">
      <div class="read-header">
        <button class="btn-primary" type="button" @click="showUpload = !showUpload">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3">
            <path d="M12 5v14"/>
            <path d="M5 12h14"/>
          </svg>
          上传小说
        </button>
      </div>

      <transition name="fade">
        <section v-if="showUpload" class="upload-panel">
          <div class="upload-grid">
            <label>
              <span>标题</span>
              <input v-model="form.title" placeholder="小说标题" maxlength="120" />
            </label>
            <label>
              <span>作者</span>
              <input v-model="form.author" placeholder="可留空" maxlength="80" />
            </label>
          </div>
          <div class="file-upload-area" @click="triggerFileInput">
            <input id="novel-file-input" type="file" accept=".txt,text/plain" hidden @change="handleFileUpload" />
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="12" y1="18" x2="12" y2="12"/>
              <polyline points="9 15 12 12 15 15"/>
            </svg>
            <span v-if="!uploadedFileName" class="file-hint">点击选择 TXT 文件自动填入正文</span>
            <span v-else class="file-name">{{ uploadedFileName }}</span>
          </div>
          <label class="content-field">
            <span>正文</span>
            <textarea v-model="form.content" placeholder="可以粘贴正文，也可以选择 TXT 文件自动填入"></textarea>
          </label>
          <div class="upload-actions">
            <button class="btn-primary" type="button" :disabled="uploading" @click="submitNovel">
              {{ uploading ? '上传中...' : '保存到广场' }}
            </button>
            <button class="btn-ghost" type="button" @click="showUpload = false">取消</button>
            <span v-if="uploadError" class="error-text">{{ uploadError }}</span>
          </div>
        </section>
      </transition>

      <div v-if="!showUpload" class="workspace">
        <section class="library">
          <div class="section-head">
            <h2>全部小说</h2>
            <span>{{ filteredNovels.length }} 本</span>
          </div>
          <div class="search-box">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input v-model="searchQuery" placeholder="搜索标题或作者..." />
          </div>
          <div v-if="loading" class="state">加载中...</div>
          <div v-else-if="!novels.length" class="state">还没有小说，先上传一本吧</div>
          <div v-else-if="!filteredNovels.length" class="state">没有找到匹配的小说</div>
          <button
            v-for="novel in filteredNovels"
            v-else
            :key="novel.id"
            class="novel-row"
            :class="{ active: selectedNovel?.id === novel.id }"
            type="button"
            @click="openNovel(novel.id)"
          >
            <span class="novel-title">{{ novel.title }}</span>
            <span class="novel-meta">{{ novel.author || '匿名作者' }} · {{ formatDate(novel.createdAt) }}</span>
            <span class="novel-excerpt">{{ novel.excerpt }}</span>
            <span class="novel-score">{{ ratingText(novel) }} · {{ novel.ratingCount }} 人</span>
          </button>
        </section>

        <section class="reader">
          <div class="reader-head">
            <div>
              <h2>{{ selectedTitle }}</h2>
              <p>{{ selectedAuthor }}</p>
            </div>
            <div v-if="selectedNovel" class="score-box">
              <strong>{{ ratingText(selectedNovel) }}</strong>
              <span>{{ selectedNovel.ratingCount }} 人评分</span>
            </div>
          </div>

          <div v-if="detailLoading" class="state reader-state">加载正文中...</div>
          <div v-else-if="readerError" class="state reader-state error-text">{{ readerError }}</div>
          <div v-else-if="!selectedNovel" class="state reader-state">从左侧选择小说，正文会显示在这里</div>
          <article v-else class="reader-body">{{ selectedNovel.content }}</article>

          <div v-if="selectedNovel" class="rating-bar">
            <span>我的评分</span>
            <div class="stars">
              <button
                v-for="score in 5"
                :key="score"
                type="button"
                :class="{ active: selectedNovel.myRating >= score }"
                :title="`${score} 分`"
                @click="rate(score)"
              >
                ★
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- 排行榜 -->
    <div v-show="pageTab === 'ranking'">
      <section class="leaderboard-stage">
        <div class="stage-grid"></div>
        <div class="stage-content">
          <header class="stage-header">
            <div class="badge-pill">
              <span class="live-dot"></span>
              <span>Redis ZSet 实时评分榜</span>
            </div>
            <h1 class="main-title">Novel <span>Rankings</span></h1>
            <p class="subtitle">发现大家一起读、一起打分的高分小说。</p>

            <div class="stats-board">
              <div class="stat-card">
                <div class="stat-num">{{ totalNovels }}</div>
                <div class="stat-label">总小说</div>
              </div>
              <div class="stat-separator"></div>
              <div class="stat-card">
                <div class="stat-num">{{ shortNumber(totalRatings) }}</div>
                <div class="stat-label">总评分</div>
              </div>
              <div class="stat-separator"></div>
              <div class="stat-card">
                <div class="stat-num">{{ topScore }}</div>
                <div class="stat-label">最高均分</div>
              </div>
            </div>
          </header>

          <div class="controls-bar">
            <div class="tabs glass-panel">
              <button
                v-for="mode in boardModes"
                :key="mode.value"
                type="button"
                class="tab-btn"
                :class="{ active: boardMode === mode.value }"
                @click="boardMode = mode.value"
              >
                {{ mode.label }}
              </button>
            </div>
            <div class="tabs glass-panel">
              <button
                v-for="limit in boardLimits"
                :key="limit.value"
                type="button"
                class="tab-btn"
                :class="{ active: boardLimit === limit.value }"
                @click="boardLimit = limit.value"
              >
                {{ limit.label }}
              </button>
            </div>
            <button class="refresh-btn glass-panel" type="button" :disabled="rankingLoading" @click="refreshAll">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 12a9 9 0 0 1-9 9 9.8 9.8 0 0 1-6.74-2.74L3 16"/>
                <path d="M3 21v-5h5"/>
                <path d="M3 12a9 9 0 0 1 9-9 9.8 9.8 0 0 1 6.74 2.74L21 8"/>
                <path d="M16 8h5V3"/>
              </svg>
            </button>
          </div>

          <div v-if="rankingLoading && !boardItems.length" class="loading-container">
            <div class="spinner"></div>
            <p>排行榜加载中...</p>
          </div>

          <div v-else-if="boardItems.length" class="rank-list">
            <transition-group name="list-anim">
              <button
                v-for="(item, index) in boardItems"
                :key="`${boardMode}-${item.id}`"
                type="button"
                class="rank-item glass-panel"
                :class="{ 'top-three': item.rank <= 3, selected: selectedNovel?.id === item.id }"
                @click="openFromBoard(item)"
              >
                <div class="rank-index">
                  <span class="number" :class="rankClass(item.rank)">{{ item.rank }}</span>
                  <span v-if="item.rank <= 3" class="trend new">TOP</span>
                </div>

                <div class="cover-wrapper">
                  <div class="cover-img" :style="{ background: coverGradient(index) }">
                    <span class="cover-initial">{{ item.title?.charAt(0) || '书' }}</span>
                    <div class="play-overlay">
                      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H21"/>
                        <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5z"/>
                      </svg>
                    </div>
                  </div>
                  <div v-if="item.rank <= 3" class="crown-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path d="M5 17h14l1-10-5 4-3-6-3 6-5-4 1 10Zm1 2h12v2H6v-2Z"/>
                    </svg>
                  </div>
                </div>

                <div class="song-info">
                  <div class="title-row">
                    <h3 class="song-title">{{ item.title }}</h3>
                  </div>
                  <p class="artist-name">{{ item.author || '匿名作者' }}</p>
                </div>

                <div class="play-stats">
                  <div class="stat-row">
                    <svg class="icon-small" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27Z"/>
                    </svg>
                    <span>{{ ratingText(item) }}</span>
                  </div>
                  <div class="stat-row duration">{{ item.ratingCount }} 人评分</div>
                </div>

                <div class="action-btns">
                  <span class="icon-btn">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="m9 18 6-6-6-6"/>
                    </svg>
                  </span>
                </div>
              </button>
            </transition-group>
          </div>

          <div v-else class="empty-state glass-panel">
            <div class="empty-icon">
              <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H21"/>
                <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5z"/>
              </svg>
            </div>
            <h3>暂无排行榜数据</h3>
            <p>上传小说并完成评分后，这里会生成榜单。</p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page {
  animation: pageIn 0.4s var(--ease-out);
}

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.leaderboard-stage {
  position: relative;
  overflow: hidden;
  min-height: auto;
  color: #fff;
  border-radius: 10px;
  background:
    linear-gradient(135deg, rgba(112, 0, 255, 0.35), transparent 34%),
    linear-gradient(315deg, rgba(188, 0, 109, 0.34), transparent 32%),
    linear-gradient(180deg, #050511 0%, #0a0a1d 100%);
  box-shadow: 0 26px 70px rgba(5, 5, 17, 0.28);
}

.stage-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: linear-gradient(180deg, #000 45%, transparent 100%);
}

.leaderboard-stage::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(0, 242, 254, 0.14), transparent 28%, rgba(255, 255, 255, 0.06) 52%, transparent 74%),
    linear-gradient(0deg, rgba(255, 255, 255, 0.08), transparent 30%);
  opacity: 0.9;
  pointer-events: none;
}

.stage-content {
  position: relative;
  z-index: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 38px 20px 44px;
}

.stage-header {
  text-align: center;
  margin-bottom: 32px;
  animation: slideDown 0.8s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.badge-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  margin-bottom: 18px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 100px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
}

.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #00ff88;
  box-shadow: 0 0 10px #00ff88;
  animation: blink 2s infinite;
}

.main-title {
  margin: 0 0 14px;
  font-size: clamp(42px, 6vw, 72px);
  line-height: 1.1;
  font-weight: 800;
  letter-spacing: 0;
}

.main-title span {
  background: linear-gradient(135deg, #fff 0%, #a5a5a5 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.subtitle {
  margin: 0 0 34px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 17px;
}

.stats-board {
  display: inline-flex;
  align-items: center;
  padding: 20px 40px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 24px;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(20px);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
}

.stat-card {
  min-width: 100px;
  text-align: left;
}

.stat-num {
  font-size: 24px;
  font-weight: 800;
  background: linear-gradient(90deg, #00f2fe, #fff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.stat-label {
  margin-top: 4px;
  color: rgba(255, 255, 255, 0.58);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.stat-separator {
  width: 1px;
  height: 30px;
  margin: 0 30px;
  background: rgba(255, 255, 255, 0.1);
}

.controls-bar {
  display: flex;
  justify-content: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 26px;
}

.glass-panel {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.035);
  backdrop-filter: blur(16px);
}

.tabs {
  display: flex;
  gap: 4px;
  padding: 6px;
}

.tab-btn,
.refresh-btn {
  border: none;
  color: rgba(255, 255, 255, 0.62);
  background: transparent;
  cursor: pointer;
  transition: all 0.3s ease;
}

.tab-btn {
  padding: 10px 24px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 700;
}

.tab-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.055);
}

.tab-btn.active {
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(255, 255, 255, 0.12);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
}

.refresh-btn {
  width: 46px;
  height: 46px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.refresh-btn:hover {
  color: #fff;
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.08);
}

.refresh-btn:disabled {
  cursor: wait;
  opacity: 0.6;
}

.rank-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rank-item {
  width: 100%;
  display: grid;
  grid-template-columns: 60px 80px 1fr 150px 60px;
  align-items: center;
  padding: 16px;
  color: #fff;
  text-align: left;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.rank-item:hover,
.rank-item.selected {
  transform: scale(1.01);
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.085);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.22);
  z-index: 2;
}

.rank-item.top-three {
  border-color: rgba(255, 255, 255, 0.14);
}

.rank-index {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.number {
  color: rgba(255, 255, 255, 0.6);
  font-size: 20px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.rank-1 { color: #ffd700; text-shadow: 0 0 10px rgba(255, 215, 0, 0.5); font-size: 24px; }
.rank-2 { color: #e0e0e0; font-size: 22px; }
.rank-3 { color: #cd7f32; font-size: 22px; }

.trend {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.6);
}

.trend.new {
  color: #d000ff;
  font-weight: 800;
  animation: pulse 1s infinite;
}

.cover-wrapper {
  position: relative;
  width: 60px;
  height: 60px;
}

.cover-img {
  width: 100%;
  height: 100%;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.22);
}

.cover-initial {
  color: rgba(255, 255, 255, 0.42);
  font-size: 24px;
  font-weight: 900;
}

.play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  color: #fff;
  background: rgba(0, 0, 0, 0.42);
  backdrop-filter: blur(2px);
  transition: opacity 0.2s;
}

.rank-item:hover .play-overlay {
  opacity: 1;
}

.crown-icon {
  position: absolute;
  top: -9px;
  left: -7px;
  width: 22px;
  height: 22px;
  color: #ffd700;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.34));
  transform: rotate(-15deg);
}

.song-info {
  min-width: 0;
  padding-left: 20px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.song-title {
  margin: 0;
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artist-name {
  margin: 0;
  color: rgba(255, 255, 255, 0.6);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.play-stats {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 13px;
}

.stat-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
}

.duration {
  font-size: 12px;
}

.icon-small {
  width: 14px;
  height: 14px;
  opacity: 0.7;
}

.action-btns {
  display: flex;
  justify-content: flex-end;
  opacity: 0;
  transition: opacity 0.2s;
}

.rank-item:hover .action-btns {
  opacity: 1;
}

.icon-btn {
  width: 36px;
  height: 36px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 50%;
  color: #fff;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.rank-item:hover .icon-btn {
  border-color: #7000ff;
  background: #7000ff;
  box-shadow: 0 0 15px rgba(112, 0, 255, 0.4);
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  color: rgba(255, 255, 255, 0.62);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(255, 255, 255, 0.1);
  border-top-color: #7000ff;
  border-radius: 50%;
  margin-bottom: 20px;
  animation: spin 1s linear infinite;
}

.empty-state {
  color: rgba(255, 255, 255, 0.62);
  text-align: center;
  padding: 56px 20px;
}

.empty-icon {
  display: inline-flex;
  margin-bottom: 16px;
}

.empty-state h3 {
  color: #fff;
  margin-bottom: 6px;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 18px;
  margin-bottom: 18px;
}

.page-head h2 {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 0;
}

.page-head p {
  color: var(--text-secondary);
  font-size: 14px;
  margin-top: 4px;
}

.page-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.page-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
  white-space: nowrap;
}

.page-tab:hover {
  color: var(--text);
  background: var(--primary-soft);
}

.page-tab.active {
  color: #fff;
  background: var(--text);
  box-shadow: var(--shadow-md);
}

.read-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 14px;
}

.btn-primary,
.btn-ghost {
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
  white-space: nowrap;
}

.btn-primary {
  background: var(--text);
  color: #fff;
  border: none;
}

.btn-primary:hover {
  background: #0f0f23;
  box-shadow: var(--shadow-md);
}

.btn-primary:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.btn-ghost {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

.btn-ghost:hover {
  color: var(--primary);
  border-color: var(--primary-glow);
}

.upload-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 18px;
  box-shadow: var(--shadow-card);
}

.upload-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

label span {
  display: block;
  margin-bottom: 5px;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

input,
textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  outline: none;
  transition: border-color var(--duration) var(--ease), box-shadow var(--duration) var(--ease);
}

input {
  height: 38px;
  padding: 0 12px;
}

textarea {
  min-height: 170px;
  resize: vertical;
  padding: 11px 12px;
  line-height: 1.7;
}

input:focus,
textarea:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-glow);
}

.file-upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
  padding: 24px;
  border: 2px dashed var(--border);
  border-radius: 10px;
  background: var(--surface);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.file-upload-area:hover {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.file-hint {
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 600;
}

.file-name {
  color: var(--primary);
  font-size: 13px;
  font-weight: 700;
}

.content-field {
  display: block;
  margin-top: 12px;
}

.upload-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.error-text {
  color: var(--danger);
}

.workspace {
  display: grid;
  grid-template-columns: minmax(260px, 0.75fr) minmax(420px, 1.55fr);
  gap: 16px;
  align-items: start;
}

.library,
.reader {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.section-head {
  height: 54px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
}

.section-head h2,
.reader-head h2 {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 0;
}

.section-head span,
.reader-head p,
.score-box span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  height: 40px;
  border-bottom: 1px solid var(--border);
  color: var(--text-muted);
}

.search-box input {
  flex: 1;
  border: none;
  background: transparent;
  height: 100%;
  padding: 0;
  font-size: 13px;
  outline: none;
}

.state {
  min-height: 92px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  color: var(--text-muted);
  font-size: 13px;
}

.novel-row {
  width: 100%;
  border: none;
  border-bottom: 1px solid var(--border);
  background: transparent;
  text-align: left;
  cursor: pointer;
  display: grid;
  gap: 2px;
  padding: 13px 16px;
  transition: background var(--duration) var(--ease);
}

.novel-row:hover,
.novel-row.active {
  background: var(--primary-soft);
}

.novel-title {
  color: var(--text);
  font-size: 14px;
  font-weight: 800;
  word-break: break-word;
}

.novel-meta,
.novel-score {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
}

.novel-excerpt {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.reader-head {
  min-height: 72px;
  padding: 15px 18px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--border);
}

.score-box {
  min-width: 96px;
  text-align: right;
}

.score-box strong {
  display: block;
  font-size: 17px;
  font-weight: 800;
}

.reader-state {
  min-height: 420px;
}

.reader-body {
  min-height: 420px;
  max-height: calc(100vh - 260px);
  overflow: auto;
  padding: 22px 24px;
  color: #232336;
  font-size: 15px;
  line-height: 1.9;
  white-space: pre-wrap;
  word-break: break-word;
  background: linear-gradient(180deg, #fff 0%, #fbfcff 100%);
}

.rating-bar {
  min-height: 58px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  border-top: 1px solid var(--border);
}

.rating-bar span {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.stars {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.stars button {
  width: 32px;
  height: 32px;
  display: inline-grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #cbd5e1;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.stars button:hover,
.stars button.active {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes pulse {
  0% { opacity: 0.6; }
  50% { opacity: 1; }
  100% { opacity: 0.6; }
}

.list-anim-enter-active,
.list-anim-leave-active {
  transition: all 0.5s ease;
}

.list-anim-enter-from,
.list-anim-leave-to {
  opacity: 0;
  transform: translateY(30px);
}

@media (max-width: 980px) {

  .rank-item {
    grid-template-columns: 46px 64px 1fr 112px;
    gap: 10px;
    padding: 12px;
  }

  .action-btns {
    display: none;
  }

  .workspace {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 780px) {
  .page-head {
    flex-direction: column;
    align-items: stretch;
  }

  .page-tabs {
    align-self: stretch;
  }

  .page-tab {
    flex: 1;
    justify-content: center;
  }

  .reader-head,
  .rating-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .leaderboard-stage {
    min-height: auto;
  }

  .stage-content {
    padding: 28px 12px 30px;
  }

  .main-title {
    font-size: 36px;
  }

  .subtitle {
    font-size: 14px;
  }

  .stats-board {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 15px;
    padding: 20px;
  }

  .stat-card {
    width: 100%;
    text-align: center;
  }

  .stat-separator {
    width: 100%;
    height: 1px;
    margin: 0;
  }

  .controls-bar {
    justify-content: stretch;
  }

  .tabs {
    width: 100%;
    overflow-x: auto;
  }

  .tab-btn {
    flex: 1;
    padding: 10px 14px;
  }

  .rank-item {
    grid-template-columns: 36px 54px 1fr;
    gap: 8px;
  }

  .play-stats {
    grid-column: 3;
    align-items: flex-start;
    margin-top: 4px;
  }

  .cover-wrapper {
    width: 54px;
    height: 54px;
  }

  .upload-grid {
    grid-template-columns: 1fr;
  }

  .score-box {
    text-align: left;
  }

  .reader-body {
    max-height: none;
  }
}
</style>
