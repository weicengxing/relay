<script setup>
const stack = [
  { label: 'Frontend', value: 'Vue 3 + Vite' },
  { label: 'Backend', value: 'Spring Boot REST API' },
  { label: 'Database', value: 'Supabase PostgreSQL' },
  { label: 'Cache', value: 'Upstash Redis' }
];

const phaseOne = [
  'User signup and login',
  'Balance tracking',
  'API key management',
  'Model catalog',
  'Chat proxy forwarding',
  'Request logs',
  'Manual recharge'
];

const apiRoutes = ['GET /api/health', 'GET /api/bootstrap'];
</script>

<template>
  <main class="page">
    <header class="topbar">
      <div class="hero">
        <p class="eyebrow">Relay MVP scaffold</p>
        <h1>Free Java AI Proxy</h1>
        <p class="lede">
          The first pass keeps the stack compact: Vue 3 on the front end and Spring Boot on the
          back end.
        </p>
      </div>

      <div class="panel status">
        <span class="status-label">Current step</span>
        <strong>Repository scaffolded</strong>
        <p>Frontend and backend entry points are ready for data, auth, and routing work.</p>
      </div>
    </header>

    <section class="bands">
      <article class="panel">
        <h2>Stack</h2>
        <ul class="list">
          <li v-for="item in stack" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </li>
        </ul>
      </article>

      <article class="panel">
        <h2>Phase 1 scope</h2>
        <ul class="checks">
          <li v-for="item in phaseOne" :key="item">{{ item }}</li>
        </ul>
      </article>

      <article class="panel">
        <h2>Backend routes</h2>
        <ul class="routes">
          <li v-for="route in apiRoutes" :key="route">{{ route }}</li>
        </ul>
      </article>
    </section>
  </main>
</template>

