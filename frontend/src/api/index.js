const BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8081/api').replace(/\/$/, '');

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

export function getWebChatSession() {
  return request('/web-chat/session');
}

export function sendWebChatMessage({ message, newConversation = false, model, images = [] } = {}) {
  return request('/web-chat/messages', {
    method: 'POST',
    body: JSON.stringify({ message, newConversation, model, images }),
  });
}

export async function streamWebChatMessage(
  { message, newConversation = false, model, images = [] } = {},
  handlers = {},
) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}/web-chat/messages/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, newConversation, model, images }),
  });

  if (!res.ok) {
    throw await responseError(res);
  }

  if (!res.body) {
    return sendWebChatMessage({ message, newConversation, model, images });
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let donePayload = null;

  const dispatch = (block) => {
    const lines = block.split(/\r?\n/);
    let event = 'message';
    const dataLines = [];
    for (const line of lines) {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (!dataLines.length) return;

    const rawData = dataLines.join('\n');
    const payload = parseEventData(rawData);
    if (event === 'delta' && typeof payload?.delta === 'string') {
      handlers.onDelta?.(payload.delta);
      return;
    }
    if (event === 'replace' && typeof payload?.text === 'string') {
      handlers.onReplace?.(payload.text);
      return;
    }
    if (event === 'done') {
      donePayload = payload;
      handlers.onDone?.(payload);
      return;
    }
    if (event === 'error') {
      throw new Error(payload?.message || '发送失败');
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || '';
    for (const block of blocks) {
      dispatch(block);
    }
    if (done) break;
  }

  if (buffer.trim()) {
    dispatch(buffer);
  }

  return donePayload;
}

async function responseError(res) {
  const text = await res.text();
  try {
    const json = JSON.parse(text);
    const err = new Error(json.error?.message || json.message || 'Request failed');
    err.code = json.error?.code;
    err.details = json.error?.details;
    err.status = res.status;
    return err;
  } catch {
    const err = new Error(text || 'Request failed');
    err.status = res.status;
    return err;
  }
}

function parseEventData(data) {
  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}

function dispatchBalanceEvent(block, handlers) {
  const lines = block.split(/\r?\n/);
  let event = 'message';
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!dataLines.length) {
    return;
  }

  const payload = parseEventData(dataLines.join('\n'));
  if (event === 'error') {
    const err = new Error(payload?.error?.message || payload?.message || 'Balance stream failed');
    err.code = payload?.error?.code || payload?.code;
    handlers.onError?.(err);
    return;
  }
  if (event === 'message' || event === 'balance') {
    handlers.onBalance?.(payload);
  }
}

export function resetWebChatConversation() {
  return request('/web-chat/conversation/reset', {
    method: 'POST',
  });
}

export function getWebChatHistory({ page = 1, size = 20 } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    size: String(size),
  });
  return request(`/web-chat/history?${params.toString()}`);
}

export function getWebChatHistoryDetail(id) {
  return request(`/web-chat/history/${id}`);
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
  return request('/balance');
}

export function streamBalanceUpdates(handlers = {}) {
  const controller = new AbortController();

  (async () => {
    const headers = { Accept: 'text/event-stream, application/json' };
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
      const res = await fetch(`${BASE}/balance/stream`, {
        headers,
        signal: controller.signal,
      });
      if (!res.ok) {
        throw await responseError(res);
      }
      if (!res.body) {
        handlers.onClose?.();
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || '';
        for (const block of blocks) {
          dispatchBalanceEvent(block, handlers);
        }
        if (done) break;
      }

      if (buffer.trim()) {
        dispatchBalanceEvent(buffer, handlers);
      }
      handlers.onClose?.();
    } catch (err) {
      if (!controller.signal.aborted) {
        handlers.onError?.(err);
      }
    }
  })();

  return () => controller.abort();
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

export function getNovels({ page = 1, size = 20, query = '' } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    size: String(size),
  });
  const trimmedQuery = query.trim();
  if (trimmedQuery) {
    params.set('q', trimmedQuery);
  }
  return request(`/novels?${params.toString()}`);
}

export function getNovelRanking(limit = 20) {
  return request(`/novels/ranking?limit=${limit}`);
}

export function getNovel(id) {
  return request(`/novels/${id}`);
}

export function createNovel({ title, author, content }) {
  return request('/novels', {
    method: 'POST',
    body: JSON.stringify({ title, author, content }),
  });
}

export function rateNovel(id, score) {
  return request(`/novels/${id}/ratings`, {
    method: 'POST',
    body: JSON.stringify({ score }),
  });
}

export function getAdminTables() {
  return request('/admin/sqlite/tables');
}

export function getAdminMaintenance() {
  return request('/admin/maintenance');
}

export function setAdminMaintenance(writeDisabled) {
  return request('/admin/maintenance', {
    method: 'PUT',
    body: JSON.stringify({ writeDisabled }),
  });
}

export function getAdminTableRows(table, { limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return request(`/admin/sqlite/tables/${encodeURIComponent(table)}/rows?${params.toString()}`);
}

export function createAdminRow(table, values) {
  return request(`/admin/sqlite/tables/${encodeURIComponent(table)}/rows`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  });
}

export function updateAdminRow(table, rowid, values) {
  return request(`/admin/sqlite/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(rowid)}`, {
    method: 'PUT',
    body: JSON.stringify({ values }),
  });
}

export function deleteAdminRow(table, rowid) {
  return request(`/admin/sqlite/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(rowid)}`, {
    method: 'DELETE',
  });
}

export function executeAdminSql(sql) {
  return request('/admin/sqlite/sql', {
    method: 'POST',
    body: JSON.stringify({ sql }),
  });
}
