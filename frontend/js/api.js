/* ═══════════════════════════════════════════════════════════════════════
   API Client - Backend Communication Layer
   ═══════════════════════════════════════════════════════════════════════ */

import { getState } from './state.js';

const API_BASE = '/api';

// ── Core Request Helper ──────────────────────────────────────────────────

/**
 * 通用API请求封装
 * @param {string} path - API路径
 * @param {object} options - fetch选项
 * @returns {Promise<any>} 响应数据
 */
async function apiRequest(path, options = {}) {
  const { token } = getState();

  const headers = {
    ...(options.headers || {}),
  };

  // 添加认证头
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // 如果不是FormData，设置Content-Type
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  // 处理401未授权
  if (response.status === 401) {
    // 触发登出事件
    window.dispatchEvent(new CustomEvent('auth:logout'));
    throw new Error('登录已过期，请重新登录。');
  }

  // 处理错误响应
  if (!response.ok) {
    let message = `请求失败: ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // 忽略JSON解析错误
    }
    throw new Error(message);
  }

  // 处理204无内容
  if (response.status === 204) return null;

  // 解析响应
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
}

// ── Auth API ─────────────────────────────────────────────────────────────

/**
 * 用户登录
 * @param {string} username - 用户名
 * @param {string} password - 密码
 * @returns {Promise<{token: string, username: string}>}
 */
export async function loginApi(username, password) {
  return apiRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

/**
 * 用户注册
 * @param {string} username - 用户名
 * @param {string} password - 密码
 * @returns {Promise<{token: string, username: string}>}
 */
export async function registerApi(username, password) {
  return apiRequest('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

/**
 * 验证当前用户
 * @returns {Promise<{user_id: number, username: string}>}
 */
export async function getMeApi() {
  return apiRequest('/auth/me');
}

// ── Skills API ───────────────────────────────────────────────────────────

/**
 * 获取技能列表
 * @returns {Promise<{items: Array}>}
 */
export async function fetchSkillsApi() {
  return apiRequest('/skills');
}

/**
 * 删除技能
 * @param {string} skillId - 技能ID
 * @returns {Promise<{ok: boolean}>}
 */
export async function deleteSkillApi(skillId) {
  return apiRequest(`/skills/${skillId}`, {
    method: 'DELETE',
  });
}

/**
 * 批量删除技能
 * @param {string[]} ids - 技能ID数组
 * @returns {Promise<{deleted_count: number}>}
 */
export async function batchDeleteSkillsApi(ids) {
  return apiRequest('/skills/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  });
}

/**
 * 上传技能文件
 * @param {File} file - 文件对象
 * @returns {Promise<{imported_count: number, items: Array}>}
 */
export async function uploadSkillsApi(file) {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest('/skills/upload', {
    method: 'POST',
    body: formData,
  });
}

// ── Chat API ─────────────────────────────────────────────────────────────

/**
 * 发送聊天消息
 * @param {string} message - 消息内容
 * @param {string|null} threadId - 会话ID（可选）
 * @returns {Promise<{thread_id: string, answer: string, sql_query: string, validation_passed: boolean}>}
 */
export async function sendChatApi(message, threadId = null) {
  return apiRequest('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, thread_id: threadId }),
  });
}

/**
 * 获取会话列表
 * @returns {Promise<{items: Array}>}
 */
export async function fetchThreadsApi() {
  return apiRequest('/chat/threads');
}

/**
 * 获取会话消息
 * @param {string} threadId - 会话ID
 * @returns {Promise<{thread_id: string, messages: Array}>}
 */
export async function fetchThreadMessagesApi(threadId) {
  return apiRequest(`/chat/threads/${threadId}`);
}

// ── Database API ─────────────────────────────────────────────────────────

/**
 * 连接数据库
 * @param {object} config - 数据库配置
 * @param {string} config.host - 主机地址
 * @param {number} config.port - 端口
 * @param {string} config.user - 用户名
 * @param {string} config.password - 密码
 * @param {string} config.database - 数据库名
 * @returns {Promise<{tables: Array, database: string}>}
 */
export async function connectDbApi(config) {
  return apiRequest('/database/connect', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

/**
 * 断开数据库连接
 * @returns {Promise<{disconnected: boolean}>}
 */
export async function disconnectDbApi() {
  return apiRequest('/database/disconnect', {
    method: 'POST',
  });
}

/**
 * 获取数据库状态
 * @returns {Promise<{connected: boolean, host?: string, port?: number, user?: string, database?: string}>}
 */
export async function getDbStatusApi() {
  return apiRequest('/database/status');
}

// ── Health API ───────────────────────────────────────────────────────────

/**
 * 健康检查
 * @returns {Promise<{status: string}>}
 */
export async function healthCheckApi() {
  return apiRequest('/health');
}

export default {
  loginApi,
  registerApi,
  getMeApi,
  fetchSkillsApi,
  deleteSkillApi,
  batchDeleteSkillsApi,
  uploadSkillsApi,
  sendChatApi,
  fetchThreadsApi,
  fetchThreadMessagesApi,
  connectDbApi,
  disconnectDbApi,
  getDbStatusApi,
  healthCheckApi,
};