<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue';
import * as api from '../api';
import OpenAIIcon from '../components/OpenAIIcon.vue';

const input = ref('');
const messages = ref([]);
const loading = ref(false);
const pageLoading = ref(true);
const error = ref('');
const session = ref(null);
const newConversation = ref(false);
const messageList = ref(null);
const fileInput = ref(null);
const imageAttachments = ref([]);

const modelLabel = computed(() => 'GPT-5.5-Thinking');
const configLabel = computed(() => session.value?.configName || '默认配置');
const hasMessages = computed(() => messages.value.length > 0);

const promptStarters = [
  '帮我总结这段内容',
  '写一段更自然的中文回复',
  '解释一下这个技术问题',
  '给我三个可执行方案',
];
const supportedImageTypes = new Set(['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif']);
const maxImages = 4;
const maxImageBytes = 10 * 1024 * 1024;

async function loadSession() {
  pageLoading.value = true;
  error.value = '';
  try {
    session.value = await api.getWebChatSession();
  } catch (err) {
    error.value = err.message || '加载对话配置失败';
  } finally {
    pageLoading.value = false;
  }
}

async function scrollToBottom() {
  await nextTick();
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight;
  }
}

async function sendMessage() {
  const content = input.value.trim();
  if ((!content && !imageAttachments.value.length) || loading.value) return;

  input.value = '';
  const outgoingImages = imageAttachments.value;
  imageAttachments.value = [];
  const shouldStartNewConversation = newConversation.value || messages.value.length === 0;
  error.value = '';
  loading.value = true;
  messages.value.push({ role: 'user', content, images: outgoingImages });
  const assistant = reactive({ role: 'assistant', content: '', pending: true, streaming: true });
  const streamWriter = createStreamWriter(assistant);
  messages.value.push(assistant);
  await scrollToBottom();

  try {
    const streamPayload = {
      message: content,
      images: outgoingImages.map((image) => ({
        name: image.name,
        mediaType: image.mediaType,
        data: image.data,
        size: image.size,
        width: image.width,
        height: image.height,
      })),
      newConversation: shouldStartNewConversation,
    };
    const result = await api.streamWebChatMessage(streamPayload, {
      onDelta(delta) {
        streamWriter.append(delta);
      },
      onReplace(text) {
        streamWriter.replace(text);
      },
    });
    await streamWriter.finish();
    assistant.content = assistant.content || result?.answer || '模型没有返回文本。';
    assistant.streaming = false;
    assistant.pending = false;
    if (result) {
      session.value = {
        ...(session.value || {}),
        configId: result.configId,
        configName: result.configName,
        model: result.model,
        conversationId: result.conversationId,
        hasConversation: !!result.conversationId,
      };
    }
    newConversation.value = false;
  } catch (err) {
    streamWriter.cancel();
    assistant.streaming = false;
    assistant.pending = false;
    assistant.error = true;
    assistant.content = `请求失败：${err.message || '发送失败'}`;
  } finally {
    loading.value = false;
    await scrollToBottom();
  }
}

function createStreamWriter(message) {
  let queue = '';
  let frame = null;
  let idleResolve = null;

  const schedule = () => {
    if (!frame) {
      frame = requestAnimationFrame(writeStep);
    }
  };

  const resolveIdle = () => {
    if (idleResolve) {
      idleResolve();
      idleResolve = null;
    }
  };

  const writeStep = () => {
    frame = null;
    if (!queue) {
      resolveIdle();
      return;
    }

    const chunkSize = queue.length > 240 ? 10 : queue.length > 80 ? 7 : 4;
    message.pending = false;
    message.streaming = true;
    message.content += queue.slice(0, chunkSize);
    queue = queue.slice(chunkSize);
    scrollToBottom();
    schedule();
  };

  return {
    append(delta) {
      if (!delta) return;
      queue += delta;
      message.pending = false;
      message.streaming = true;
      schedule();
    },
    replace(text) {
      queue = '';
      message.pending = false;
      message.streaming = false;
      message.content = text || '';
      scrollToBottom();
      resolveIdle();
    },
    finish() {
      if (!queue) return Promise.resolve();
      return new Promise((resolve) => {
        idleResolve = resolve;
        schedule();
      });
    },
    cancel() {
      if (frame) {
        cancelAnimationFrame(frame);
      }
      frame = null;
      queue = '';
      message.streaming = false;
      resolveIdle();
    },
  };
}

async function startNewConversation() {
  error.value = '';
  messages.value = [];
  newConversation.value = true;
  try {
    session.value = await api.resetWebChatConversation();
  } catch (err) {
    error.value = err.message || '重置对话失败';
  }
}

function usePromptStarter(text) {
  input.value = text;
}

function openImagePicker() {
  if (!loading.value && !pageLoading.value) {
    fileInput.value?.click();
  }
}

async function handleImageSelect(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = '';
  await addImageFiles(files);
}

async function handlePaste(event) {
  const files = Array.from(event.clipboardData?.files || []).filter((file) => file.type.startsWith('image/'));
  if (files.length) {
    event.preventDefault();
    await addImageFiles(files);
  }
}

async function addImageFiles(files) {
  error.value = '';
  for (const file of files) {
    if (imageAttachments.value.length >= maxImages) {
      error.value = `最多一次发送 ${maxImages} 张图片`;
      break;
    }
    if (!supportedImageTypes.has(file.type)) {
      error.value = '仅支持 PNG、JPEG、WebP 或 GIF 图片';
      continue;
    }
    if (file.size > maxImageBytes) {
      error.value = '单张图片不能超过 10 MB';
      continue;
    }
    try {
      imageAttachments.value.push(await imageFileToAttachment(file));
    } catch (err) {
      error.value = err.message || '图片读取失败';
    }
  }
}

function removeImage(index) {
  imageAttachments.value.splice(index, 1);
}

async function imageFileToAttachment(file) {
  const dataUrl = await readFileAsDataUrl(file);
  const { width, height } = await readImageSize(dataUrl);
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    name: file.name || 'image',
    mediaType: file.type,
    size: file.size,
    width,
    height,
    data: dataUrl,
    previewUrl: dataUrl,
  };
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('图片读取失败'));
    reader.readAsDataURL(file);
  });
}

function readImageSize(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight });
    image.onerror = () => reject(new Error('无法识别图片尺寸'));
    image.src = src;
  });
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
      const language = fence[1] || '';
      const codeLines = [];
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
    while (
      index < lines.length
      && lines[index].trim()
      && !isBlockBoundary(lines, index)
    ) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    blocks.push(`<p>${renderInlineMarkdown(paragraphLines.join('\n')).replace(/\n/g, '<br>')}</p>`);
  }

  return blocks.join('');
}

function renderCodeBlock(code, language = '') {
  const label = language ? escapeHtml(language) : 'code';
  return `
    <div class="code-block">
      <div class="code-header"><span>${label}</span></div>
      <pre><code>${escapeHtml(code)}</code></pre>
    </div>
  `;
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
      if (match.startsWith('!')) {
        return stash(`<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`);
      }
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
  const items = lines.map((line) => {
    const unordered = line.match(/^(\s*)([-*+])\s+(\[[ xX]\]\s+)?(.+)$/);
    if (unordered) {
      return {
        indent: unordered[1].length,
        ordered: false,
        checked: unordered[3] ? /x/i.test(unordered[3]) : null,
        text: unordered[4],
      };
    }
    const ordered = line.match(/^(\s*)\d+[.)]\s+(.+)$/);
    return {
      indent: ordered[1].length,
      ordered: true,
      checked: null,
      text: ordered[2],
    };
  });

  let html = '';
  let index = 0;
  while (index < items.length) {
    const rendered = renderListAt(items, index, items[index].indent, items[index].ordered);
    html += rendered.html;
    index = rendered.index;
  }
  return html;
}

function renderListAt(items, start, indent, ordered) {
  const tag = ordered ? 'ol' : 'ul';
  let html = `<${tag}>`;
  let index = start;
  while (index < items.length) {
    const item = items[index];
    if (item.indent < indent || item.ordered !== ordered) break;
    if (item.indent > indent) {
      const nested = renderListAt(items, index, item.indent, item.ordered);
      html += nested.html;
      index = nested.index;
      continue;
    }

    const checkbox = item.checked === null
      ? ''
      : `<input type="checkbox" disabled ${item.checked ? 'checked' : ''}>`;
    let content = `${checkbox}${renderInlineMarkdown(item.text)}`;
    index += 1;
    while (index < items.length && items[index].indent > indent) {
      const nested = renderListAt(items, index, items[index].indent, items[index].ordered);
      content += nested.html;
      index = nested.index;
    }
    html += `<li>${content}</li>`;
  }
  html += `</${tag}>`;
  return { html, index };
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
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|');
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

function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    if (!loading.value && !pageLoading.value) {
      sendMessage();
    }
  }
}

onMounted(loadSession);
</script>

<template>
  <div class="chat-page" :class="{ 'is-empty': !hasMessages }">
    <header class="chat-topbar">
      <button class="icon-btn" :disabled="loading" title="新建对话" aria-label="新建对话" @click="startNewConversation">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
          <path d="M12 5v14" />
          <path d="M5 12h14" />
        </svg>
      </button>

      <div class="model-chip" aria-label="当前模型">
        <span>{{ modelLabel }}</span>
      </div>

      <div class="config-pill">
        <span class="status-dot"></span>
        <span>{{ pageLoading ? '加载中' : configLabel }}</span>
      </div>
    </header>

    <section ref="messageList" class="conversation" aria-live="polite">
      <div v-if="pageLoading" class="welcome-panel">
        <div class="mark">
          <OpenAIIcon />
        </div>
        <h1>正在连接模型</h1>
        <p>稍等一下，马上就好。</p>
      </div>

      <div v-else-if="!messages.length" class="welcome-panel">
        <div class="mark">
          <OpenAIIcon />
        </div>
        <h1>今天想聊点什么？</h1>
        <p>选择一个开头，或者直接输入你的问题。</p>
        <div class="starter-grid">
          <button
            v-for="starter in promptStarters"
            :key="starter"
            type="button"
            class="starter"
            @click="usePromptStarter(starter)"
          >
            {{ starter }}
          </button>
        </div>
      </div>

      <div v-else class="message-stack">
        <article
          v-for="(message, index) in messages"
          :key="index"
          class="message-row"
          :class="[message.role, { pending: message.pending, error: message.error }]"
        >
          <div v-if="message.role === 'assistant'" class="avatar" aria-hidden="true">
            <OpenAIIcon v-if="message.role === 'assistant'" />
          </div>

          <div class="message-body">
            <div v-if="message.role === 'assistant'" class="message-name">ChatGPT</div>
            <div class="bubble">
              <div v-if="message.images?.length" class="message-images">
                <img
                  v-for="image in message.images"
                  :key="image.id"
                  :src="image.previewUrl"
                  :alt="image.name"
                />
              </div>
              <span v-if="message.pending" class="typing">
                <i></i>
                <i></i>
                <i></i>
              </span>
              <span v-else class="rendered-content" v-html="renderMessageContent(message.content)"></span>
            </div>
          </div>
        </article>
      </div>
    </section>

    <footer class="composer-wrap">
      <div v-if="error" class="error-line">{{ error }}</div>
      <div v-if="imageAttachments.length" class="image-preview-strip">
        <div v-for="(image, index) in imageAttachments" :key="image.id" class="image-preview">
          <img :src="image.previewUrl" :alt="image.name" />
          <button type="button" title="移除图片" aria-label="移除图片" @click="removeImage(index)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
      </div>
      <form class="composer" @submit.prevent="sendMessage">
        <input
          ref="fileInput"
          class="file-input"
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          multiple
          @change="handleImageSelect"
        />
        <button type="button" class="attach-btn" :disabled="loading || pageLoading" title="添加图片" aria-label="添加图片" @click="openImagePicker">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
            <path d="M21.44 11.05 12.25 20.24a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 1 1-2.83-2.83l8.49-8.48" />
          </svg>
        </button>
        <textarea
          v-model="input"
          rows="1"
          :disabled="pageLoading"
          placeholder="给 ChatGPT 发送消息"
          @keydown="handleKeydown"
          @paste="handlePaste"
        ></textarea>
        <button type="submit" class="send-btn" :disabled="loading || pageLoading || (!input.trim() && !imageAttachments.length)" title="发送" aria-label="发送">
          <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M12 19V5" />
            <path d="m5 12 7-7 7 7" />
          </svg>
          <span v-else class="spinner"></span>
        </button>
      </form>
      <p class="fine-print">内容由模型生成，请核对重要信息。</p>
    </footer>
  </div>
</template>

<style scoped>
.chat-page {
  --chat-text: #171717;
  --chat-muted: #6b7280;
  --chat-soft: #f7f7f8;
  --chat-line: rgba(0, 0, 0, 0.08);
  --chat-user: #f4f4f4;
  --chat-accent: #10a37f;
  min-height: calc(100vh - 104px);
  margin: -16px -16px -24px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  background: #fff;
  color: var(--chat-text);
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.06);
}

.chat-topbar {
  min-height: 58px;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 9px 16px;
  border-bottom: 1px solid var(--chat-line);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(16px);
  z-index: 2;
}

.icon-btn,
.composer button {
  border: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background var(--duration) var(--ease), color var(--duration) var(--ease), transform var(--duration) var(--ease), opacity var(--duration) var(--ease);
}

.icon-btn {
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: transparent;
  color: #444;
}

.icon-btn:hover:not(:disabled) {
  background: #f1f1f1;
}

.icon-btn:disabled,
.composer button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.model-chip {
  justify-self: center;
  max-width: min(430px, 100%);
  height: 38px;
  padding: 0 12px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #202123;
  font-weight: 700;
  font-size: 15px;
}

.model-chip span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.config-pill {
  max-width: 210px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--chat-line);
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--chat-muted);
  background: #fff;
  font-size: 12px;
  white-space: nowrap;
}

.config-pill span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--chat-accent);
  box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.12);
  flex-shrink: 0;
}

.conversation {
  min-height: 0;
  overflow-y: auto;
  background:
    linear-gradient(#fff, #fff) padding-box,
    linear-gradient(180deg, rgba(247, 247, 248, 0.7), rgba(255, 255, 255, 0)) border-box;
}

.welcome-panel {
  min-height: 100%;
  width: min(760px, calc(100% - 32px));
  margin: 0 auto;
  padding: 11vh 0 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.mark {
  width: 48px;
  height: 48px;
  margin-bottom: 22px;
  border-radius: 50%;
  background: #101010;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
}

.mark svg {
  width: 25px;
  height: 25px;
}

.welcome-panel h1 {
  font-size: 30px;
  font-weight: 750;
  letter-spacing: 0;
  color: #202123;
}

.welcome-panel p {
  margin-top: 8px;
  color: var(--chat-muted);
}

.starter-grid {
  width: min(620px, 100%);
  margin-top: 28px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.starter {
  min-height: 46px;
  padding: 12px 14px;
  border: 1px solid var(--chat-line);
  border-radius: 8px;
  background: #fff;
  color: #343541;
  text-align: left;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
  transition: border-color var(--duration) var(--ease), background var(--duration) var(--ease), transform var(--duration) var(--ease);
}

.starter:hover {
  background: var(--chat-soft);
  border-color: rgba(0, 0, 0, 0.16);
  transform: translateY(-1px);
}

.message-stack {
  width: min(860px, calc(100% - 36px));
  margin: 0 auto;
  padding: 34px 0 150px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.message-row {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 14px;
  align-items: flex-start;
}

.message-row.user {
  display: flex;
  justify-content: flex-end;
}

.message-row.user .message-body {
  align-items: flex-end;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #111827;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12);
}

.avatar svg {
  width: 18px;
  height: 18px;
}

.user .avatar {
  background: #ececf1;
  color: #343541;
}

.message-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 7px;
}

.message-name {
  color: #343541;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.bubble {
  max-width: min(680px, 100%);
  padding: 0;
  color: #202123;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.78;
  font-size: 15px;
}

.rendered-content {
  display: block;
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
  margin: 20px 0 9px;
  color: #171717;
  font-weight: 750;
  line-height: 1.25;
}

.rendered-content :deep(h1) {
  font-size: 1.45em;
}

.rendered-content :deep(h2) {
  font-size: 1.28em;
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

.rendered-content :deep(li > ul),
.rendered-content :deep(li > ol) {
  margin: 4px 0 0;
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

.user .bubble {
  padding: 10px 14px;
  border-radius: 18px;
  background: var(--chat-user);
  line-height: 1.65;
}

.message-images {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
  width: min(360px, 70vw);
  margin-bottom: 8px;
}

.message-images img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: #fff;
}

.assistant.error .bubble {
  color: var(--danger);
}

.typing {
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.typing i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #9ca3af;
  animation: pulse 1.2s infinite ease-in-out;
}

.typing i:nth-child(2) {
  animation-delay: 0.15s;
}

.typing i:nth-child(3) {
  animation-delay: 0.3s;
}

.composer-wrap {
  width: min(820px, calc(100% - 34px));
  justify-self: center;
  padding: 0 0 16px;
  z-index: 3;
}

.image-preview-strip {
  margin: 0 8px 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.image-preview {
  width: 76px;
  height: 76px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.1);
  background: #f7f7f8;
  position: relative;
}

.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.image-preview button {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.composer {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) 38px;
  align-items: end;
  gap: 10px;
  padding: 10px 10px 10px 16px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 26px;
  background: #fff;
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.1);
}

.composer:focus-within {
  border-color: rgba(0, 0, 0, 0.22);
  box-shadow: 0 14px 38px rgba(15, 23, 42, 0.13);
}

.file-input {
  display: none;
}

.composer textarea {
  width: 100%;
  max-height: 190px;
  min-height: 38px;
  padding: 8px 0;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: #202123;
  line-height: 1.55;
}

.composer textarea::placeholder {
  color: #8e8ea0;
}

.attach-btn,
.send-btn {
  width: 38px;
  height: 38px;
  border-radius: 50%;
}

.attach-btn {
  background: transparent;
  color: #6b7280;
}

.attach-btn:hover:not(:disabled) {
  background: #f1f1f1;
  color: #202123;
}

.send-btn {
  background: #111;
  color: #fff;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: #000;
}

.error-line {
  margin: 0 10px 8px;
  color: var(--danger);
  font-size: 13px;
}

.fine-print {
  margin-top: 8px;
  color: #8e8ea0;
  text-align: center;
  font-size: 12px;
}

.spinner {
  width: 17px;
  height: 17px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes pulse {
  0%,
  80%,
  100% {
    opacity: 0.28;
    transform: translateY(0);
  }

  40% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

@media (max-width: 900px) {
  .chat-page {
    margin: -8px -8px -16px;
  }

  .chat-topbar {
    grid-template-columns: 40px minmax(0, 1fr);
  }

  .config-pill {
    display: none;
  }
}

@media (max-width: 760px) {
  .chat-page {
    min-height: calc(100vh - 88px);
    margin: -4px -6px -18px;
    border-left: none;
    border-right: none;
  }

  .chat-topbar {
    padding: 8px 10px;
  }

  .model-chip {
    justify-self: start;
    font-size: 14px;
  }

  .welcome-panel {
    width: min(100% - 24px, 620px);
    padding-top: 6vh;
  }

  .welcome-panel h1 {
    font-size: 24px;
  }

  .starter-grid {
    grid-template-columns: 1fr;
  }

  .message-stack {
    width: calc(100% - 24px);
    padding-top: 24px;
  }

  .message-row,
  .message-row.user {
    grid-template-columns: 28px minmax(0, 1fr);
    gap: 10px;
  }

  .message-row.user {
    display: flex;
    justify-content: flex-end;
  }

  .message-row.user .message-body {
    align-items: flex-end;
  }

  .avatar {
    width: 28px;
    height: 28px;
  }

  .bubble {
    font-size: 14px;
  }

  .user .bubble {
    border-radius: 16px;
  }

  .composer-wrap {
    width: calc(100% - 20px);
  }
}
</style>
