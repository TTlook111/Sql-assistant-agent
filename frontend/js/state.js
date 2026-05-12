/* ═══════════════════════════════════════════════════════════════════════
   State Management - Global State with Pub/Sub
   ═══════════════════════════════════════════════════════════════════════ */

import { safeJsonParse } from './utils.js';

// ── Storage Keys ────────────────────────────────────────────────────────
const STORAGE_KEY = 'skill_studio_data_v1';
const TOKEN_KEY = 'skill_studio_token';
const USERNAME_KEY = 'skill_studio_username';

// ── State Object ────────────────────────────────────────────────────────
const state = {
  // Auth
  token: localStorage.getItem(TOKEN_KEY) || '',
  username: localStorage.getItem(USERNAME_KEY) || '',
  isAuthenticated: false,

  // Skills
  skills: [],
  selectedIds: new Set(),
  searchKeyword: '',

  // Chat
  chats: [],
  chatThreadId: null,
  threads: [],
  historyVisible: false,
  isLoading: false,

  // Database
  dbConnected: false,
  dbConfig: null,
  dbTables: [],

  // UI
  sidebarOpen: true,
  activePanel: 'chat', // 'chat' | 'skills' | 'database'
};

// ── Subscribers ──────────────────────────────────────────────────────────
const subscribers = new Map();

/**
 * 订阅状态变化
 * @param {string|string[]} keys - 要监听的状态键名
 * @param {Function} callback - 回调函数
 * @returns {Function} 取消订阅函数
 */
export function subscribe(keys, callback) {
  const keyArray = Array.isArray(keys) ? keys : [keys];

  keyArray.forEach(key => {
    if (!subscribers.has(key)) {
      subscribers.set(key, new Set());
    }
    subscribers.get(key).add(callback);
  });

  // 返回取消订阅函数
  return () => {
    keyArray.forEach(key => {
      const subs = subscribers.get(key);
      if (subs) {
        subs.delete(callback);
        if (subs.size === 0) {
          subscribers.delete(key);
        }
      }
    });
  };
}

/**
 * 通知订阅者
 * @param {string[]} changedKeys - 变化的键名数组
 */
function notify(changedKeys) {
  const notifiedCallbacks = new Set();

  changedKeys.forEach(key => {
    const subs = subscribers.get(key);
    if (subs) {
      subs.forEach(callback => {
        if (!notifiedCallbacks.has(callback)) {
          notifiedCallbacks.add(callback);
          try {
            callback(state[key], key);
          } catch (error) {
            console.error(`State subscriber error for key "${key}":`, error);
          }
        }
      });
    }
  });
}

/**
 * 更新状态
 * @param {object} patch - 要更新的状态片段
 */
export function setState(patch) {
  const changedKeys = [];

  Object.entries(patch).forEach(([key, value]) => {
    if (key in state) {
      const oldValue = state[key];
      state[key] = value;

      // 检查是否真的变化了
      if (oldValue !== value) {
        changedKeys.push(key);
      }
    } else {
      console.warn(`State key "${key}" does not exist.`);
    }
  });

  // 自动保存到localStorage
  if (changedKeys.some(key => ['chats', 'chatThreadId'].includes(key))) {
    saveState();
  }

  // 通知订阅者
  if (changedKeys.length > 0) {
    notify(changedKeys);
  }
}

/**
 * 获取当前状态（只读副本）
 * @returns {object} 状态副本
 */
export function getState() {
  return {
    ...state,
    selectedIds: new Set(state.selectedIds),  // 深拷贝Set
  };
}

/**
 * 获取单个状态值
 * @param {string} key - 状态键名
 * @returns {*} 状态值
 */
export function get(key) {
  return state[key];
}

// ── Persistence ──────────────────────────────────────────────────────────

function getStorageKey() {
  return `${STORAGE_KEY}:${state.username || 'guest'}`;
}

/**
 * 保存状态到localStorage
 */
export function saveState() {
  try {
    const data = {
      chats: state.chats,
      chatThreadId: state.chatThreadId,
    };
    localStorage.setItem(getStorageKey(), JSON.stringify(data));
  } catch (error) {
    console.error('Failed to save state:', error);
  }
}

/**
 * 从localStorage加载状态
 */
export function loadState() {
  try {
    const raw = localStorage.getItem(getStorageKey());
    if (!raw) return;

    const data = safeJsonParse(raw, {});
    if (data.chats) state.chats = data.chats;
    if (data.chatThreadId) state.chatThreadId = data.chatThreadId;
  } catch (error) {
    console.error('Failed to load state:', error);
  }
}

/**
 * 保存认证信息
 * @param {string} token - JWT token
 * @param {string} username - 用户名
 */
export function saveAuth(token, username) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USERNAME_KEY, username);
  setState({ token, username, isAuthenticated: true });
}

/**
 * 清除认证信息
 */
export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
  setState({
    token: '',
    username: '',
    isAuthenticated: false,
    skills: [],
    chats: [],
    chatThreadId: null,
    threads: [],
    dbConnected: false,
    dbConfig: null,
    dbTables: [],
  });
}

/**
 * 清除所有本地数据
 */
export function clearAllData() {
  // 清除所有用户的存储数据
  const keys = Object.keys(localStorage);
  keys.forEach(key => {
    if (key.startsWith(STORAGE_KEY) || key === TOKEN_KEY || key === USERNAME_KEY) {
      localStorage.removeItem(key);
    }
  });
}

// ── Initialize ──────────────────────────────────────────────────────────

// 初始化时检查是否有有效的token
state.isAuthenticated = !!state.token;

export default {
  subscribe,
  setState,
  getState,
  get,
  saveState,
  loadState,
  saveAuth,
  clearAuth,
  clearAllData,
};