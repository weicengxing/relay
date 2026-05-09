<script setup>
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();

const links = [
  { path: '/api-keys', label: 'API 密钥', desc: '管理你的 Key', icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78Zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>`, gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)' },
  { path: '/chat', label: '网页对话', desc: '直接和网页模型聊天', icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 9h8"/><path d="M8 13h5"/></svg>`, gradient: 'linear-gradient(135deg, #14b8a6, #0f766e)' },
  { path: '/models', label: '模型目录', desc: '查看可用模型', icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`, gradient: 'linear-gradient(135deg, #8b5cf6, #a78bfa)' },
  { path: '/logs', label: '请求日志', desc: '查看调用记录', icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`, gradient: 'linear-gradient(135deg, #06b6d4, #22d3ee)' },
  { path: '/recharge', label: '充值', desc: '为账户充值', icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="1" y="4" width="22" height="16" rx="3"/><line x1="1" y1="10" x2="23" y2="10"/></svg>`, gradient: 'linear-gradient(135deg, #10b981, #34d399)' },
];
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>仪表盘</h1>
        <p>欢迎回来，{{ auth.email?.split('@')[0] }}</p>
      </div>
    </header>

    <section class="stats">
      <div class="stat-card stat-hero">
        <div class="stat-label">账户余额</div>
        <div class="stat-number">{{ auth.balance.toFixed(2) }}$</div>
        <div class="stat-sub">可用余额</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">账户状态</div>
        <div class="stat-number stat-ok">正常</div>
        <div class="stat-sub">所有服务可用</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">注册邮箱</div>
        <div class="stat-number stat-email">{{ auth.email }}</div>
        <div class="stat-sub">主账户</div>
      </div>
    </section>

    <section class="shortcuts">
      <h2>快捷入口</h2>
      <div class="shortcut-grid">
        <router-link v-for="item in links" :key="item.path" :to="item.path" class="shortcut-card">
          <div class="shortcut-icon" :style="{ background: item.gradient }">
            <span v-html="item.icon"></span>
          </div>
          <div class="shortcut-text">
            <strong>{{ item.label }}</strong>
            <span>{{ item.desc }}</span>
          </div>
          <svg class="shortcut-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </router-link>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { animation: pageIn 0.4s var(--ease-out); }

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-head {
  margin-bottom: 28px;
}

.page-head h1 {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.5px;
}

.page-head p {
  color: var(--text-secondary);
  font-size: 14px;
  margin-top: 4px;
}

.stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 36px;
}

.stat-card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  padding: 24px;
  box-shadow: var(--shadow-card);
  transition: all var(--duration) var(--ease);
}

.stat-card:hover {
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-2px);
}

.stat-hero {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a78bfa 100%);
  color: #fff;
  border: none;
}

.stat-hero .stat-label { color: rgba(255,255,255,0.7); }
.stat-hero .stat-number { color: #fff; }
.stat-hero .stat-sub { color: rgba(255,255,255,0.5); }

.stat-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.stat-number {
  font-size: 32px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: -1px;
  line-height: 1;
  margin-bottom: 6px;
}

.stat-ok { color: var(--success); font-size: 20px; letter-spacing: 0; }
.stat-email { font-size: 15px; font-weight: 600; letter-spacing: 0; word-break: break-all; }

.stat-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.shortcuts h2 {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 14px;
}

.shortcut-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

.shortcut-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--surface);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  box-shadow: var(--shadow-card);
  transition: all var(--duration) var(--ease);
  color: inherit;
}

.shortcut-card:hover {
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-2px);
}

.shortcut-card:hover .shortcut-arrow {
  opacity: 1;
  transform: translateX(3px);
}

.shortcut-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.shortcut-text {
  flex: 1;
  min-width: 0;
}

.shortcut-text strong {
  display: block;
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 1px;
}

.shortcut-text span {
  font-size: 12px;
  color: var(--text-muted);
}

.shortcut-arrow {
  color: var(--text-muted);
  opacity: 0;
  transition: all var(--duration) var(--ease);
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .stats, .shortcut-grid { grid-template-columns: 1fr; }
}
</style>
