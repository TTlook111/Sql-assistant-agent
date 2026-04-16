"use strict";

const STORAGE_KEY = "skill_studio_data_v1";
const API_BASE = "/api";
const USER_ID_KEY = "skill_studio_user_id";

function resolveUserId() {
  const fromQuery = new URLSearchParams(window.location.search).get("user_id");
  const raw = (fromQuery || localStorage.getItem(USER_ID_KEY) || "demo-user").trim();
  return raw.slice(0, 64) || "demo-user";
}

const state = {
  skills: [],
  selectedIds: new Set(),
  searchKeyword: "",
  chats: [],
  userId: resolveUserId(),
  chatThreadId: null
};

const el = {
  dropZone: document.getElementById("dropZone"),
  fileInput: document.getElementById("fileInput"),
  selectFileBtn: document.getElementById("selectFileBtn"),
  importBtn: document.getElementById("importBtn"),
  exportBtn: document.getElementById("exportBtn"),
  uploadHint: document.getElementById("uploadHint"),
  batchDeleteBtn: document.getElementById("batchDeleteBtn"),
  selectAllCheckbox: document.getElementById("selectAllCheckbox"),
  searchInput: document.getElementById("searchInput"),
  skillList: document.getElementById("skillList"),
  emptyState: document.getElementById("emptyState"),
  chatWindow: document.getElementById("chatWindow"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  toast: document.getElementById("toast"),
  userBadge: document.getElementById("userBadge"),
  modeBadge: document.getElementById("modeBadge"),
  countBadge: document.getElementById("countBadge"),
  chatModeTip: document.getElementById("chatModeTip")
};

function getStorageKey() {
  return `${STORAGE_KEY}:${state.userId}`;
}

function getHeaders() {
  return { "x-user-id": state.userId };
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...getHeaders()
    }
  });
  if (!response.ok) {
    let message = `请求失败: ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_err) {
      // ignore json parse error
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

async function fetchSkills() {
  const result = await apiRequest("/skills");
  state.skills = result.items || [];
  state.selectedIds = new Set();
}

function saveState() {
  const data = {
    chats: state.chats,
    chatThreadId: state.chatThreadId
  };
  localStorage.setItem(getStorageKey(), JSON.stringify(data));
  localStorage.setItem(USER_ID_KEY, state.userId);
}

function loadState() {
  try {
    const raw = localStorage.getItem(getStorageKey());
    if (!raw) {
      return;
    }
    const data = JSON.parse(raw);
    state.chats = Array.isArray(data.chats) ? data.chats : [];
    state.chatThreadId = data.chatThreadId || null;
  } catch (error) {
    console.error(error);
    showToast("读取本地数据失败，已使用空数据初始化。", true);
  }
}

function hasUploadedSkills() {
  return state.skills.some((skill) => Boolean((skill.source_file || "").trim()));
}

function getEffectiveMode() {
  return hasUploadedSkills() ? "uploaded" : "builtin_fallback";
}

function getModeLabel() {
  return getEffectiveMode() === "uploaded" ? "上传优先生效" : "内置回退";
}

function isSkillEffective(skill) {
  const uploaded = Boolean((skill.source_file || "").trim());
  return getEffectiveMode() === "uploaded" ? uploaded : true;
}

function renderStatusStrip() {
  const uploadedCount = state.skills.filter((item) => Boolean((item.source_file || "").trim())).length;
  const modeText = getModeLabel();
  if (el.userBadge) {
    el.userBadge.textContent = `用户：${state.userId}`;
  }
  if (el.modeBadge) {
    el.modeBadge.textContent = `生效模式：${modeText}`;
  }
  if (el.countBadge) {
    el.countBadge.textContent = `技能数：${state.skills.length}（上传 ${uploadedCount}）`;
  }
  if (el.chatModeTip) {
    el.chatModeTip.textContent = `路由模式：${modeText}`;
  }
}

function showToast(text, isError = false) {
  el.toast.textContent = text;
  el.toast.style.borderColor = isError ? "rgba(255, 107, 157, 0.7)" : "rgba(168, 181, 255, 0.3)";
  el.toast.classList.add("show");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => {
    el.toast.classList.remove("show");
  }, 2200);
}

function getFilteredSkills() {
  const keyword = state.searchKeyword.trim().toLowerCase();
  if (!keyword) {
    return state.skills;
  }
  return state.skills.filter((skill) => {
    const targets = [
      skill.name.toLowerCase(),
      skill.description.toLowerCase(),
      (skill.tags || []).join(",").toLowerCase()
    ];
    return targets.some((item) => item.includes(keyword));
  });
}

function renderSkillList() {
  const skills = getFilteredSkills();
  el.skillList.innerHTML = "";
  el.emptyState.style.display = skills.length ? "none" : "block";
  el.selectAllCheckbox.checked = skills.length > 0 && skills.every((skill) => state.selectedIds.has(skill.id));
  if (!skills.length) {
    return;
  }

  const frag = document.createDocumentFragment();
  skills.forEach((skill) => {
    const sourceType = (skill.source_file || "").trim() ? "uploaded" : "builtin";
    const sourceText = sourceType === "uploaded" ? "来源：上传" : "来源：内置";
    const item = document.createElement("article");
    item.className = `skill-item ${isSkillEffective(skill) ? "" : "inactive"}`.trim();
    item.innerHTML = `
      <div class="skill-main">
        <label class="check-wrap">
          <input type="checkbox" data-id="${skill.id}" class="skill-checkbox" ${state.selectedIds.has(skill.id) ? "checked" : ""}>
          <strong class="skill-title">${escapeHtml(skill.name)}</strong>
        </label>
        <div class="skill-actions">
          <button class="btn danger delete-btn" data-id="${skill.id}" type="button">删除</button>
        </div>
      </div>
      <p>${escapeHtml(skill.description)}</p>
      <div class="skill-meta">
        <span class="source-chip ${sourceType === "builtin" ? "builtin" : ""}">${sourceText}</span>
        ${(skill.tags || []).map((tag) => `<span class="chip">#${escapeHtml(tag)}</span>`).join("")}
      </div>
    `;
    frag.appendChild(item);
  });
  el.skillList.appendChild(frag);
}

function renderChatWindow() {
  el.chatWindow.innerHTML = "";
  if (!state.skills.length) {
    el.chatWindow.innerHTML = '<p class="chat-msg bot">当前无技能可用，请先上传 skills.md。</p>';
    return;
  }

  if (!state.chats.length) {
    const initialText =
      getEffectiveMode() === "uploaded"
        ? "你可以直接提问，Agent 将在“上传技能”范围内自动路由并作答。"
        : "你可以直接提问，当前使用“内置技能回退”模式自动路由并作答。";
    el.chatWindow.innerHTML = `<p class="chat-msg bot">${initialText}</p>`;
    return;
  }

  const frag = document.createDocumentFragment();
  state.chats.forEach((msg) => {
    const p = document.createElement("p");
    p.className = `chat-msg ${msg.role}`;
    p.textContent = msg.content;
    frag.appendChild(p);
  });
  el.chatWindow.appendChild(frag);
  el.chatWindow.scrollTop = el.chatWindow.scrollHeight;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function addChatMessage(role, content) {
  state.chats.push({
    role,
    content,
    time: Date.now()
  });
}

async function handleFile(file) {
  if (!file) {
    return;
  }
  if (!/\.md$/i.test(file.name)) {
    showToast("仅支持上传 .md 文件。", true);
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  try {
    const result = await apiRequest("/skills/upload", {
      method: "POST",
      body: formData
    });
    state.skills = result.items || [];
    renderAll();
    showToast(`导入成功：${result.imported_count || 0} 条技能`);
  } catch (error) {
    showToast(error.message || "上传失败", true);
  }
}

function renderAll() {
  renderStatusStrip();
  renderSkillList();
  renderChatWindow();
  saveState();
}

function initEvents() {
  el.selectFileBtn.addEventListener("click", () => el.fileInput.click());
  el.importBtn.addEventListener("click", () => el.fileInput.click());
  el.fileInput.addEventListener("change", async (event) => {
    await handleFile(event.target.files?.[0]);
    event.target.value = "";
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    el.dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      el.dropZone.classList.add("drag-over");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    el.dropZone.addEventListener(eventName, () => {
      el.dropZone.classList.remove("drag-over");
    });
  });
  el.dropZone.addEventListener("drop", async (event) => {
    event.preventDefault();
    await handleFile(event.dataTransfer?.files?.[0]);
  });
  el.dropZone.addEventListener("click", () => el.fileInput.click());
  el.dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      el.fileInput.click();
    }
  });

  el.searchInput.addEventListener("input", (event) => {
    state.searchKeyword = event.target.value || "";
    renderSkillList();
  });

  el.skillList.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const id = target.dataset.id;
    if (!id) {
      return;
    }
    if (target.classList.contains("delete-btn")) {
      if (!window.confirm("确认删除该技能吗？")) {
        return;
      }
      try {
        await apiRequest(`/skills/${id}`, { method: "DELETE" });
        state.selectedIds.delete(id);
        await fetchSkills();
        showToast("技能已删除");
        renderAll();
      } catch (error) {
        showToast(error.message || "删除失败", true);
      }
    }
  });

  el.skillList.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || !target.classList.contains("skill-checkbox")) {
      return;
    }
    const id = target.dataset.id;
    if (!id) {
      return;
    }
    if (target.checked) {
      state.selectedIds.add(id);
    } else {
      state.selectedIds.delete(id);
    }
    const allIds = getFilteredSkills().map((s) => s.id);
    el.selectAllCheckbox.checked = allIds.length > 0 && allIds.every((nextId) => state.selectedIds.has(nextId));
  });

  el.selectAllCheckbox.addEventListener("change", (event) => {
    const checked = event.target.checked;
    const filtered = getFilteredSkills();
    filtered.forEach((item) => {
      if (checked) {
        state.selectedIds.add(item.id);
      } else {
        state.selectedIds.delete(item.id);
      }
    });
    renderSkillList();
  });

  el.batchDeleteBtn.addEventListener("click", async () => {
    if (!state.selectedIds.size) {
      showToast("请先选中要删除的技能。", true);
      return;
    }
    if (!window.confirm(`确认删除已选中的 ${state.selectedIds.size} 项技能吗？`)) {
      return;
    }
    const selected = Array.from(state.selectedIds);
    try {
      await apiRequest("/skills/batch-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: selected })
      });
      state.selectedIds = new Set();
      el.selectAllCheckbox.checked = false;
      await fetchSkills();
      showToast("批量删除完成");
      renderAll();
    } catch (error) {
      showToast(error.message || "批量删除失败", true);
    }
  });

  el.exportBtn.addEventListener("click", async () => {
    if (!state.skills.length) {
      showToast("没有可导出的技能数据。", true);
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/skills/export.md`, { headers: getHeaders() });
      if (!response.ok) {
        throw new Error("导出失败");
      }
      const content = await response.text();
      const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "skills.md";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToast("skills.md 已导出");
    } catch (error) {
      showToast(error.message || "导出失败", true);
    }
  });

  el.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = el.chatInput.value.trim();
    if (!text) {
      return;
    }
    if (!state.skills.length) {
      showToast("请先上传 skills.md。", true);
      return;
    }
    addChatMessage("user", text);
    renderChatWindow();
    el.chatInput.value = "";
    try {
      const result = await apiRequest("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          thread_id: state.chatThreadId
        })
      });
      state.chatThreadId = result.thread_id || state.chatThreadId;
      addChatMessage("bot", result.answer || "助手未返回内容。");
      renderChatWindow();
      saveState();
    } catch (error) {
      addChatMessage("bot", `请求失败：${error.message || "未知错误"}`);
      renderChatWindow();
      saveState();
    }
  });
}

async function bootstrap() {
  loadState();
  if (el.uploadHint) {
    el.uploadHint.textContent = `当前用户：${state.userId}（可通过 ?user_id=xxx 切换隔离空间）`;
  }
  initEvents();
  try {
    await fetchSkills();
  } catch (error) {
    showToast(`加载技能失败：${error.message || "未知错误"}`, true);
  }
  renderAll();
}

void bootstrap();
