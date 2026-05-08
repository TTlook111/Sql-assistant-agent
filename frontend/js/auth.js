/* ═══════════════════════════════════════════════════════════════════════
   Auth Module - Authentication Logic
   ═══════════════════════════════════════════════════════════════════════ */

import { getState, setState, saveAuth, clearAuth, loadState } from './state.js';
import { loginApi, registerApi, getMeApi, fetchSkillsApi, fetchThreadsApi } from './api.js';
import { showToast } from './components/toast.js';

// ── DOM References ───────────────────────────────────────────────────────
let el = {};

function cacheDom() {
  el = {
    authOverlay: document.getElementById('authOverlay'),
    appShell: document.getElementById('appShell'),
    authForm: document.getElementById('authForm'),
    authUsername: document.getElementById('authUsername'),
    authPassword: document.getElementById('authPassword'),
    loginBtn: document.getElementById('loginBtn'),
    registerBtn: document.getElementById('registerBtn'),
    authError: document.getElementById('authError'),
    currentUser: document.getElementById('currentUser'),
    logoutBtn: document.getElementById('logoutBtn'),
  };
}

// ── Auth Functions ───────────────────────────────────────────────────────

/**
 * 显示主应用
 */
export function showApp() {
  if (el.authOverlay) el.authOverlay.classList.add('hidden');
  if (el.appShell) el.appShell.style.display = '';
  if (el.currentUser) el.currentUser.textContent = getState().username;
}

/**
 * 显示登录界面
 */
export function showAuth() {
  if (el.authOverlay) el.authOverlay.classList.remove('hidden');
  if (el.appShell) el.appShell.style.display = 'none';
}

/**
 * 处理登录
 * @param {string} username - 用户名
 * @param {string} password - 密码
 */
async function handleLogin(username, password) {
  if (el.authError) el.authError.textContent = '';

  try {
    const result = await loginApi(username, password);
    saveAuth(result.token, result.username || username);
    await onLoginSuccess();
  } catch (error) {
    if (el.authError) el.authError.textContent = error.message || '登录失败';
    showToast(error.message || '登录失败', 'error');
  }
}

/**
 * 处理注册
 * @param {string} username - 用户名
 * @param {string} password - 密码
 */
async function handleRegister(username, password) {
  if (el.authError) el.authError.textContent = '';

  try {
    const result = await registerApi(username, password);
    saveAuth(result.token, result.username || username);
    await onLoginSuccess();
    showToast('注册成功！', 'success');
  } catch (error) {
    if (el.authError) el.authError.textContent = error.message || '注册失败';
    showToast(error.message || '注册失败', 'error');
  }
}

/**
 * 处理登出
 */
export function handleLogout() {
  clearAuth();
  showAuth();
  showToast('已退出登录', 'info');
}

/**
 * 登录成功后的处理
 */
export async function onLoginSuccess() {
  showApp();
  loadState();

  // 加载技能列表
  try {
    const result = await fetchSkillsApi();
    setState({ skills: result.items || [] });
  } catch (error) {
    showToast(`加载技能失败：${error.message || '未知错误'}`, 'error');
  }

  // 加载历史对话列表
  try {
    const result = await fetchThreadsApi();
    setState({ threads: result.items || [] });
  } catch (error) {
    // 忽略错误
  }

  // 触发登录成功事件
  window.dispatchEvent(new CustomEvent('auth:login'));
}

/**
 * 检查认证状态
 */
export async function checkAuth() {
  const { token } = getState();

  if (!token) {
    showAuth();
    return false;
  }

  try {
    await getMeApi();
    await onLoginSuccess();
    return true;
  } catch {
    clearAuth();
    showAuth();
    return false;
  }
}

// ── Event Binding ────────────────────────────────────────────────────────

/**
 * 初始化认证事件
 */
export function initAuth() {
  cacheDom();

  // 登录表单提交
  if (el.authForm) {
    el.authForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = el.authUsername?.value?.trim();
      const password = el.authPassword?.value;

      if (!username || !password) {
        if (el.authError) el.authError.textContent = '请输入用户名和密码。';
        return;
      }

      if (el.loginBtn) el.loginBtn.disabled = true;
      if (el.registerBtn) el.registerBtn.disabled = true;

      await handleLogin(username, password);

      if (el.loginBtn) el.loginBtn.disabled = false;
      if (el.registerBtn) el.registerBtn.disabled = false;
    });
  }

  // 注册按钮点击
  if (el.registerBtn) {
    el.registerBtn.addEventListener('click', async () => {
      const username = el.authUsername?.value?.trim();
      const password = el.authPassword?.value;

      if (!username || !password) {
        if (el.authError) el.authError.textContent = '请输入用户名和密码。';
        return;
      }

      if (password.length < 4) {
        if (el.authError) el.authError.textContent = '密码至少 4 位。';
        return;
      }

      el.loginBtn.disabled = true;
      el.registerBtn.disabled = true;

      await handleRegister(username, password);

      el.loginBtn.disabled = false;
      el.registerBtn.disabled = false;
    });
  }

  // 登出按钮点击
  if (el.logoutBtn) {
    el.logoutBtn.addEventListener('click', handleLogout);
  }

  // 监听登出事件（来自API层的401错误）
  window.addEventListener('auth:logout', handleLogout);
}

export default {
  initAuth,
  checkAuth,
  handleLogout,
  showApp,
  showAuth,
};