/* ═══════════════════════════════════════════════════════════════════════
   Database Panel Component - DB Connection Management
   ═══════════════════════════════════════════════════════════════════════ */

import { getState, setState, subscribe } from '../state.js';
import { listDatabasesApi, connectDbApi, disconnectDbApi, getDbStatusApi } from '../api.js';
import { showToast } from './toast.js';
import { escapeHtml } from '../utils.js';

// ── DOM References ───────────────────────────────────────────────────────
let el = {};

function cacheDom() {
  el = {
    dbForm: document.getElementById('dbForm'),
    dbHost: document.getElementById('dbHost'),
    dbPort: document.getElementById('dbPort'),
    dbUser: document.getElementById('dbUser'),
    dbPassword: document.getElementById('dbPassword'),
    dbDatabase: document.getElementById('dbDatabase'),
    dbFetchDatabasesBtn: document.getElementById('dbFetchDatabasesBtn'),
    dbConnectBtn: document.getElementById('dbConnectBtn'),
    dbDisconnectBtn: document.getElementById('dbDisconnectBtn'),
    dbStatusBadge: document.getElementById('dbStatusBadge'),
    dbTablesPreview: document.getElementById('dbTablesPreview'),
    dbTablesList: document.getElementById('dbTablesList'),
  };
}

// ── Render Functions ─────────────────────────────────────────────────────

/**
 * 渲染数据库状态
 */
export function renderDbStatus() {
  const { dbConnected } = getState();

  if (el.dbStatusBadge) {
    el.dbStatusBadge.textContent = dbConnected ? '已连接' : '未连接';
    el.dbStatusBadge.className = `badge ${dbConnected ? 'badge-success' : ''}`;
  }

  if (el.dbConnectBtn) {
    el.dbConnectBtn.style.display = dbConnected ? 'none' : '';
  }

  if (el.dbDisconnectBtn) {
    el.dbDisconnectBtn.style.display = dbConnected ? '' : 'none';
  }

  if (el.dbFetchDatabasesBtn) {
    el.dbFetchDatabasesBtn.style.display = dbConnected ? 'none' : '';
  }

  // 禁用/启用表单字段
  const fields = [el.dbHost, el.dbPort, el.dbUser, el.dbPassword, el.dbDatabase];
  fields.forEach(field => {
    if (field) field.disabled = dbConnected;
  });
}

/**
 * 渲染数据库下拉列表
 * @param {string[]} databases - 数据库名称数组
 */
function renderDatabaseSelect(databases) {
  if (!el.dbDatabase) return;

  // 保存当前值
  const currentValue = el.dbDatabase.value;

  // 清空选项
  el.dbDatabase.innerHTML = '';

  // 添加默认选项
  const defaultOption = document.createElement('option');
  defaultOption.value = '';
  defaultOption.textContent = '-- 请选择数据库 --';
  el.dbDatabase.appendChild(defaultOption);

  // 添加数据库选项
  databases.forEach(db => {
    const option = document.createElement('option');
    option.value = db;
    option.textContent = db;
    el.dbDatabase.appendChild(option);
  });

  // 恢复之前的值
  if (currentValue && databases.includes(currentValue)) {
    el.dbDatabase.value = currentValue;
  }
}

/**
 * 渲染数据库表列表
 * @param {Array} tables - 表数组
 */
export function renderDbTables(tables) {
  if (!el.dbTablesPreview) return;

  if (!tables || !tables.length) {
    el.dbTablesPreview.style.display = 'none';
    return;
  }

  el.dbTablesPreview.style.display = '';
  if (el.dbTablesList) {
    el.dbTablesList.innerHTML = '';

    const frag = document.createDocumentFragment();

    tables.forEach(t => {
      const div = document.createElement('div');
      div.className = 'db-table-item';
      const comment = t.comment ? ` — ${escapeHtml(t.comment)}` : '';

      div.innerHTML = `
        <span>
          <span class="db-table-name">${escapeHtml(t.name)}</span>
          <span class="db-table-comment">${comment}</span>
        </span>
        <span class="db-table-meta">${t.columns_count} 列</span>
      `;

      frag.appendChild(div);
    });

    el.dbTablesList.appendChild(frag);
  }
}

// ── API Functions ────────────────────────────────────────────────────────

/**
 * 获取数据库列表
 */
async function fetchDatabaseList() {
  const host = el.dbHost?.value?.trim();
  const port = parseInt(el.dbPort?.value, 10) || 3306;
  const user = el.dbUser?.value?.trim();
  const password = el.dbPassword?.value || '';

  if (!host || !user) {
    showToast('请先填写 Host 和 User。', 'warning');
    return;
  }

  if (el.dbFetchDatabasesBtn) {
    el.dbFetchDatabasesBtn.disabled = true;
    el.dbFetchDatabasesBtn.textContent = '获取中...';
  }

  try {
    const result = await listDatabasesApi({ host, port, user, password });
    const databases = result.databases || [];

    renderDatabaseSelect(databases);

    if (databases.length > 0) {
      showToast(`获取到 ${databases.length} 个数据库`, 'success');
    } else {
      showToast('未找到用户数据库', 'warning');
    }
  } catch (err) {
    showToast(err.message || '获取数据库列表失败', 'error');
  } finally {
    if (el.dbFetchDatabasesBtn) {
      el.dbFetchDatabasesBtn.disabled = false;
      el.dbFetchDatabasesBtn.textContent = '获取数据库列表';
    }
  }
}

/**
 * 获取数据库状态
 */
export async function fetchDbStatus() {
  try {
    const result = await getDbStatusApi();
    const { dbConnected } = getState();

    setState({ dbConnected: result.connected || false });

    if (result.connected) {
      if (el.dbHost) el.dbHost.value = result.host || '';
      if (el.dbPort) el.dbPort.value = result.port || 3306;
      if (el.dbUser) el.dbUser.value = result.user || '';
      if (el.dbDatabase) {
        // 如果已连接，设置为只读显示
        el.dbDatabase.innerHTML = `<option value="${escapeHtml(result.database || '')}">${escapeHtml(result.database || '')}</option>`;
      }
    }

    renderDbStatus();
  } catch {
    // 忽略错误
  }
}

// ── Event Handlers ───────────────────────────────────────────────────────

/**
 * 处理数据库连接表单提交
 */
async function handleConnect(e) {
  e.preventDefault();

  const host = el.dbHost?.value?.trim();
  const port = parseInt(el.dbPort?.value, 10) || 3306;
  const user = el.dbUser?.value?.trim();
  const password = el.dbPassword?.value || '';
  const database = el.dbDatabase?.value?.trim();

  if (!host || !user || !database) {
    showToast('请填写 Host、User 并选择 Database。', 'warning');
    return;
  }

  if (el.dbConnectBtn) {
    el.dbConnectBtn.disabled = true;
    el.dbConnectBtn.textContent = '连接中...';
  }

  try {
    const result = await connectDbApi({ host, port, user, password, database });

    setState({
      dbConnected: true,
      dbConfig: { host, port, user, database },
      dbTables: result.tables || [],
    });

    renderDbStatus();
    renderDbTables(result.tables || []);

    showToast(`已连接 ${result.database}，共 ${(result.tables || []).length} 张表`, 'success');
  } catch (err) {
    showToast(err.message || '连接失败', 'error');
  } finally {
    if (el.dbConnectBtn) {
      el.dbConnectBtn.disabled = false;
      el.dbConnectBtn.textContent = '连接';
    }
  }
}

/**
 * 处理断开连接按钮点击
 */
async function handleDisconnect() {
  try {
    await disconnectDbApi();

    setState({
      dbConnected: false,
      dbConfig: null,
      dbTables: [],
    });

    renderDbStatus();
    renderDbTables([]);

    // 重置数据库选择为输入模式
    if (el.dbDatabase) {
      el.dbDatabase.innerHTML = '<option value="">-- 请先获取数据库列表 --</option>';
    }

    if (el.dbPassword) {
      el.dbPassword.value = '';
    }

    showToast('已断开连接', 'success');
  } catch (err) {
    showToast(err.message || '断开失败', 'error');
  }
}

// ── Initialize ───────────────────────────────────────────────────────────

/**
 * 初始化数据库面板组件
 */
export function initDbPanel() {
  cacheDom();

  // 获取初始状态
  fetchDbStatus();

  // 获取数据库列表按钮
  if (el.dbFetchDatabasesBtn) {
    el.dbFetchDatabasesBtn.addEventListener('click', fetchDatabaseList);
  }

  // 连接表单提交
  if (el.dbForm) {
    el.dbForm.addEventListener('submit', handleConnect);
  }

  // 断开连接按钮
  if (el.dbDisconnectBtn) {
    el.dbDisconnectBtn.addEventListener('click', handleDisconnect);
  }

  // 订阅状态变化
  subscribe('dbConnected', () => {
    renderDbStatus();
  });
}

export default {
  initDbPanel,
  renderDbStatus,
  renderDbTables,
  fetchDbStatus,
};