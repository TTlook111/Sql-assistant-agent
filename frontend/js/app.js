/* ═══════════════════════════════════════════════════════════════════════
   App Entry Point - Bootstrap & Initialize
   ═══════════════════════════════════════════════════════════════════════ */

import { initAuth, checkAuth } from './auth.js';
import { initStatusStrip } from './components/statusStrip.js';
import { initSkillList } from './components/skillList.js';
import { initFileUpload } from './components/fileUpload.js';
import { initDbPanel } from './components/dbPanel.js';
import { initChatPanel } from './components/chatPanel.js';
import { showToast } from './components/toast.js';

// ── Sidebar Toggle ───────────────────────────────────────────────────────

function initSidebar() {
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarOverlay = document.getElementById('sidebarOverlay');

  if (!sidebar || !sidebarToggle) return;

  // 切换侧边栏
  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    sidebar.classList.toggle('mobile-open');
    if (sidebarOverlay) {
      sidebarOverlay.classList.toggle('visible');
    }
  });

  // 点击遮罩关闭侧边栏（移动端）
  if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', () => {
      sidebar.classList.remove('mobile-open');
      sidebarOverlay.classList.remove('visible');
    });
  }

  // 面板折叠/展开
  const panelHeaders = document.querySelectorAll('[data-toggle]');
  panelHeaders.forEach(header => {
    header.addEventListener('click', () => {
      const panelId = header.dataset.toggle;
      const panel = document.getElementById(panelId);
      if (panel) {
        panel.classList.toggle('collapsed');
      }
    });
  });
}

// ── User Menu ────────────────────────────────────────────────────────────

function initUserMenu() {
  const userMenu = document.getElementById('userMenu');
  const userMenuTrigger = document.getElementById('userMenuTrigger');

  if (!userMenu || !userMenuTrigger) return;

  userMenuTrigger.addEventListener('click', (e) => {
    e.stopPropagation();
    userMenu.classList.toggle('open');
  });

  // 点击其他地方关闭菜单
  document.addEventListener('click', () => {
    userMenu.classList.remove('open');
  });
}

// ── Keyboard Shortcuts ───────────────────────────────────────────────────

function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K: 聚焦搜索框
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      const searchInput = document.getElementById('searchInput');
      if (searchInput) {
        searchInput.focus();
      }
    }

    // Escape: 关闭侧边栏（移动端）
    if (e.key === 'Escape') {
      const sidebar = document.getElementById('sidebar');
      const sidebarOverlay = document.getElementById('sidebarOverlay');
      if (sidebar && sidebar.classList.contains('mobile-open')) {
        sidebar.classList.remove('mobile-open');
        if (sidebarOverlay) {
          sidebarOverlay.classList.remove('visible');
        }
      }
    }
  });
}

// ── Auto-resize Textarea ─────────────────────────────────────────────────

function initTextareaAutoResize() {
  const chatInput = document.getElementById('chatInput');
  if (!chatInput) return;

  chatInput.addEventListener('input', () => {
    // 重置高度
    chatInput.style.height = 'auto';
    // 设置新高度
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });
}

// ── Bootstrap ────────────────────────────────────────────────────────────

async function bootstrap() {
  console.log('🚀 SQL Assistant initializing...');

  try {
    // 初始化认证模块
    initAuth();

    // 初始化UI组件
    initSidebar();
    initUserMenu();
    initKeyboardShortcuts();
    initTextareaAutoResize();

    // 初始化功能模块
    initStatusStrip();
    initSkillList();
    initFileUpload();
    initDbPanel();
    initChatPanel();

    // 检查认证状态
    const isAuthenticated = await checkAuth();

    if (isAuthenticated) {
      console.log('✅ User authenticated');
    } else {
      console.log('ℹ️ User not authenticated, showing login');
    }

    console.log('✅ SQL Assistant initialized');
  } catch (error) {
    console.error('❌ Initialization failed:', error);
    showToast('应用初始化失败，请刷新页面重试', 'error');
  }
}

// ── Start ────────────────────────────────────────────────────────────────

// Module scripts are deferred, so DOM is ready
// But we wait for DOMContentLoaded for safety
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}