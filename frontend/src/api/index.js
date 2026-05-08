const BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

function getToken() {
  return localStorage.getItem('token');
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  const json = await res.json();

  if (!res.ok || !json.success) {
    const err = new Error(json.error?.message || 'Request failed');
    err.code = json.error?.code;
    err.details = json.error?.details;
    err.status = res.status;
    throw err;
  }
  return json.data;
}

export function register(email, password, verificationCode) {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, verificationCode }),
  });
}

export function login(email, password) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function sendRegisterCode(email) {
  return request('/auth/register-code', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export function getBootstrap() {
  return request('/bootstrap');
}

export function getHealth() {
  return request('/health');
}

export function getApiKeys() {
  return request('/api-keys');
}

export function createApiKey(name) {
  return request('/api-keys', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function revokeApiKey(id) {
  return request(`/api-keys/${id}`, {
    method: 'DELETE',
  });
}

export function getLogs(limit = 100) {
  return request(`/request-logs?limit=${limit}`);
}

export function getModels() {
  return request('/models');
}

export function getAnnouncements() {
  return request('/announcements');
}

export function markAnnouncementsRead() {
  return request('/announcements/read', {
    method: 'POST',
  });
}

export async function getBalance() {
  return { balance: 0 };
}

export async function createRecharge(amount, remark) {
  return { id: Date.now(), amount, status: 'pending', remark, createdAt: new Date().toISOString() };
}

export function redeemCode(code) {
  return request('/redeem-codes/redeem', {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}
