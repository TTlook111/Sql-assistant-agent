/* ═══════════════════════════════════════════════════════════════════════
   Database Panel Component - DB Connection Management
   ═══════════════════════════════════════════════════════════════════════ */

import { getState, setState, subscribe } from '../state.js';
import { listDatabasesApi, connectDbApi, disconnectDbApi, getDbStatusApi } from '../api.js';
import { showToast } from './toast.js';
import { escapeHtml, debounce } from '../utils.js';

// ── DOM References ───────────────────────────────────────────────────────
let el = {};
let isLoadingDatabases = false;

function cacheDom() {
  el = {
    dbForm: document.getElementById('dbForm'),
    dbHost: document.getElementById('dbHost'),
    dbPort: document.getElementById('dbPort'),
    dbUser: document.getElementById('dbUser'),
    dbPassword: document.getElementById('dbPassword'),
    dbDatabase: document.getElementById('dbDatabase'),
    dbConnectBtn: document.getElementById('dbConnectBtn'),
    dbDisconnectBtn: document.getElementById('dbDisconnectBtn'),
    dbStatusBadge: document.getElementById('dbStatusBadge'),
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

// ── API Functions ────────────────────────────────────────────────────────

/**
 * 获取数据库列表（自动触发）
 */
async function fetchDatabaseList() {
  if (isLoadingDatabases) return;

  const host = el.dbHost?.value?.trim();
  const port = parseInt(el.dbPort?.value, 10) || 3306;
  const user = el.dbUser?.value?.trim();
  const password = el.dbPassword?.value || '';

  // 至少需要host和user
  if (!host || !user) {
    return;
  }

  isLoadingDatabases = true;

  try {
    const result = await listDatabasesApi({ host, port, user, password });
    const databases = result.databases || [];

    renderDatabaseSelect(databases);
  } catch (err) {
    // 静默失败，不显示toast
    console.error('获取数据库列表失败:', err);
  } finally {
    isLoadingDatabases = false;
  }
}

/**
 * 防抖版本的获取数据库列表
 */
const fetchDatabaseListDebounced = debounce(fetchDatabaseList, 1200);

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
 * 处理输入变化（自动获取数据库列表）
 */
function handleInputChange() {
  const { dbConnected } = getState();
  if (dbConnected) return;

  fetchDatabaseListDebounced();
}

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

    showToast(`已连接 ${result.database}`, 'success');
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

    // 重置数据库选择
    if (el.dbDatabase) {
      el.dbDatabase.innerHTML = '<option value="">-- 请填写连接信息 --</option>';
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

  // 输入框变化时自动获取数据库列表
  const inputs = [el.dbHost, el.dbPort, el.dbUser, el.dbPassword];
  inputs.forEach(input => {
    if (input) {
      input.addEventListener('input', handleInputChange);
    }
  });

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
  fetchDbStatus,
};
