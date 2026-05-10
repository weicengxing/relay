<script setup>
import { computed, nextTick, onMounted, ref } from 'vue';
import * as api from '../api';

const tables = ref([]);
const selectedTable = ref('');
const columns = ref([]);
const rows = ref([]);
const total = ref(0);
const limit = ref(100);
const offset = ref(0);
const loadingTables = ref(false);
const loadingRows = ref(false);
const saving = ref(false);
const error = ref('');
const editorOpen = ref(false);
const editorMode = ref('create');
const editorText = ref('{}');
const editingRowid = ref(null);
const editorError = ref('');
const sqlText = ref("select name from sqlite_master where type = 'table' order by name;");
const sqlRunning = ref(false);
const sqlResult = ref(null);
const sqlError = ref('');
const maintenance = ref({ writeDisabled: false });
const maintenanceLoading = ref(false);
const cellEdit = ref(null);

const currentTable = computed(() => tables.value.find((table) => table.name === selectedTable.value));
const pageStart = computed(() => (total.value === 0 ? 0 : offset.value + 1));
const pageEnd = computed(() => Math.min(offset.value + rows.value.length, total.value));
const canPrev = computed(() => offset.value > 0);
const canNext = computed(() => offset.value + rows.value.length < total.value);
const sqlResultColumns = computed(() => {
  if (sqlResult.value?.columns?.length) return sqlResult.value.columns;
  const first = sqlResult.value?.rows?.[0];
  return first ? Object.keys(first) : [];
});

onMounted(() => {
  loadMaintenance();
  loadTables();
});

async function loadMaintenance() {
  maintenanceLoading.value = true;
  try {
    maintenance.value = await api.getAdminMaintenance();
  } catch (err) {
    error.value = err.message || 'Failed to load maintenance status';
  } finally {
    maintenanceLoading.value = false;
  }
}

async function toggleMaintenance() {
  maintenanceLoading.value = true;
  error.value = '';
  try {
    maintenance.value = await api.setAdminMaintenance(!maintenance.value.writeDisabled);
  } catch (err) {
    error.value = err.message || 'Failed to update maintenance status';
  } finally {
    maintenanceLoading.value = false;
  }
}

async function loadTables() {
  loadingTables.value = true;
  error.value = '';
  try {
    const data = await api.getAdminTables();
    tables.value = data.tables || [];
    if (!selectedTable.value && tables.value.length) {
      selectedTable.value = tables.value[0].name;
    }
    if (selectedTable.value) {
      await loadRows();
    }
  } catch (err) {
    error.value = err.message || 'Failed to load SQLite tables';
  } finally {
    loadingTables.value = false;
  }
}

async function selectTable(name) {
  if (selectedTable.value === name) return;
  selectedTable.value = name;
  offset.value = 0;
  await loadRows();
}

async function loadRows() {
  if (!selectedTable.value) return;
  loadingRows.value = true;
  error.value = '';
  try {
    const data = await api.getAdminTableRows(selectedTable.value, {
      limit: limit.value,
      offset: offset.value,
    });
    columns.value = data.columns || [];
    rows.value = data.rows || [];
    total.value = Number(data.total || 0);
  } catch (err) {
    error.value = err.message || 'Failed to load rows';
  } finally {
    loadingRows.value = false;
  }
}

function refreshAll() {
  return loadTables();
}

function prevPage() {
  if (!canPrev.value) return;
  offset.value = Math.max(0, offset.value - limit.value);
  loadRows();
}

function nextPage() {
  if (!canNext.value) return;
  offset.value += limit.value;
  loadRows();
}

function rowPayload(row) {
  const copy = { ...row };
  delete copy._rowid;
  return copy;
}

function cellKey(row, column) {
  return `${row._rowid}:${column.name}`;
}

function isEditingCell(row, column) {
  return cellEdit.value?.key === cellKey(row, column);
}

function startCellEdit(row, column) {
  if (saving.value || isEditingCell(row, column)) return;
  cellEdit.value = {
    key: cellKey(row, column),
    rowid: row._rowid,
    column: column.name,
    original: row[column.name],
    value: inlineEditText(row[column.name]),
    saving: false,
  };
  nextTick(() => {
    document.querySelector('.cell-editor-input')?.focus();
    document.querySelector('.cell-editor-input')?.select();
  });
}

function inlineEditText(value) {
  if (value === null || value === undefined) return 'NULL';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function parseInlineValue(text, original) {
  const value = String(text ?? '');
  if (value.trim().toUpperCase() === 'NULL') return null;
  if (typeof original === 'number' && value.trim() !== '' && !Number.isNaN(Number(value))) {
    return Number(value);
  }
  if (typeof original === 'object' && original !== null) {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

async function commitCellEdit(row, column) {
  const edit = cellEdit.value;
  if (!edit || edit.key !== cellKey(row, column) || edit.saving) return;
  const nextValue = parseInlineValue(edit.value, edit.original);
  if (formatValue(nextValue) === formatValue(edit.original)) {
    cellEdit.value = null;
    return;
  }
  edit.saving = true;
  error.value = '';
  try {
    await api.updateAdminRow(selectedTable.value, edit.rowid, { [column.name]: nextValue });
    row[column.name] = nextValue;
    cellEdit.value = null;
  } catch (err) {
    edit.saving = false;
    error.value = err.message || 'Cell update failed';
  }
}

function cancelCellEdit() {
  cellEdit.value = null;
}

function openCreate() {
  editorMode.value = 'create';
  editingRowid.value = null;
  editorText.value = '{\n  \n}';
  editorError.value = '';
  editorOpen.value = true;
}

function openEdit(row) {
  editorMode.value = 'edit';
  editingRowid.value = row._rowid;
  editorText.value = JSON.stringify(rowPayload(row), null, 2);
  editorError.value = '';
  editorOpen.value = true;
}

function closeEditor() {
  if (saving.value) return;
  editorOpen.value = false;
}

async function saveEditor() {
  editorError.value = '';
  let values;
  try {
    values = JSON.parse(editorText.value || '{}');
  } catch (err) {
    editorError.value = 'JSON is invalid';
    return;
  }
  if (!values || Array.isArray(values) || typeof values !== 'object') {
    editorError.value = 'JSON must be an object';
    return;
  }

  saving.value = true;
  try {
    if (editorMode.value === 'create') {
      await api.createAdminRow(selectedTable.value, values);
    } else {
      await api.updateAdminRow(selectedTable.value, editingRowid.value, values);
    }
    editorOpen.value = false;
    await refreshAll();
  } catch (err) {
    editorError.value = err.message || 'Save failed';
  } finally {
    saving.value = false;
  }
}

async function deleteRow(row) {
  const label = `${selectedTable.value} rowid ${row._rowid}`;
  if (!window.confirm(`Delete ${label}?`)) return;
  error.value = '';
  try {
    await api.deleteAdminRow(selectedTable.value, row._rowid);
    await refreshAll();
  } catch (err) {
    error.value = err.message || 'Delete failed';
  }
}

async function executeSql() {
  const sql = sqlText.value.trim();
  if (!sql) {
    sqlError.value = 'SQL is required';
    return;
  }
  sqlRunning.value = true;
  sqlError.value = '';
  sqlResult.value = null;
  try {
    sqlResult.value = await api.executeAdminSql(sql);
    await refreshAll();
  } catch (err) {
    sqlError.value = err.message || 'SQL execution failed';
  } finally {
    sqlRunning.value = false;
  }
}

function formatValue(value) {
  if (value === null || value === undefined) return 'NULL';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function columnHint(column) {
  const parts = [column.name];
  if (column.type) parts.push(column.type);
  if (column.primaryKey) parts.push(`PK ${column.primaryKey}`);
  if (column.notNull) parts.push('NOT NULL');
  if (column.defaultValue !== null && column.defaultValue !== undefined) {
    parts.push(`DEFAULT ${column.defaultValue}`);
  }
  return parts.join(' | ');
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>SQLite Admin</h1>
        <p>Owner-only database table editor</p>
      </div>
      <div class="head-actions">
        <button
          class="ghost-btn"
          :class="{ danger: maintenance.writeDisabled }"
          type="button"
          @click="toggleMaintenance"
          :disabled="maintenanceLoading"
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
            <path d="M12 2 3 7v6c0 5 3.8 8.6 9 9 5.2-.4 9-4 9-9V7l-9-5Z" />
            <path d="M9 12h6" />
          </svg>
          {{ maintenance.writeDisabled ? 'Writes Disabled' : 'Writes Enabled' }}
        </button>
        <button class="ghost-btn" type="button" @click="refreshAll" :disabled="loadingTables || loadingRows">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
            <path d="M3 21v-5h5" />
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
            <path d="M16 8h5V3" />
          </svg>
          Refresh
        </button>
        <button class="primary-btn" type="button" @click="openCreate" :disabled="!selectedTable">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
          Add Row
        </button>
      </div>
    </header>

    <div v-if="error" class="error-bar">{{ error }}</div>

    <section class="sql-panel">
      <div class="sql-head">
        <div>
          <h2>SQL Console</h2>
          <p>Execute SQLite statements as owner</p>
        </div>
        <button class="primary-btn" type="button" :disabled="sqlRunning" @click="executeSql">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 3l14 9-14 9V3Z" />
          </svg>
          {{ sqlRunning ? 'Executing...' : 'Execute' }}
        </button>
      </div>
      <textarea v-model="sqlText" class="sql-editor" spellcheck="false"></textarea>
      <div v-if="sqlError" class="error-bar sql-error">{{ sqlError }}</div>
      <div v-if="sqlResult" class="sql-result">
        <div class="sql-summary">
          <span>{{ sqlResult.statementCount }} statement{{ sqlResult.statementCount === 1 ? '' : 's' }}</span>
          <span>{{ sqlResult.changes }} change{{ sqlResult.changes === 1 ? '' : 's' }}</span>
          <span>{{ sqlResult.rowCount }} row{{ sqlResult.rowCount === 1 ? '' : 's' }}</span>
          <span v-if="sqlResult.truncated">showing first 500 rows</span>
        </div>
        <div v-if="sqlResult.rows?.length" class="sql-table-wrap">
          <table class="data-table sql-table">
            <thead>
              <tr>
                <th v-for="column in sqlResultColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in sqlResult.rows" :key="index">
                <td v-for="column in sqlResultColumns" :key="column" class="value-cell" :title="formatValue(row[column])">
                  {{ formatValue(row[column]) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="admin-shell">
      <aside class="table-list">
        <div class="table-list-head">
          <span>Tables</span>
          <strong>{{ tables.length }}</strong>
        </div>
        <div v-if="loadingTables" class="state">Loading...</div>
        <template v-else>
          <button
            v-for="table in tables"
            :key="table.name"
            class="table-item"
            :class="{ active: table.name === selectedTable }"
            type="button"
            @click="selectTable(table.name)"
          >
            <span class="table-name">{{ table.name }}</span>
            <span class="table-meta">{{ table.rowCount }} rows</span>
          </button>
        </template>
      </aside>

      <main class="data-panel">
        <div class="data-toolbar">
          <div>
            <h2>{{ selectedTable || 'No table selected' }}</h2>
            <span v-if="currentTable" class="meta-line">
              {{ currentTable.columnCount }} columns - {{ total }} rows
            </span>
          </div>
          <div class="pager">
            <button class="icon-btn" type="button" title="Previous" :disabled="!canPrev" @click="prevPage">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="m15 18-6-6 6-6" />
              </svg>
            </button>
            <span>{{ pageStart }}-{{ pageEnd }} / {{ total }}</span>
            <button class="icon-btn" type="button" title="Next" :disabled="!canNext" @click="nextPage">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="m9 18 6-6-6-6" />
              </svg>
            </button>
          </div>
        </div>

        <div class="column-strip" v-if="columns.length">
          <span v-for="column in columns" :key="column.name" class="column-pill" :title="columnHint(column)">
            {{ column.name }}
          </span>
        </div>

        <div v-if="loadingRows" class="empty">
          <div class="loader"></div>
          <span>Loading rows...</span>
        </div>
        <div v-else-if="!selectedTable" class="empty">No SQLite table found.</div>
        <div v-else-if="rows.length === 0" class="empty">This table has no rows.</div>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th class="rowid-col">rowid</th>
                <th v-for="column in columns" :key="column.name">{{ column.name }}</th>
                <th class="actions-col">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row._rowid">
                <td class="rowid-cell">{{ row._rowid }}</td>
                <td
                  v-for="column in columns"
                  :key="column.name"
                  class="value-cell editable-cell"
                  :class="{ editing: isEditingCell(row, column) }"
                  :title="formatValue(row[column.name])"
                  @dblclick="startCellEdit(row, column)"
                >
                  <input
                    v-if="isEditingCell(row, column)"
                    v-model="cellEdit.value"
                    class="cell-editor-input"
                    :disabled="cellEdit.saving"
                    @keydown.enter.prevent="commitCellEdit(row, column)"
                    @keydown.esc.prevent="cancelCellEdit"
                    @blur="commitCellEdit(row, column)"
                  >
                  <span v-else>{{ formatValue(row[column.name]) }}</span>
                </td>
                <td class="actions-cell">
                  <button class="icon-btn" type="button" title="Edit" @click="openEdit(row)">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
                    </svg>
                  </button>
                  <button class="icon-btn danger" type="button" title="Delete" @click="deleteRow(row)">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
                      <path d="M3 6h18" />
                      <path d="M8 6V4h8v2" />
                      <path d="M19 6 18 20H6L5 6" />
                    </svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </main>
    </section>

    <transition name="fade">
      <div v-if="editorOpen" class="modal-backdrop" @click.self="closeEditor">
        <section class="editor-modal" role="dialog" aria-modal="true" aria-label="Edit SQLite row">
          <header class="editor-head">
            <div>
              <h2>{{ editorMode === 'create' ? 'Add Row' : 'Edit Row' }}</h2>
              <span>{{ selectedTable }}<template v-if="editingRowid"> - rowid {{ editingRowid }}</template></span>
            </div>
            <button class="icon-btn" type="button" title="Close" @click="closeEditor">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            </button>
          </header>
          <textarea v-model="editorText" class="json-editor" spellcheck="false"></textarea>
          <div class="editor-foot">
            <span class="editor-error">{{ editorError }}</span>
            <div class="editor-actions">
              <button class="ghost-btn" type="button" @click="closeEditor" :disabled="saving">Cancel</button>
              <button class="primary-btn" type="button" @click="saveEditor" :disabled="saving">
                {{ saving ? 'Saving...' : 'Save' }}
              </button>
            </div>
          </div>
        </section>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.page { animation: pageIn 0.4s var(--ease-out); }

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.page-head h1 {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0;
}

.page-head p,
.meta-line {
  color: var(--text-secondary);
  font-size: 13px;
}

.head-actions,
.editor-actions,
.pager,
.actions-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.primary-btn,
.ghost-btn,
.icon-btn {
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.primary-btn,
.ghost-btn {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 13px;
  font-size: 13px;
  font-weight: 700;
}

.primary-btn {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

.primary-btn:hover { background: var(--primary-hover); }

.ghost-btn {
  background: var(--surface);
  color: var(--text-secondary);
}

.ghost-btn:hover,
.icon-btn:hover {
  color: var(--primary);
  background: var(--primary-soft);
  border-color: var(--primary-glow);
}

.ghost-btn.danger {
  color: var(--danger);
  background: var(--danger-soft);
  border-color: rgba(239, 68, 68, 0.18);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.icon-btn {
  width: 32px;
  height: 32px;
  display: inline-grid;
  place-items: center;
  background: var(--surface);
  color: var(--text-muted);
}

.icon-btn.danger:hover {
  color: var(--danger);
  background: var(--danger-soft);
  border-color: rgba(239, 68, 68, 0.18);
}

.error-bar {
  margin-bottom: 14px;
  padding: 10px 12px;
  border: 1px solid rgba(239, 68, 68, 0.18);
  border-radius: 8px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 13px;
  font-weight: 700;
}

.sql-panel {
  margin-bottom: 16px;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
}

.sql-head {
  min-height: 58px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
}

.sql-head h2 {
  font-size: 17px;
  font-weight: 800;
}

.sql-head p {
  color: var(--text-secondary);
  font-size: 12px;
}

.sql-editor {
  width: 100%;
  min-height: 150px;
  padding: 14px 16px;
  display: block;
  border: 0;
  resize: vertical;
  outline: none;
  background: #0f172a;
  color: #e5e7eb;
  font: 13px/1.6 'SF Mono', Consolas, monospace;
}

.sql-error {
  margin: 12px 14px;
}

.sql-result {
  border-top: 1px solid var(--border);
}

.sql-summary {
  min-height: 38px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  background: var(--bg);
}

.sql-summary span {
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 11px;
  font-weight: 800;
}

.sql-table-wrap {
  max-height: 340px;
  overflow: auto;
}

.sql-table {
  min-width: 640px;
}

.admin-shell {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 16px;
  min-height: 620px;
}

.table-list,
.data-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
  min-width: 0;
}

.table-list {
  overflow: hidden;
}

.table-list-head {
  height: 48px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

.table-list-head strong {
  color: var(--text);
}

.table-item {
  width: 100%;
  min-height: 48px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 2px;
  padding: 8px 14px;
  border: 0;
  border-bottom: 1px solid var(--border);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.table-item:hover,
.table-item.active {
  background: var(--primary-soft);
}

.table-name {
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
  font-size: 13px;
  font-weight: 700;
}

.table-meta {
  color: var(--text-muted);
  font-size: 12px;
}

.data-panel {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.data-toolbar {
  min-height: 64px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
}

.data-toolbar h2 {
  font-size: 18px;
  font-weight: 800;
}

.pager span {
  min-width: 110px;
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

.column-strip {
  padding: 10px 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}

.column-pill {
  max-width: 180px;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 11px;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty,
.state {
  min-height: 180px;
  display: grid;
  place-items: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 13px;
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

.table-wrap {
  overflow: auto;
  flex: 1;
}

.data-table {
  width: 100%;
  min-width: 860px;
  border-collapse: collapse;
}

.data-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  text-align: left;
  padding: 10px 12px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.data-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  font-size: 12px;
}

.data-table tbody tr:hover { background: rgba(0, 0, 0, 0.01); }

.rowid-col,
.rowid-cell {
  width: 80px;
  color: var(--text-muted);
  font-family: 'SF Mono', monospace;
}

.value-cell {
  max-width: 280px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.editable-cell {
  cursor: text;
}

.editable-cell:hover {
  background: #f8fafc;
}

.editable-cell.editing {
  padding: 5px 8px;
  background: #eef2ff;
}

.cell-editor-input {
  width: 100%;
  min-width: 160px;
  height: 32px;
  padding: 0 8px;
  border: 1px solid var(--primary-glow);
  border-radius: 6px;
  outline: none;
  background: #fff;
  color: var(--text);
  font: inherit;
  box-shadow: 0 0 0 3px var(--primary-soft);
}

.actions-col,
.actions-cell {
  width: 92px;
  white-space: nowrap;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(17, 24, 39, 0.38);
}

.editor-modal {
  width: min(760px, calc(100vw - 32px));
  max-height: min(760px, calc(100vh - 48px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-xl);
}

.editor-head {
  padding: 15px 16px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
}

.editor-head h2 {
  font-size: 17px;
  font-weight: 800;
}

.editor-head span {
  color: var(--text-muted);
  font-size: 12px;
}

.json-editor {
  width: 100%;
  min-height: 360px;
  flex: 1;
  padding: 14px 16px;
  border: 0;
  resize: vertical;
  outline: none;
  background: #0f172a;
  color: #e5e7eb;
  font: 13px/1.6 'SF Mono', Consolas, monospace;
}

.editor-foot {
  min-height: 58px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid var(--border);
}

.editor-error {
  color: var(--danger);
  font-size: 13px;
  font-weight: 700;
}

@media (max-width: 900px) {
  .page-head,
  .sql-head,
  .data-toolbar,
  .editor-foot {
    flex-direction: column;
    align-items: stretch;
  }

  .admin-shell {
    grid-template-columns: 1fr;
  }

  .table-list {
    max-height: 260px;
    overflow: auto;
  }

  .head-actions,
  .editor-actions {
    justify-content: flex-end;
  }
}
</style>
