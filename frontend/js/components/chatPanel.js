/* ═══════════════════════════════════════════════════════════════════════
   Chat Panel Component - Chat Window & Thread History
   ═══════════════════════════════════════════════════════════════════════ */

import { getState, setState, subscribe, saveState } from '../state.js';
import { sendChatApi, fetchThreadsApi, fetchThreadMessagesApi } from '../api.js';
import { showToast } from './toast.js';
import { escapeHtml, formatRelativeTime } from '../utils.js';

// ── DOM References ───────────────────────────────────────────────────────
let el = {};

function cacheDom() {
  el = {
    chatWindow: document.getElementById('chatWindow'),
    chatForm: document.getElementById('chatForm'),
    chatInput: document.getElementById('chatInput'),
    chatModeTip: document.getElementById('chatModeTip'),
    newChatBtn: document.getElementById('newChatBtn'),
    toggleHistoryBtn: document.getElementById('toggleHistoryBtn'),
    threadHistory: document.getElementById('threadHistory'),
    threadList: document.getElementById('threadList'),
  };
}

// ── Helper Functions ─────────────────────────────────────────────────────

/**
 * 渲染数据表格
 * @param {Array} data - 数据数组
 * @param {Array} columns - 列名数组
 * @returns {HTMLElement} 表格元素
 */
function renderDataTable(data, columns) {
  if (!data || !data.length || !columns || !columns.length) {
    return null;
  }

  const tableWrapper = document.createElement('div');
  tableWrapper.className = 'data-table-wrapper';

  const table = document.createElement('table');
  table.className = 'data-table';

  // 表头
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  columns.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // 表体
  const tbody = document.createElement('tbody');
  data.forEach(row => {
    const tr = document.createElement('tr');
    columns.forEach(col => {
      const td = document.createElement('td');
      const value = row[col];
      td.textContent = value === null ? 'NULL' : String(value);
      if (value === null) {
        td.className = 'null-value';
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  tableWrapper.appendChild(table);
  return tableWrapper;
}

// ── Render Functions ─────────────────────────────────────────────────────

/**
 * 渲染聊天窗口
 */
export function renderChatWindow() {
  if (!el.chatWindow) return;

  el.chatWindow.innerHTML = '';

  const { chats } = getState();

  if (!chats.length) {
    // 显示欢迎消息
    const welcomeHtml = `
      <div class="empty-state">
        <div class="empty-state-icon">💬</div>
        <div class="empty-state-title">开始对话</div>
        <div class="empty-state-text">输入你的问题，AI助手将查询数据库并返回结果</div>
      </div>
    `;
    el.chatWindow.innerHTML = welcomeHtml;
    return;
  }

  const frag = document.createDocumentFragment();

  chats.forEach(msg => {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${msg.role}`;

    // 头像
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = msg.role === 'user' ? 'U' : 'AI';

    // 消息内容
    const content = document.createElement('div');
    content.className = 'message-content';

    // 气泡
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = msg.content;
    content.appendChild(bubble);

    // 数据表格（优先显示）
    if (msg.data && msg.data.length > 0 && msg.columns && msg.columns.length > 0) {
      const tableContainer = document.createElement('div');
      tableContainer.className = 'data-result-container';

      // 结果摘要
      const summary = document.createElement('div');
      summary.className = 'data-summary';
      summary.textContent = `查询结果：${msg.row_count || msg.data.length} 条记录`;
      tableContainer.appendChild(summary);

      // 渲染表格
      const table = renderDataTable(msg.data, msg.columns);
      if (table) {
        tableContainer.appendChild(table);
      }

      content.appendChild(tableContainer);
    }
    // 如果有错误，显示错误信息
    else if (msg.execution_error) {
      const errorBlock = document.createElement('div');
      errorBlock.className = 'error-block';
      errorBlock.textContent = `执行错误：${msg.execution_error}`;
      content.appendChild(errorBlock);
    }
    // SQL代码块（折叠显示）
    else if (msg.sql_query) {
      const sqlBlock = document.createElement('details');
      sqlBlock.className = 'sql-block';

      const sqlHeader = document.createElement('summary');
      sqlHeader.className = 'sql-header';
      sqlHeader.textContent = '查看 SQL 查询';
      sqlBlock.appendChild(sqlHeader);

      const sqlContent = document.createElement('div');
      sqlContent.className = 'sql-content';

      const code = document.createElement('code');
      code.textContent = msg.sql_query;
      sqlContent.appendChild(code);

      sqlBlock.appendChild(sqlContent);
      content.appendChild(sqlBlock);
    }

    // 时间
    if (msg.time) {
      const time = document.createElement('div');
      time.className = 'message-time';
      time.textContent = formatRelativeTime(msg.time);
      content.appendChild(time);
    }

    wrapper.appendChild(avatar);
    wrapper.appendChild(content);
    frag.appendChild(wrapper);
  });

  el.chatWindow.appendChild(frag);

  // 滚动到底部
  el.chatWindow.scrollTop = el.chatWindow.scrollHeight;
}

/**
 * 渲染会话历史列表
 */
export function renderThreadList() {
  if (!el.threadList) return;

  el.threadList.innerHTML = '';

  const { threads, chatThreadId } = getState();

  if (!threads.length) {
    el.threadList.innerHTML = '<div class="empty-sidebar"><div class="empty-sidebar-icon">📝</div><div class="empty-sidebar-text">暂无历史对话</div></div>';
    return;
  }

  const frag = document.createDocumentFragment();

  threads.forEach(t => {
    const div = document.createElement('div');
    div.className = `thread-item ${t.thread_id === chatThreadId ? 'active' : ''}`;

    const title = t.first_message || '空对话';
    const count = t.message_count || 0;

    div.innerHTML = `
      <div class="thread-item-icon">💬</div>
      <div class="thread-item-content">
        <div class="thread-item-title">${escapeHtml(title)}</div>
        <div class="thread-item-meta">${count} 条消息</div>
      </div>
      <span class="thread-item-arrow">›</span>
    `;

    div.addEventListener('click', () => loadThread(t.thread_id));
    frag.appendChild(div);
  });

  el.threadList.appendChild(frag);
}

// ── API Functions ────────────────────────────────────────────────────────

/**
 * 添加聊天消息
 * @param {string} role - 角色：user | bot
 * @param {string} content - 消息内容
 * @param {object} meta - 额外数据
 */
function addChatMessage(role, content, meta = {}) {
  const { chats } = getState();
  const newChats = [...chats, { role, content, time: Date.now(), ...meta }];
  setState({ chats: newChats });
}

/**
 * 获取会话列表
 */
export async function fetchThreads() {
  try {
    const result = await fetchThreadsApi();
    setState({ threads: result.items || [] });
    renderThreadList();
  } catch {
    // 忽略错误
  }
}

/**
 * 加载会话消息
 * @param {string} threadId - 会话ID
 */
export async function loadThread(threadId) {
  try {
    const result = await fetchThreadMessagesApi(threadId);
    const messages = result.messages || [];

    setState({
      chatThreadId: threadId,
      chats: messages.map(m => ({
        role: m.role,
        content: m.content,
        sql_query: m.sql_query || '',
        validation_passed: true,
        data: m.data || [],
        columns: m.columns || [],
        row_count: m.row_count || 0,
        execution_error: m.execution_error || '',
        time: Date.now(),
      })),
      historyVisible: false,
    });

    if (el.threadHistory) {
      el.threadHistory.style.display = 'none';
    }

    renderChatWindow();
  } catch (err) {
    showToast(err.message || '加载对话失败', 'error');
  }
}

/**
 * 开始新对话
 */
export function startNewChat() {
  setState({
    chatThreadId: null,
    chats: [],
  });
  renderChatWindow();
}

// ── Event Handlers ───────────────────────────────────────────────────────

/**
 * 处理聊天表单提交
 */
async function handleChatSubmit(e) {
  e.preventDefault();

  const text = el.chatInput?.value?.trim();
  if (!text) return;

  // 检查是否已连接数据库
  const { dbConnected } = getState();
  if (!dbConnected) {
    showToast('请先连接数据库', 'warning');
    return;
  }

  // 添加用户消息
  addChatMessage('user', text);
  renderChatWindow();

  // 清空输入框
  if (el.chatInput) {
    el.chatInput.value = '';
  }

  // 显示加载状态
  setState({ isLoading: true });

  try {
    const { chatThreadId } = getState();
    const result = await sendChatApi(text, chatThreadId);

    // 更新会话ID
    if (result.thread_id) {
      setState({ chatThreadId: result.thread_id });
    }

    // 添加AI回复（包含数据）
    addChatMessage('bot', result.answer || '助手未返回内容。', {
      sql_query: result.sql_query || '',
      validation_passed: result.validation_passed !== false,
      data: result.data || [],
      columns: result.columns || [],
      row_count: result.row_count || 0,
      execution_error: result.execution_error || '',
    });

    renderChatWindow();
    saveState();
  } catch (err) {
    addChatMessage('bot', `请求失败：${err.message || '未知错误'}`);
    renderChatWindow();
    saveState();
  } finally {
    setState({ isLoading: false });
  }
}

/**
 * 处理新对话按钮点击
 */
function handleNewChatClick() {
  startNewChat();
  showToast('已开始新对话', 'info');
}

/**
 * 处理历史记录按钮点击
 */
async function handleToggleHistoryClick() {
  const { historyVisible } = getState();
  const newHistoryVisible = !historyVisible;

  setState({ historyVisible: newHistoryVisible });

  if (el.threadHistory) {
    el.threadHistory.style.display = newHistoryVisible ? '' : 'none';
  }

  if (newHistoryVisible) {
    await fetchThreads();
  }
}

// ── Initialize ───────────────────────────────────────────────────────────

/**
 * 初始化聊天面板组件
 */
export function initChatPanel() {
  cacheDom();

  // 聊天表单提交
  if (el.chatForm) {
    el.chatForm.addEventListener('submit', handleChatSubmit);
  }

  // 新对话按钮
  if (el.newChatBtn) {
    el.newChatBtn.addEventListener('click', handleNewChatClick);
  }

  // 历史记录按钮
  if (el.toggleHistoryBtn) {
    el.toggleHistoryBtn.addEventListener('click', handleToggleHistoryClick);
  }

  // 订阅状态变化
  subscribe(['chats', 'chatThreadId'], () => {
    renderChatWindow();
  });

  // 初始渲染
  renderChatWindow();
}

export default {
  initChatPanel,
  renderChatWindow,
  renderThreadList,
  fetchThreads,
  loadThread,
  startNewChat,
};