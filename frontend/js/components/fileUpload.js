/* ═══════════════════════════════════════════════════════════════════════
   File Upload Component - Drag & Drop Upload
   ═══════════════════════════════════════════════════════════════════════ */

import { getState, setState } from '../state.js';
import { uploadSkillsApi } from '../api.js';
import { showToast } from './toast.js';

// ── DOM References ───────────────────────────────────────────────────────
let el = {};

function cacheDom() {
  el = {
    dropZone: document.getElementById('dropZone'),
    fileInput: document.getElementById('fileInput'),
    selectFileBtn: document.getElementById('selectFileBtn'),
    importBtn: document.getElementById('importBtn'),
    uploadHint: document.getElementById('uploadHint'),
  };
}

// ── File Handling ────────────────────────────────────────────────────────

/**
 * 处理文件上传
 * @param {File} file - 文件对象
 */
async function handleFile(file) {
  if (!file) return;

  // 验证文件类型
  if (!/\.md$/i.test(file.name)) {
    showToast('仅支持上传 .md 文件。', 'error');
    return;
  }

  try {
    showToast('正在上传...', 'info', 0);

    const result = await uploadSkillsApi(file);
    setState({ skills: result.items || [] });

    showToast(`导入成功：${result.imported_count || 0} 条技能`, 'success');
  } catch (error) {
    showToast(error.message || '上传失败', 'error');
  }
}

// ── Event Handlers ───────────────────────────────────────────────────────

/**
 * 处理文件选择
 */
function handleFileSelect(e) {
  const file = e.target.files?.[0];
  if (file) {
    handleFile(file);
    e.target.value = ''; // 重置input
  }
}

/**
 * 处理拖拽进入
 */
function handleDragEnter(e) {
  e.preventDefault();
  if (el.dropZone) {
    el.dropZone.classList.add('drag-over');
  }
}

/**
 * 处理拖拽经过
 */
function handleDragOver(e) {
  e.preventDefault();
}

/**
 * 处理拖拽离开
 */
function handleDragLeave(e) {
  e.preventDefault();
  if (el.dropZone) {
    el.dropZone.classList.remove('drag-over');
  }
}

/**
 * 处理文件拖放
 */
function handleDrop(e) {
  e.preventDefault();
  if (el.dropZone) {
    el.dropZone.classList.remove('drag-over');
  }

  const file = e.dataTransfer?.files?.[0];
  if (file) {
    handleFile(file);
  }
}

/**
 * 处理键盘事件
 */
function handleKeyDown(e) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    if (el.fileInput) {
      el.fileInput.click();
    }
  }
}

// ── Initialize ───────────────────────────────────────────────────────────

/**
 * 初始化文件上传组件
 */
export function initFileUpload() {
  cacheDom();

  // 选择文件按钮
  if (el.selectFileBtn) {
    el.selectFileBtn.addEventListener('click', () => {
      if (el.fileInput) el.fileInput.click();
    });
  }

  // 导入按钮
  if (el.importBtn) {
    el.importBtn.addEventListener('click', () => {
      if (el.fileInput) el.fileInput.click();
    });
  }

  // 文件选择事件
  if (el.fileInput) {
    el.fileInput.addEventListener('change', handleFileSelect);
  }

  // 拖拽事件
  if (el.dropZone) {
    el.dropZone.addEventListener('dragenter', handleDragEnter);
    el.dropZone.addEventListener('dragover', handleDragOver);
    el.dropZone.addEventListener('dragleave', handleDragLeave);
    el.dropZone.addEventListener('drop', handleDrop);
    el.dropZone.addEventListener('click', () => {
      if (el.fileInput) el.fileInput.click();
    });
    el.dropZone.addEventListener('keydown', handleKeyDown);
  }

  // 更新提示信息
  if (el.uploadHint) {
    const { username } = getState();
    el.uploadHint.textContent = username
      ? `当前用户：${username}（支持 Markdown 文件上传）`
      : '支持 Markdown 文件上传，上传后会按技能名更新并参与路由。';
  }
}

export default {
  initFileUpload,
};