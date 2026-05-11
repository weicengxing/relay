<script setup>
import { computed, onMounted, ref } from 'vue';
import * as api from '../api';
import OpenAIIcon from '../components/OpenAIIcon.vue';

const files = ref([]);
const selected = ref(null);
const turns = ref([]);
const page = ref(1);
const size = 20;
const sourcePreviewLimit = 15;
const total = ref(0);
const hasMore = ref(false);
const loading = ref(false);
const loadingDetail = ref(false);
const error = ref('');

const selectedTitle = computed(() => {
  if (!selected.value) return '选择一个历史文件';
  return `会话记录 ${String(selected.value.sequence).padStart(6, '0')}`;
});

async function loadHistory({ reset = true } = {}) {
  if (loading.value) return;
  loading.value = true;
  error.value = '';
  const nextPage = reset ? 1 : page.value + 1;
  try {
    const result = await api.getWebChatHistory({ page: nextPage, size });
    const items = result.items || [];
    files.value = reset ? items : [...files.value, ...items];
    page.value = result.page || nextPage;
    total.value = result.total || files.value.length;
    hasMore.value = Boolean(result.hasMore);
    if (reset && items.length) {
      await openHistory(items[0]);
    } else if (reset) {
      selected.value = null;
      turns.value = [];
    }
  } catch (err) {
    error.value = err.message || '加载聊天历史失败';
  } finally {
    loading.value = false;
  }
}

async function openHistory(file) {
  selected.value = file;
  turns.value = [];
  loadingDetail.value = true;
  error.value = '';
  try {
    const detail = await api.getWebChatHistoryDetail(file.id);
    selected.value = detail.file || file;
    turns.value = detail.turns || [];
  } catch (err) {
    error.value = err.message || '读取历史文件失败';
  } finally {
    loadingDetail.value = false;
  }
}

function formatTime(value) {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch {
    return '';
  }
}

function formatSize(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

function imageUrl(image = {}) {
  return api.resolveApiUrl(image.data || image.url || image.previewUrl || '');
}

function imageLink(image = {}) {
  return image.pageUrl || imageUrl(image);
}

function visibleSources(sources = [], expanded = false) {
  return expanded ? sources : sources.slice(0, sourcePreviewLimit);
}

function hasHiddenSources(sources = [], expanded = false) {
  return !expanded && sources.length > sourcePreviewLimit;
}

function renderMessageContent(content = '') {
  return renderMarkdownBlocks(String(content).replace(/\r\n/g, '\n').trim());
}

function renderMarkdownBlocks(markdown) {
  if (!markdown) return '';
  const lines = markdown.split('\n');
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^```([\w-]*)\s*$/);
    if (fence) {
      const codeLines = [];
      const language = fence[1] || '';
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(renderCodeBlock(codeLines.join('\n'), language));
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = Math.min(heading[1].length, 4);
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2].trim())}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
      blocks.push('<hr>');
      index += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quoteLines = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, ''));
        index += 1;
      }
      blocks.push(`<blockquote>${renderMarkdownBlocks(quoteLines.join('\n'))}</blockquote>`);
      continue;
    }

    if (isTableStart(lines, index)) {
      const tableLines = [lines[index], lines[index + 1]];
      index += 2;
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        tableLines.push(lines[index]);
        index += 1;
      }
      blocks.push(renderTable(tableLines));
      continue;
    }

    if (isListLine(line)) {
      const listLines = [];
      while (index < lines.length && isListLine(lines[index])) {
        listLines.push(lines[index]);
        index += 1;
      }
      blocks.push(renderListGroup(listLines));
      continue;
    }

    const paragraphLines = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockBoundary(lines, index)) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    blocks.push(`<p>${renderInlineMarkdown(paragraphLines.join('\n')).replace(/\n/g, '<br>')}</p>`);
  }

  return blocks.join('');
}

function renderCodeBlock(code, language = '') {
  const label = language ? escapeHtml(language) : 'code';
  return `<div class="code-block"><div class="code-header"><span>${label}</span></div><pre><code>${escapeHtml(code)}</code></pre></div>`;
}

function renderInlineMarkdown(text) {
  const placeholders = [];
  const stash = (html) => {
    const key = `\u0000MD${placeholders.length}\u0000`;
    placeholders.push([key, html]);
    return key;
  };

  let source = String(text)
    .replace(/`([^`\n]+)`/g, (_, code) => stash(`<code>${escapeHtml(code)}</code>`))
    .replace(/!?\[([^\]\n]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (match, label, url) => {
      const safeUrl = sanitizeUrl(url);
      if (!safeUrl) return escapeHtml(label);
      return stash(`<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`);
    });

  let html = escapeHtml(source)
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
    .replace(/~~([^~\n]+)~~/g, '<del>$1</del>')
    .replace(/(^|[^\*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>');

  placeholders.forEach(([key, value]) => {
    html = html.replaceAll(key, value);
  });
  return html;
}

function isBlockBoundary(lines, index) {
  const line = lines[index];
  return /^```/.test(line)
    || /^(#{1,6})\s+/.test(line)
    || /^\s*>\s?/.test(line)
    || isListLine(line)
    || isTableStart(lines, index)
    || /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/.test(line);
}

function isListLine(line) {
  return /^(\s*)([-*+])\s+(\[[ xX]\]\s+)?(.+)$/.test(line)
    || /^(\s*)\d+[.)]\s+(.+)$/.test(line);
}

function renderListGroup(lines) {
  let ordered = /^\s*\d+[.)]\s+/.test(lines[0]);
  let tag = ordered ? 'ol' : 'ul';
  let html = `<${tag}>`;
  for (const line of lines) {
    const nextOrdered = /^\s*\d+[.)]\s+/.test(line);
    if (nextOrdered !== ordered) {
      html += `</${tag}>`;
      ordered = nextOrdered;
      tag = ordered ? 'ol' : 'ul';
      html += `<${tag}>`;
    }
    const unordered = line.match(/^\s*[-*+]\s+(\[[ xX]\]\s+)?(.+)$/);
    const orderedMatch = line.match(/^\s*\d+[.)]\s+(.+)$/);
    const checked = unordered?.[1] ? /x/i.test(unordered[1]) : null;
    const text = unordered ? unordered[2] : orderedMatch?.[1] || line;
    const checkbox = checked === null ? '' : `<input type="checkbox" disabled ${checked ? 'checked' : ''}>`;
    html += `<li>${checkbox}${renderInlineMarkdown(text)}</li>`;
  }
  return `${html}</${tag}>`;
}

function isTableStart(lines, index) {
  return Boolean(
    lines[index]?.includes('|')
    && lines[index + 1]
    && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index + 1]),
  );
}

function renderTable(lines) {
  const headers = splitTableRow(lines[0]);
  const alignments = splitTableRow(lines[1]).map((cell) => {
    const value = cell.trim();
    if (value.startsWith(':') && value.endsWith(':')) return 'center';
    if (value.endsWith(':')) return 'right';
    return 'left';
  });
  const rows = lines.slice(2).map(splitTableRow);
  const head = headers
    .map((cell, index) => `<th class="align-${alignments[index] || 'left'}">${renderInlineMarkdown(cell.trim())}</th>`)
    .join('');
  const body = rows
    .map((row) => `<tr>${row.map((cell, index) => `<td class="align-${alignments[index] || 'left'}">${renderInlineMarkdown(cell.trim())}</td>`).join('')}</tr>`)
    .join('');
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function splitTableRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|');
}

function sanitizeUrl(url) {
  const value = String(url || '').trim();
  if (/^(https?:|mailto:)/i.test(value)) {
    return escapeHtml(value);
  }
  return '';
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

onMounted(() => loadHistory());
</script>

<template>
  <div class="history-page">
    <aside class="history-list">
      <header class="panel-head">
        <div>
          <h1>聊天历史</h1>
          <p>{{ total }} 个记录文件</p>
        </div>
        <button type="button" :disabled="loading" title="刷新" aria-label="刷新" @click="loadHistory()">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
            <path d="M21 12a9 9 0 1 1-2.64-6.36"/>
            <path d="M21 3v6h-6"/>
          </svg>
        </button>
      </header>

      <div v-if="error" class="error">{{ error }}</div>
      <div v-if="loading && !files.length" class="state">加载中...</div>
      <div v-else-if="!files.length" class="state">还没有记录，先发起一次对话吧</div>

      <div v-else class="file-list">
        <button
          v-for="file in files"
          :key="file.id"
          type="button"
          class="file-item"
          :class="{ active: selected?.id === file.id }"
          @click="openHistory(file)"
        >
          <span class="file-name">{{ String(file.sequence).padStart(6, '0') }}.jsonl</span>
          <span class="file-meta">{{ file.turnCount }} 轮 · {{ formatSize(file.sizeBytes) }}</span>
          <span class="file-time">{{ formatTime(file.updatedAt) }}</span>
        </button>
        <button v-if="hasMore" class="load-more" type="button" :disabled="loading" @click="loadHistory({ reset: false })">
          {{ loading ? '加载中...' : '加载更多' }}
        </button>
      </div>
    </aside>

    <section class="history-detail">
      <header class="detail-head">
        <div class="title-row">
          <span class="mark"><OpenAIIcon /></span>
          <div>
            <h2>{{ selectedTitle }}</h2>
            <p v-if="selected">{{ selected.objectKey }}</p>
            <p v-else>对话会按用户分文件保存到 GitHub 仓库</p>
          </div>
        </div>
      </header>

      <div v-if="loadingDetail" class="state detail-state">读取中...</div>
      <div v-else-if="!selected" class="state detail-state">从左侧选择记录文件</div>
      <div v-else-if="!turns.length" class="state detail-state">这个文件暂时没有可展示的记录</div>

      <div v-else class="turns">
        <article v-for="(turn, index) in turns" :key="`${turn.createdAt}-${index}`" class="turn">
          <div class="turn-time">{{ formatTime(turn.createdAt) }} · {{ turn.model || 'model' }}</div>

          <div class="message user">
            <div class="bubble">
              <div v-if="turn.images?.length" class="images">
                <a
                  v-for="(image, imageIndex) in turn.images"
                  :key="imageIndex"
                  :href="imageLink(image)"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img
                    :src="imageUrl(image)"
                    :alt="image.name || 'image'"
                  />
                </a>
              </div>
              <div class="rendered-content user-rendered" v-html="renderMessageContent(turn.userMessage || '（仅图片消息）')"></div>
            </div>
          </div>

          <div class="message assistant">
            <span class="avatar"><OpenAIIcon /></span>
            <div class="bubble">
              <div v-if="turn.assistantImages?.length" class="images">
                <a
                  v-for="(image, imageIndex) in turn.assistantImages"
                  :key="image.id || imageIndex"
                  :href="imageLink(image)"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img
                    :src="imageUrl(image)"
                    :alt="image.name || 'image'"
                  />
                </a>
              </div>
              <div class="rendered-content" v-html="renderMessageContent(turn.assistantAnswer || '模型没有返回文本。')"></div>
              <div v-if="turn.assistantSources?.length" class="sources">
                <a
                  v-for="source in visibleSources(turn.assistantSources, turn.sourcesExpanded)"
                  :key="source.url"
                  :href="source.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  :title="source.snippet || source.title"
                >
                  <span>{{ source.attribution || source.title || source.url }}</span>
                </a>
                <button
                  v-if="hasHiddenSources(turn.assistantSources, turn.sourcesExpanded)"
                  type="button"
                  class="source-more"
                  title="显示全部来源"
                  aria-label="显示全部来源"
                  @click="turn.sourcesExpanded = true"
                >
                  ...
                </button>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.history-page {
  min-height: calc(100vh - 104px);
  display: grid;
  grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
  gap: 16px;
  margin: -8px -8px -16px;
}

.history-list,
.history-detail {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  min-width: 0;
  overflow: hidden;
  box-shadow: 0 14px 36px rgba(15, 23, 42, 0.05);
}

.history-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel-head,
.detail-head {
  padding: 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-head h1,
.detail-head h2 {
  margin: 0;
  color: #202123;
  font-size: 18px;
  font-weight: 750;
}

.panel-head p,
.detail-head p {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 12px;
  word-break: break-all;
}

.panel-head button {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 8px;
  background: #f7f7f8;
  color: #4b5563;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.file-list {
  padding: 10px;
  overflow: auto;
}

.file-item {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #202123;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-item:hover,
.file-item.active {
  background: #f4f4f4;
}

.file-name {
  font-size: 14px;
  font-weight: 700;
}

.file-meta,
.file-time {
  color: #6b7280;
  font-size: 12px;
}

.history-detail {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}

.title-row {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.mark,
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #111827;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.mark svg,
.avatar svg {
  width: 18px;
  height: 18px;
}

.detail-head a {
  flex-shrink: 0;
  color: #0b57d0;
  font-size: 13px;
  font-weight: 600;
}

.turns {
  padding: 22px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.turn {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.turn-time {
  color: #8e8ea0;
  font-size: 12px;
  text-align: center;
}

.message {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.message.user {
  justify-content: flex-end;
}

.bubble {
  max-width: min(720px, 86%);
  color: #202123;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.user .bubble {
  padding: 10px 14px;
  border-radius: 18px;
  background: #f4f4f4;
}

.assistant .bubble {
  padding-top: 2px;
}

.rendered-content {
  white-space: normal;
}

.rendered-content :deep(p) {
  margin: 0 0 12px;
}

.rendered-content :deep(p:last-child),
.rendered-content :deep(ul:last-child),
.rendered-content :deep(ol:last-child),
.rendered-content :deep(blockquote:last-child),
.rendered-content :deep(.table-wrap:last-child),
.rendered-content :deep(.code-block:last-child) {
  margin-bottom: 0;
}

.rendered-content :deep(h1),
.rendered-content :deep(h2),
.rendered-content :deep(h3),
.rendered-content :deep(h4) {
  margin: 18px 0 8px;
  color: #171717;
  font-weight: 750;
  line-height: 1.25;
}

.rendered-content :deep(h1) {
  font-size: 1.42em;
}

.rendered-content :deep(h2) {
  font-size: 1.25em;
}

.rendered-content :deep(h3),
.rendered-content :deep(h4) {
  font-size: 1.08em;
}

.rendered-content :deep(strong) {
  font-weight: 750;
}

.rendered-content :deep(em) {
  font-style: italic;
}

.rendered-content :deep(del) {
  color: #6b7280;
}

.rendered-content :deep(a) {
  color: #0b57d0;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.rendered-content :deep(ul),
.rendered-content :deep(ol) {
  margin: 0 0 12px;
  padding-left: 24px;
}

.rendered-content :deep(li) {
  margin: 4px 0;
  padding-left: 2px;
}

.rendered-content :deep(input[type='checkbox']) {
  width: 14px;
  height: 14px;
  margin: 0 7px 0 -21px;
  vertical-align: -2px;
  accent-color: #111;
}

.rendered-content :deep(blockquote) {
  margin: 0 0 12px;
  padding: 2px 0 2px 14px;
  border-left: 3px solid #d1d5db;
  color: #4b5563;
}

.rendered-content :deep(hr) {
  height: 1px;
  margin: 18px 0;
  border: none;
  background: rgba(0, 0, 0, 0.12);
}

.rendered-content :deep(code) {
  padding: 2px 5px;
  border-radius: 5px;
  background: #f1f1f1;
  font-family: ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace;
  font-size: 0.92em;
}

.rendered-content :deep(.code-block) {
  margin: 10px 0;
  overflow: hidden;
  border-radius: 8px;
  background: #171717;
}

.rendered-content :deep(.code-header) {
  min-height: 34px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: #2f2f2f;
  color: #d1d5db;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace;
}

.rendered-content :deep(pre) {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  background: #171717;
  color: #f7f7f8;
  white-space: pre;
}

.rendered-content :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
}

.rendered-content :deep(.table-wrap) {
  width: 100%;
  margin: 12px 0;
  overflow-x: auto;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
}

.rendered-content :deep(table) {
  width: 100%;
  min-width: 420px;
  border-collapse: collapse;
  font-size: 14px;
  white-space: normal;
}

.rendered-content :deep(th),
.rendered-content :deep(td) {
  padding: 9px 11px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  text-align: left;
  vertical-align: top;
}

.rendered-content :deep(th) {
  background: #f7f7f8;
  font-weight: 700;
}

.rendered-content :deep(tr:last-child td) {
  border-bottom: none;
}

.rendered-content :deep(.align-center) {
  text-align: center;
}

.rendered-content :deep(.align-right) {
  text-align: right;
}

.user-rendered :deep(p) {
  margin-bottom: 0;
}

.images {
  width: min(360px, 70vw);
  margin-bottom: 8px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 8px;
}

.images a {
  display: block;
  min-width: 0;
}

.images img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.08);
}

.sources {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sources a,
.source-more {
  max-width: 220px;
  min-height: 28px;
  padding: 5px 8px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  background: #f7f7f8;
  color: #4b5563;
  font-size: 12px;
  line-height: 1.35;
  text-decoration: none;
}

.source-more {
  cursor: pointer;
  font-weight: 700;
  min-width: 34px;
}

.sources a:hover,
.source-more:hover {
  background: #f1f1f1;
  color: #202123;
}

.sources span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state,
.error {
  min-height: 120px;
  padding: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  font-size: 13px;
  text-align: center;
}

.error {
  min-height: auto;
  color: #b91c1c;
}

.detail-state {
  min-height: 420px;
}

.load-more {
  width: 100%;
  margin-top: 8px;
  padding: 10px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  background: #fff;
  color: #4b5563;
  cursor: pointer;
}

@media (max-width: 900px) {
  .history-page {
    grid-template-columns: 1fr;
  }

  .history-list {
    max-height: 320px;
  }
}
</style>
