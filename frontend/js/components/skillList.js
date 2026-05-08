/* ═══════════════════════════════════════════════════════════════════════
   Skill List Component - Skills Management
   ═══════════════════════════════════════════════════════════════════════ */

import { getState, setState, subscribe } from '../state.js';
import { deleteSkillApi, batchDeleteSkillsApi, fetchSkillsApi } from '../api.js';
import { showToast } from './toast.js';
import { isSkillEffective } from './statusStrip.js';
import { escapeHtml } from '../utils.js';

// ── DOM References ───────────────────────────────────────────────────────
let el = {};

function cacheDom() {
  el = {
    skillList: document.getElementById('skillList'),
    emptyState: document.getElementById('emptyState'),
    searchInput: document.getElementById('searchInput'),
    selectAllCheckbox: document.getElementById('selectAllCheckbox'),
    batchDeleteBtn: document.getElementById('batchDeleteBtn'),
  };
}

// ── Helper Functions ─────────────────────────────────────────────────────

/**
 * 获取过滤后的技能列表
 * @returns {Array} 过滤后的技能数组
 */
function getFilteredSkills() {
  const { skills, searchKeyword } = getState();
  const keyword = searchKeyword.trim().toLowerCase();

  if (!keyword) return skills;

  return skills.filter(s => {
    const targets = [
      s.name.toLowerCase(),
      s.description.toLowerCase(),
      (s.tags || []).join(',').toLowerCase(),
    ];
    return targets.some(t => t.includes(keyword));
  });
}

// ── Render Functions ─────────────────────────────────────────────────────

/**
 * 渲染技能列表
 */
export function renderSkillList() {
  const skills = getFilteredSkills();
  const { selectedIds } = getState();

  if (!el.skillList) return;

  el.skillList.innerHTML = '';

  // 显示/隐藏空状态
  if (el.emptyState) {
    el.emptyState.style.display = skills.length ? 'none' : 'block';
  }

  // 更新全选复选框状态
  if (el.selectAllCheckbox) {
    el.selectAllCheckbox.checked = skills.length > 0 && skills.every(s => selectedIds.has(s.id));
  }

  if (!skills.length) return;

  // 创建文档片段
  const frag = document.createDocumentFragment();

  skills.forEach(skill => {
    const sourceType = (skill.source_file || '').trim() ? 'uploaded' : 'builtin';
    const sourceText = sourceType === 'uploaded' ? '来源：上传' : '来源：内置';
    const isActive = isSkillEffective(skill);

    const item = document.createElement('article');
    item.className = `skill-item ${isActive ? '' : 'inactive'}`.trim();

    item.innerHTML = `
      <input type="checkbox" class="skill-checkbox checkbox" data-id="${skill.id}" ${selectedIds.has(skill.id) ? 'checked' : ''}>
      <div class="skill-content">
        <div class="skill-name">${escapeHtml(skill.name)}</div>
        <div class="skill-description">${escapeHtml(skill.description)}</div>
        <div class="skill-tags">
          <span class="chip ${sourceType === 'builtin' ? '' : 'chip-success'}">${sourceText}</span>
          ${(skill.tags || []).map(t => `<span class="chip">#${escapeHtml(t)}</span>`).join('')}
        </div>
      </div>
      <div class="skill-actions">
        <button class="btn btn-danger btn-sm delete-btn" data-id="${skill.id}" type="button">删除</button>
      </div>
    `;

    frag.appendChild(item);
  });

  el.skillList.appendChild(frag);
}

// ── Event Handlers ───────────────────────────────────────────────────────

/**
 * 处理搜索输入
 */
function handleSearchInput(e) {
  setState({ searchKeyword: e.target.value || '' });
  renderSkillList();
}

/**
 * 处理复选框变化
 */
function handleCheckboxChange(e) {
  const target = e.target;
  if (!target.classList.contains('skill-checkbox')) return;

  const id = target.dataset.id;
  if (!id) return;

  const { selectedIds } = getState();
  const newSelectedIds = new Set(selectedIds);

  if (target.checked) {
    newSelectedIds.add(id);
  } else {
    newSelectedIds.delete(id);
  }

  setState({ selectedIds: newSelectedIds });

  // 更新全选复选框状态
  const allIds = getFilteredSkills().map(s => s.id);
  if (el.selectAllCheckbox) {
    el.selectAllCheckbox.checked = allIds.length > 0 && allIds.every(n => newSelectedIds.has(n));
  }
}

/**
 * 处理全选复选框变化
 */
function handleSelectAllChange(e) {
  const checked = e.target.checked;
  const { selectedIds } = getState();
  const newSelectedIds = new Set(selectedIds);

  getFilteredSkills().forEach(s => {
    if (checked) {
      newSelectedIds.add(s.id);
    } else {
      newSelectedIds.delete(s.id);
    }
  });

  setState({ selectedIds: newSelectedIds });
  renderSkillList();
}

/**
 * 处理删除按钮点击
 */
async function handleDeleteClick(e) {
  const target = e.target;
  if (!target.classList.contains('delete-btn')) return;

  const id = target.dataset.id;
  if (!id) return;

  const { skills } = getState();
  const cur = skills.find(s => s.id === id);
  const sf = (cur?.source_file || '').trim();

  const confirmMessage = sf
    ? '该技能来自上传文件，删除后会同步删除同一文件导入的全部技能，确认继续吗？'
    : '确认删除该技能吗？';

  if (!window.confirm(confirmMessage)) return;

  try {
    await deleteSkillApi(id);
    const { selectedIds } = getState();
    const newSelectedIds = new Set(selectedIds);
    newSelectedIds.delete(id);
    setState({ selectedIds: newSelectedIds });

    // 重新获取技能列表
    const result = await fetchSkillsApi();
    setState({ skills: result.items || [] });

    showToast('技能已删除', 'success');
  } catch (err) {
    showToast(err.message || '删除失败', 'error');
  }
}

/**
 * 处理批量删除按钮点击
 */
async function handleBatchDeleteClick() {
  const { selectedIds } = getState();

  if (!selectedIds.size) {
    showToast('请先选中要删除的技能。', 'warning');
    return;
  }

  if (!window.confirm(`确认删除已选中的 ${selectedIds.size} 项技能吗？`)) return;

  try {
    await batchDeleteSkillsApi(Array.from(selectedIds));
    setState({ selectedIds: new Set() });

    if (el.selectAllCheckbox) {
      el.selectAllCheckbox.checked = false;
    }

    // 重新获取技能列表
    const result = await fetchSkillsApi();
    setState({ skills: result.items || [] });

    showToast('批量删除完成', 'success');
  } catch (err) {
    showToast(err.message || '批量删除失败', 'error');
  }
}

// ── Initialize ───────────────────────────────────────────────────────────

/**
 * 初始化技能列表组件
 */
export function initSkillList() {
  cacheDom();

  // 搜索输入
  if (el.searchInput) {
    el.searchInput.addEventListener('input', handleSearchInput);
  }

  // 技能列表点击事件委托
  if (el.skillList) {
    el.skillList.addEventListener('click', handleDeleteClick);
    el.skillList.addEventListener('change', handleCheckboxChange);
  }

  // 全选复选框
  if (el.selectAllCheckbox) {
    el.selectAllCheckbox.addEventListener('change', handleSelectAllChange);
  }

  // 批量删除按钮
  if (el.batchDeleteBtn) {
    el.batchDeleteBtn.addEventListener('click', handleBatchDeleteClick);
  }

  // 订阅状态变化
  subscribe('skills', () => {
    renderSkillList();
  });
}

export default {
  initSkillList,
  renderSkillList,
};