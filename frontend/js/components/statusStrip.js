/* ═══════════════════════════════════════════════════════════════════════
   Status Strip Component - Top Status Bar
   ═══════════════════════════════════════════════════════════════════════ */

import { getState, subscribe } from '../state.js';

// ── DOM References ───────────────────────────────────────────────────────
let el = {};

function cacheDom() {
  el = {
    userBadge: document.getElementById('userBadge'),
    modeBadge: document.getElementById('modeBadge'),
    countBadge: document.getElementById('countBadge'),
    chatModeTip: document.getElementById('chatModeTip'),
    currentUser: document.getElementById('currentUser'),
  };
}

// ── Helper Functions ─────────────────────────────────────────────────────

/**
 * 检查是否有上传的技能
 * @returns {boolean}
 */
function hasUploadedSkills() {
  const { skills } = getState();
  return skills.some(s => Boolean((s.source_file || '').trim()));
}

/**
 * 获取生效模式
 * @returns {string} 'uploaded' | 'builtin_fallback' | 'none'
 */
export function getEffectiveMode() {
  const { skills } = getState();
  if (!skills.length) return 'none';
  return hasUploadedSkills() ? 'uploaded' : 'builtin_fallback';
}

/**
 * 获取模式标签
 * @returns {string}
 */
export function getModeLabel() {
  const mode = getEffectiveMode();
  if (mode === 'uploaded') return '上传优先生效';
  if (mode === 'builtin_fallback') return '内置回退';
  return '无技能上下文';
}

/**
 * 检查技能是否生效
 * @param {object} skill - 技能对象
 * @returns {boolean}
 */
export function isSkillEffective(skill) {
  const uploaded = Boolean((skill.source_file || '').trim());
  return getEffectiveMode() !== 'uploaded' || uploaded;
}

// ── Render Functions ─────────────────────────────────────────────────────

/**
 * 渲染状态栏
 */
export function renderStatusStrip() {
  const { skills, username } = getState();
  const uploadedCount = skills.filter(s => Boolean((s.source_file || '').trim())).length;
  const modeText = getModeLabel();

  if (el.userBadge) el.userBadge.textContent = `用户：${username}`;
  if (el.modeBadge) el.modeBadge.textContent = `生效模式：${modeText}`;
  if (el.countBadge) el.countBadge.textContent = `技能数：${skills.length}（上传 ${uploadedCount}）`;
  if (el.chatModeTip) el.chatModeTip.textContent = `路由模式：${modeText}`;
  if (el.currentUser) el.currentUser.textContent = username;
}

// ── Initialize ───────────────────────────────────────────────────────────

/**
 * 初始化状态栏组件
 */
export function initStatusStrip() {
  cacheDom();

  // 订阅状态变化
  subscribe(['skills', 'username'], () => {
    renderStatusStrip();
  });

  // 初始渲染
  renderStatusStrip();
}

export default {
  initStatusStrip,
  renderStatusStrip,
  getEffectiveMode,
  getModeLabel,
  isSkillEffective,
};