/* ═══════════════════════════════════════════════════════════════════════
   Toast Component - Notification Messages
   ═══════════════════════════════════════════════════════════════════════ */

// ── Toast Container ──────────────────────────────────────────────────────
let container = null;
let toastTimeout = null;

/**
 * 初始化Toast容器
 */
function ensureContainer() {
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    container.id = 'toastContainer';
    document.body.appendChild(container);
  }
  return container;
}

/**
 * 创建Toast元素
 * @param {string} message - 消息内容
 * @param {string} type - 类型：success | error | warning | info
 * @returns {HTMLElement} Toast元素
 */
function createToastElement(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  // 图标
  const icons = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ',
  };

  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || icons.info}</span>
    <span class="toast-message">${escapeHtml(message)}</span>
    <span class="toast-close" role="button" aria-label="关闭">✕</span>
  `;

  // 关闭按钮事件
  const closeBtn = toast.querySelector('.toast-close');
  closeBtn.addEventListener('click', () => removeToast(toast));

  return toast;
}

/**
 * HTML转义（简化版，避免循环依赖）
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text ?? '';
  return div.innerHTML;
}

/**
 * 移除Toast
 * @param {HTMLElement} toast - Toast元素
 */
function removeToast(toast) {
  if (!toast) return;

  toast.style.animation = 'toast-out 0.2s ease-in forwards';
  setTimeout(() => {
    toast.remove();
    // 如果容器为空，移除容器
    if (container && container.children.length === 0) {
      container.remove();
      container = null;
    }
  }, 200);
}

/**
 * 显示Toast消息
 * @param {string} message - 消息内容
 * @param {string} type - 类型：success | error | warning | info
 * @param {number} duration - 显示时长（毫秒），默认3000
 */
export function showToast(message, type = 'info', duration = 3000) {
  const toastContainer = ensureContainer();
  const toast = createToastElement(message, type);

  // 添加到容器
  toastContainer.appendChild(toast);

  // 自动移除
  if (duration > 0) {
    const timeout = setTimeout(() => removeToast(toast), duration);
    // 存储timeout以便清理
    toast._timeout = timeout;
  }
}

/**
 * 清除所有Toast
 */
export function clearToasts() {
  if (container) {
    container.innerHTML = '';
    container.remove();
    container = null;
  }
}

// ── Toast Out Animation ──────────────────────────────────────────────────
const style = document.createElement('style');
style.textContent = `
  @keyframes toast-out {
    from {
      opacity: 1;
      transform: translateX(0);
    }
    to {
      opacity: 0;
      transform: translateX(100%);
    }
  }
`;
document.head.appendChild(style);

export default {
  showToast,
  clearToasts,
};