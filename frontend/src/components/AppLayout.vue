<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useAuthStore } from '../stores/auth';
import { useRouter, useRoute } from 'vue-router';
import * as api from '../api';
import OpenAIIcon from './OpenAIIcon.vue';

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const announcements = ref([]);
const announcementBadge = ref(0);
const announcementUnread = ref(0);
const announcementOpen = ref(false);
const newbieGuideOpen = ref(false);
const guideCopyStatus = ref('');
const announcementLoading = ref(false);
const announcementError = ref('');
let stopBalanceStream = null;
let balanceRetryTimer = null;
let guideCopyTimer = null;
let disposed = false;
let balanceRetryDelay = 3000;

const displayBadge = computed(() => (announcementBadge.value > 99 ? '99+' : String(announcementBadge.value)));
const guideSnippets = {
  codexConfig: `model_provider = "relay"
model = "gpt-5.5"
model_reasoning_effort = "medium"

[model_providers]
[model_providers.relay]
name = "Relay"
requires_openai_auth = true
base_url = "https://api.relaywei.ccwu.cc/v1"
wire_api = "responses"`,
  codexAuth: `{
  "OPENAI_API_KEY": "relay_xxxxxxxxxxxxxxxx"
}`,
  claudeWindows: `$env:ANTHROPIC_BASE_URL="https://api.relaywei.ccwu.cc/v1"
$env:ANTHROPIC_AUTH_TOKEN="relay_xxxxxxxxxxxxxxxx"
$env:ANTHROPIC_MODEL="mimo-v2.5-pro"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL="mimo-v2.5-pro"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL="mimo-v2.5-pro"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL="mimo-v2.5-pro"`,
  claudeUnix: `export ANTHROPIC_BASE_URL="https://api.relaywei.ccwu.cc/v1"
export ANTHROPIC_AUTH_TOKEN="relay_xxxxxxxxxxxxxxxx"
export ANTHROPIC_MODEL="mimo-v2.5-pro"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="mimo-v2.5-pro"
export ANTHROPIC_DEFAULT_OPUS_MODEL="mimo-v2.5-pro"
export ANTHROPIC_DEFAULT_SONNET_MODEL="mimo-v2.5-pro"`,
};

function handleLogout() {
  auth.logout();
  router.push('/login');
}

function applyAnnouncementInbox(data) {
  announcements.value = data?.announcements || [];
  announcementUnread.value = Number(data?.unreadCount || 0);
  announcementBadge.value = Number(data?.badgeCount || 0);
}

async function loadAnnouncements() {
  announcementLoading.value = true;
  announcementError.value = '';
  try {
    applyAnnouncementInbox(await api.getAnnouncements());
  } catch (error) {
    announcementError.value = error.message || '公告加载失败';
  } finally {
    announcementLoading.value = false;
  }
}

async function refreshBalanceQuietly() {
  try {
    await auth.refreshBalance();
  } catch (error) {
    if (isAuthGone(error)) {
      endExpiredSession();
    }
  }
}

function clearBalanceRetry() {
  if (balanceRetryTimer) {
    clearTimeout(balanceRetryTimer);
    balanceRetryTimer = null;
  }
}

function startBalanceStream() {
  if (disposed || stopBalanceStream || !auth.isLoggedIn) {
    return;
  }

  stopBalanceStream = api.streamBalanceUpdates({
    onBalance(payload) {
      if (payload?.balance !== undefined) {
        auth.setBalance(payload.balance);
        balanceRetryDelay = 3000;
      }
    },
    onClose() {
      handleBalanceStreamStopped();
    },
    onError(error) {
      if (isAuthGone(error)) {
        endExpiredSession();
        return;
      }
      handleBalanceStreamStopped();
    },
  });
}

function handleBalanceStreamStopped() {
  if (disposed || !auth.isLoggedIn) {
    return;
  }
  if (stopBalanceStream) {
    stopBalanceStream();
    stopBalanceStream = null;
  }
  clearBalanceRetry();
  const retryDelay = balanceRetryDelay;
  balanceRetryDelay = Math.min(balanceRetryDelay * 2, 30000);
  balanceRetryTimer = setTimeout(startBalanceStream, retryDelay);
}

function isAuthGone(error) {
  return error?.status === 401 || error?.status === 404 || error?.code === 'UNAUTHORIZED';
}

function endExpiredSession() {
  disposed = true;
  clearBalanceRetry();
  balanceRetryDelay = 3000;
  if (stopBalanceStream) {
    stopBalanceStream();
    stopBalanceStream = null;
  }
  auth.logout();
  router.push('/login');
}

async function handleAnnouncementClick() {
  announcementOpen.value = true;
  if (!announcements.value.length && !announcementLoading.value) {
    await loadAnnouncements();
  }
  if (announcementBadge.value <= 0 && announcementUnread.value <= 0) {
    return;
  }

  const previousBadge = announcementBadge.value;
  const previousUnread = announcementUnread.value;
  announcementBadge.value = 0;
  announcementUnread.value = 0;
  try {
    applyAnnouncementInbox(await api.markAnnouncementsRead());
  } catch (error) {
    announcementBadge.value = previousBadge;
    announcementUnread.value = previousUnread;
    announcementError.value = error.message || '公告状态更新失败';
  }
}

function closeAnnouncement() {
  announcementOpen.value = false;
}

function openNewbieGuide() {
  newbieGuideOpen.value = true;
}

function closeNewbieGuide() {
  newbieGuideOpen.value = false;
}

async function copyGuideSnippet(key, text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      copyGuideSnippetFallback(text);
    }
    guideCopyStatus.value = key;
    if (guideCopyTimer) {
      clearTimeout(guideCopyTimer);
    }
    guideCopyTimer = setTimeout(() => {
      guideCopyStatus.value = '';
      guideCopyTimer = null;
    }, 1600);
  } catch (error) {
    copyGuideSnippetFallback(text);
    guideCopyStatus.value = key;
  }
}

function copyGuideSnippetFallback(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

function formatAnnouncementTime(value) {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch (error) {
    return '';
  }
}

onMounted(() => {
  loadAnnouncements();
  refreshBalanceQuietly();
  startBalanceStream();
  window.addEventListener('focus', refreshBalanceQuietly);
});

onBeforeUnmount(() => {
  disposed = true;
  clearBalanceRetry();
  if (guideCopyTimer) {
    clearTimeout(guideCopyTimer);
    guideCopyTimer = null;
  }
  if (stopBalanceStream) {
    stopBalanceStream();
    stopBalanceStream = null;
  }
  window.removeEventListener('focus', refreshBalanceQuietly);
});

const ownerEmails = new Set(['2997657261@qq.com', '2997657261']);
const isOwner = computed(() => ownerEmails.has((auth.email || '').trim().toLowerCase()));

const baseNavItems = [
  { path: '/', label: '仪表盘', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/></svg>` },
  { path: '/api-keys', label: 'API 密钥', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78Zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>` },
  { path: '/chat', label: '网页对话', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 9h8"/><path d="M8 13h5"/></svg>` },
  { path: '/chat-history', label: '聊天历史', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 8h8"/><path d="M8 12h6"/><path d="M8 16h4"/></svg>` },
  { path: '/models', label: '模型目录', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>` },
  { path: '/logs', label: '请求日志', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>` },
  { path: '/novels', label: '小说广场', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H21"/><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5z"/><path d="M8 6h8"/><path d="M8 10h7"/></svg>` },
  { path: '/recharge', label: '充值', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="1" y="4" width="22" height="16" rx="3"/><line x1="1" y1="10" x2="23" y2="10"/></svg>` },
];

const adminNavItem = {
  path: '/admin-sqlite',
  label: 'SQLite',
  icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/></svg>`,
};

const navItems = computed(() => (isOwner.value ? [...baseNavItems, adminNavItem] : baseNavItems));
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo">
          <div class="logo-icon">
            <OpenAIIcon />
          </div>
          <span class="logo-text">Relay</span>
        </div>
      </div>

      <nav class="nav">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
        >
          <span class="nav-icon" v-html="item.icon"></span>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="user-pill">
          <div class="avatar">{{ auth.email?.charAt(0)?.toUpperCase() }}</div>
          <div class="user-meta">
            <span class="user-name">{{ auth.email?.split('@')[0] }}</span>
            <span class="user-bal">{{ auth.balance.toFixed(2) }}$</span>
          </div>
        </div>
        <button class="logout-btn" @click="handleLogout" title="退出登录">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        </button>
      </div>
    </aside>

    <main class="main">
      <div class="top-actions">
        <span class="guide-tip">新手请看这个😚</span>
        <button class="guide-btn" @click="openNewbieGuide" title="新手告示" aria-label="新手告示">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 16v-4"/>
            <path d="M12 8h.01"/>
          </svg>
        </button>
        <button class="announcement-btn" @click="handleAnnouncementClick" title="公告" aria-label="公告">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
          <span v-if="announcementBadge > 0" class="announcement-badge">{{ displayBadge }}</span>
        </button>
      </div>
      <router-view v-slot="{ Component }">
        <transition name="page">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <transition name="fade">
      <div v-if="announcementOpen" class="announcement-backdrop" @click.self="closeAnnouncement">
        <section class="announcement-modal" role="dialog" aria-modal="true" aria-label="公告">
          <header class="announcement-header">
            <div>
              <h2>公告</h2>
              <span v-if="announcementUnread > 0" class="announcement-count">{{ announcementUnread }} 条未读</span>
            </div>
            <button class="modal-close" @click="closeAnnouncement" title="关闭" aria-label="关闭">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                <path d="M18 6 6 18"/>
                <path d="m6 6 12 12"/>
              </svg>
            </button>
          </header>

          <div class="announcement-body">
            <div v-if="announcementLoading" class="announcement-state">加载中...</div>
            <div v-else-if="announcementError" class="announcement-state error">{{ announcementError }}</div>
            <div v-else-if="!announcements.length" class="announcement-state">暂无公告</div>
            <article v-else v-for="item in announcements" :key="item.id" class="announcement-item">
              <div class="announcement-item-head">
                <h3>{{ item.title }}</h3>
                <time>{{ formatAnnouncementTime(item.publishedAt) }}</time>
              </div>
              <p>{{ item.content }}</p>
            </article>
          </div>
        </section>
      </div>
    </transition>

    <transition name="fade">
      <div v-if="newbieGuideOpen" class="announcement-backdrop" @click.self="closeNewbieGuide">
        <section class="guide-modal" role="dialog" aria-modal="true" aria-label="新手配置教程">
          <header class="announcement-header">
            <div>
              <h2>新手配置教程</h2>
              <span class="announcement-count">把本站 API Key 配到 Codex 或 Claude Code</span>
            </div>
            <button class="modal-close" @click="closeNewbieGuide" title="关闭" aria-label="关闭">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                <path d="M18 6 6 18"/>
                <path d="m6 6 12 12"/>
              </svg>
            </button>
          </header>

          <div class="guide-body">
            <section class="guide-section guide-highlight">
              <h3>先准备两样东西</h3>
              <p>你不需要部署项目，只需要使用本站提供的中转服务。</p>
              <ul>
                <li>中转站地址，即 <code>https://api.relaywei.ccwu.cc/v1</code></li>
                <li>在本站后台生成的 API Key，例如 <code>relay_xxxxxxxxxxxxxxxx</code></li>
              </ul>
              <p>这里的 API Key 是本站生成的用户 Key，不是 OpenAI 官方 Key，也不是 Claude 官方 Key。</p>
            </section>

            <section class="guide-section">
              <h3>一、Codex CLI 配置</h3>
              <p>Codex 使用 OpenAI 兼容接口，所以 Base URL 必须带 <code>/v1</code>。</p>
              <div class="guide-callout">
                <strong>Codex 地址格式</strong>
                <code>https://api.relaywei.ccwu.cc/v1</code>
              </div>
              <ol>
                <li>安装 Node.js LTS 版本。</li>
                <li>打开终端，执行 <code>npm install -g @openai/codex</code>。</li>
                <li>执行 <code>codex --version</code>，能看到版本号就是安装成功。</li>
                <li>打开 Codex 配置文件：Windows 通常在 <code>C:\Users\你的用户名\.codex\config.toml</code>，macOS / Linux 通常在 <code>~/.codex/config.toml,你可以直接完整替换成下面这份</code>。</li>
              </ol>
              <div class="guide-code-block">
                <button class="copy-code-btn" @click="copyGuideSnippet('codexConfig', guideSnippets.codexConfig)" title="复制" aria-label="复制">
                  <svg v-if="guideCopyStatus !== 'codexConfig'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                    <rect x="9" y="9" width="13" height="13" rx="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                  </svg>
                  <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 6 9 17l-5-5"/>
                  </svg>
                </button>
                <pre><code>{{ guideSnippets.codexConfig }}</code></pre>
              </div>
            </section>

            <section class="guide-section">
              <h3>二、Codex API Key 设置</h3>
              <p>配置完config.toml后，我们接下来配置auth.json，它和config.toml在同一个父目录下，你可以替换成下面这份，但是要更改成你生成的那一份token</p>
              <div class="guide-code-block">
                <button class="copy-code-btn" @click="copyGuideSnippet('codexAuth', guideSnippets.codexAuth)" title="复制" aria-label="复制">
                  <svg v-if="guideCopyStatus !== 'codexAuth'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                    <rect x="9" y="9" width="13" height="13" rx="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                  </svg>
                  <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 6 9 17l-5-5"/>
                  </svg>
                </button>
                <pre><code>{{ guideSnippets.codexAuth }}</code></pre>
              </div>
              <p>配置完成后，在终端执行 <code>codex</code>，随便问一句。如果能正常回复，说明已经配置成功。</p>
            </section>

            <section class="guide-section">
              <h3>三、Codex 桌面 App / IDE 插件</h3>
              <p>如果你使用桌面 App 或 VS Code 插件，配置方法和上述一样，也是配置那两个文件</p>
              
            </section>

            <section class="guide-section">
              <h3>四、Claude Code 配置</h3>
              <p>Claude Code 使用 Claude 风格接口，把下面的配置复制到终端后执行即可。Claude Code安装方法<code>npm install -g @anthropic-ai/claude-code</code>(目前只支持小米模型，而且小米模型使用暂不扣费，后续会开放更多模型哦)</p>
              <div class="guide-callout warning">
                <strong>Claude Code 地址格式</strong>
                <code>https://api.relaywei.ccwu.cc/v1</code>
              </div>
              <div class="guide-two-col">
                <div>
                  <strong>Windows PowerShell</strong>
                  <div class="guide-code-block">
                    <button class="copy-code-btn" @click="copyGuideSnippet('claudeWindows', guideSnippets.claudeWindows)" title="复制" aria-label="复制">
                      <svg v-if="guideCopyStatus !== 'claudeWindows'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                        <rect x="9" y="9" width="13" height="13" rx="2"/>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                      </svg>
                      <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M20 6 9 17l-5-5"/>
                      </svg>
                    </button>
                    <pre><code>{{ guideSnippets.claudeWindows }}</code></pre>
                  </div>
                </div>
                <div>
                  <strong>macOS / Linux</strong>
                  <div class="guide-code-block">
                    <button class="copy-code-btn" @click="copyGuideSnippet('claudeUnix', guideSnippets.claudeUnix)" title="复制" aria-label="复制">
                      <svg v-if="guideCopyStatus !== 'claudeUnix'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                        <rect x="9" y="9" width="13" height="13" rx="2"/>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                      </svg>
                      <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M20 6 9 17l-5-5"/>
                      </svg>
                    </button>
                    <pre><code>{{ guideSnippets.claudeUnix }}</code></pre>
                  </div>
                </div>
              </div>
              <p>然后执行 <code>claude</code> 启动 Claude Code。</p>
            </section>

            <section class="guide-section">
              <h3>五、常见问题</h3>
              <table>
                <tbody>
                  <tr>
                    <th>401 / Unauthorized</th>
                    <td>通常是 API Key 填错、复制少了字符，或者 Key 已被删除。</td>
                  </tr>
                  <tr>
                    <th>404 / Not Found</th>
                    <td>通常是 Base URL 写错。请按教程填写 <code>https://api.relaywei.ccwu.cc/v1</code>。</td>
                  </tr>
                  <tr>
                    <th>model not found</th>
                    <td>模型名不在本站支持列表里，请到模型目录查看可用模型。</td>
                  </tr>
                </tbody>
              </table>
            </section>

            <section class="guide-section guide-summary">
              <h3>最后记住这一句</h3>
              <p><strong>Codex和Claude Code的base_url都填 <code>https://api.relaywei.ccwu.cc/v1</code></strong>，token就填本站生成的</p>
            </section>
          </div>
        </section>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 240px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  height: 100vh;
}

.sidebar-header {
  padding: 24px 20px 20px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: #111827;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 2px 8px rgba(17, 24, 39, 0.18);
}

.logo-icon svg {
  width: 21px;
  height: 21px;
}

.logo-text {
  font-size: 18px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: 0;
}

.nav {
  flex: 1;
  padding: 4px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  color: var(--text-secondary);
  font-size: 13.5px;
  font-weight: 500;
  border-radius: var(--radius-sm);
  transition: all var(--duration) var(--ease);
  position: relative;
}

.nav-item:hover {
  background: var(--primary-soft);
  color: var(--text);
}

.nav-item.active {
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 18px;
  background: var(--primary);
  border-radius: 0 3px 3px 0;
}

.nav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  opacity: 0.7;
}

.nav-item.active .nav-icon {
  opacity: 1;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-pill {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #a78bfa);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 700;
  font-size: 13px;
  flex-shrink: 0;
}

.user-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-bal {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.logout-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: var(--radius-xs);
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
  flex-shrink: 0;
}

.logout-btn:hover {
  background: var(--danger-soft);
  color: var(--danger);
}

.main {
  flex: 1;
  padding: 24px 40px 32px;
  overflow-y: auto;
  min-width: 0;
  background: var(--bg);
}

.top-actions {
  min-height: 40px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.guide-tip {
  color: var(--danger);
  font-size: 13px;
  font-weight: 800;
  line-height: 1;
  white-space: nowrap;
}

.guide-btn,
.announcement-btn {
  width: 38px;
  height: 38px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  position: relative;
  box-shadow: var(--shadow-xs);
  transition: all var(--duration) var(--ease);
}

.guide-btn:hover,
.announcement-btn:hover {
  color: var(--primary);
  border-color: rgba(99, 102, 241, 0.18);
  box-shadow: var(--shadow-sm);
}

.announcement-badge {
  position: absolute;
  top: -7px;
  right: -7px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--danger);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
  box-shadow: 0 0 0 2px var(--bg);
}

.announcement-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(17, 24, 39, 0.34);
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
  padding: 72px 40px 24px;
  z-index: 50;
}

.announcement-modal {
  width: min(460px, calc(100vw - 32px));
  max-height: min(680px, calc(100vh - 96px));
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-xl);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.guide-modal {
  width: min(760px, calc(100vw - 32px));
  max-height: min(760px, calc(100vh - 96px));
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-xl);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.announcement-header {
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.announcement-header h2 {
  font-size: 17px;
  font-weight: 800;
  color: var(--text);
}

.announcement-count {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.modal-close {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.modal-close:hover {
  background: var(--danger-soft);
  color: var(--danger);
}

.announcement-body {
  padding: 12px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.announcement-state {
  min-height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 13px;
}

.announcement-state.error {
  color: var(--danger);
}

.announcement-item {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 13px 14px;
  background: #fff;
}

.announcement-item-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.announcement-item h3 {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  word-break: break-word;
}

.announcement-item time {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.announcement-item p {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.guide-body {
  padding: 16px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.guide-section {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  background: #fff;
}

.guide-section h3 {
  font-size: 15px;
  font-weight: 800;
  color: var(--text);
  margin-bottom: 8px;
}

.guide-section p,
.guide-section li,
.guide-section td,
.guide-section th {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.8;
}

.guide-section p + p {
  margin-top: 8px;
}

.guide-section ul,
.guide-section ol {
  padding-left: 20px;
  margin: 8px 0 0;
}

.guide-section li + li {
  margin-top: 5px;
}

.guide-section code {
  padding: 2px 5px;
  border-radius: 5px;
  background: rgba(17, 24, 39, 0.06);
  color: #111827;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
  word-break: break-all;
}

.guide-section pre {
  margin-top: 10px;
  padding: 12px;
  border-radius: 8px;
  background: #111827;
  overflow: auto;
}

.guide-section pre code {
  padding: 0;
  background: transparent;
  color: #f9fafb;
  line-height: 1.7;
  white-space: pre;
}

.guide-code-block {
  position: relative;
  margin-top: 10px;
}

.guide-code-block pre {
  margin-top: 0;
  padding-right: 46px;
}

.copy-code-btn {
  position: absolute;
  top: 9px;
  right: 9px;
  z-index: 1;
  width: 30px;
  height: 30px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.82);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.copy-code-btn:hover {
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
}

.guide-highlight {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(20, 184, 166, 0.08));
  border-color: rgba(99, 102, 241, 0.16);
}

.guide-callout {
  margin-top: 10px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid rgba(99, 102, 241, 0.18);
  background: var(--primary-soft);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.guide-callout.warning {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(245, 158, 11, 0.08);
}

.guide-callout strong,
.guide-two-col strong {
  color: var(--text);
  font-size: 13px;
  font-weight: 700;
}

.guide-two-col {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 10px;
}

.guide-section table {
  width: 100%;
  margin-top: 10px;
  border-collapse: collapse;
  overflow: hidden;
  border-radius: 8px;
}

.guide-section th,
.guide-section td {
  padding: 10px 12px;
  border: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.guide-section th {
  width: 160px;
  background: #fafbfd;
  color: var(--text);
  font-weight: 700;
}

.guide-summary {
  border-color: rgba(16, 185, 129, 0.18);
  background: var(--success-soft);
}

@media (max-width: 760px) {
  .main {
    padding: 20px 18px 28px;
  }

  .announcement-backdrop {
    justify-content: center;
    padding: 64px 16px 20px;
  }

  .guide-two-col {
    grid-template-columns: 1fr;
  }

  .guide-section th {
    width: 112px;
  }
}
</style>
