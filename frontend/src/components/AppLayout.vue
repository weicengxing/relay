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
const announcementLoading = ref(false);
const announcementError = ref('');
let stopBalanceStream = null;
let balanceRetryTimer = null;
let disposed = false;

const displayBadge = computed(() => (announcementBadge.value > 99 ? '99+' : String(announcementBadge.value)));

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
  balanceRetryTimer = setTimeout(startBalanceStream, 3000);
}

function isAuthGone(error) {
  return error?.status === 401 || error?.status === 404 || error?.code === 'UNAUTHORIZED';
}

function endExpiredSession() {
  disposed = true;
  clearBalanceRetry();
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
  if (stopBalanceStream) {
    stopBalanceStream();
    stopBalanceStream = null;
  }
  window.removeEventListener('focus', refreshBalanceQuietly);
});

const navItems = [
  { path: '/', label: '仪表盘', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/></svg>` },
  { path: '/api-keys', label: 'API 密钥', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78Zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>` },
  { path: '/chat', label: '网页对话', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 9h8"/><path d="M8 13h5"/></svg>` },
  { path: '/chat-history', label: '聊天历史', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 8h8"/><path d="M8 12h6"/><path d="M8 16h4"/></svg>` },
  { path: '/models', label: '模型目录', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>` },
  { path: '/logs', label: '请求日志', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>` },
  { path: '/novels', label: '小说广场', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H21"/><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5z"/><path d="M8 6h8"/><path d="M8 10h7"/></svg>` },
  { path: '/recharge', label: '充值', icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="1" y="4" width="22" height="16" rx="3"/><line x1="1" y1="10" x2="23" y2="10"/></svg>` },
];
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
        <button class="announcement-btn" @click="handleAnnouncementClick" title="公告" aria-label="公告">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
          <span v-if="announcementBadge > 0" class="announcement-badge">{{ displayBadge }}</span>
        </button>
      </div>
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
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
  margin-bottom: 8px;
}

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

@media (max-width: 760px) {
  .main {
    padding: 20px 18px 28px;
  }

  .announcement-backdrop {
    justify-content: center;
    padding: 64px 16px 20px;
  }
}
</style>
