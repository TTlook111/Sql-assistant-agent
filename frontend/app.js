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
  editingSkillId: null,
  selectedIds: new Set(),
  searchKeyword: "",
  activeChatSkillId: "",
  chats: {},
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
  skillForm: document.getElementById("skillForm"),
  formTitle: document.getElementById("formTitle"),
  nameInput: document.getElementById("nameInput"),
  descInput: document.getElementById("descInput"),
  levelInput: document.getElementById("levelInput"),
  tagsInput: document.getElementById("tagsInput"),
  cancelEditBtn: document.getElementById("cancelEditBtn"),
  formError: document.getElementById("formError"),
  addSkillBtn: document.getElementById("addSkillBtn"),
  batchDeleteBtn: document.getElementById("batchDeleteBtn"),
  selectAllCheckbox: document.getElementById("selectAllCheckbox"),
  searchInput: document.getElementById("searchInput"),
  skillList: document.getElementById("skillList"),
  emptyState: document.getElementById("emptyState"),
  chatSkillSelect: document.getElementById("chatSkillSelect"),
  chatWindow: document.getElementById("chatWindow"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  toast: document.getElementById("toast")
};

function normalizeTags(value) {
  return value
    .split(/[,\uff0c]/)
    .map((s) => s.trim())
    .filter(Boolean);
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
    activeChatSkillId: state.activeChatSkillId,
    chatThreadId: state.chatThreadId
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  localStorage.setItem(USER_ID_KEY, state.userId);
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return;
    }
    const data = JSON.parse(raw);
    state.chats = data.chats && typeof data.chats === "object" ? data.chats : {};
    state.activeChatSkillId = data.activeChatSkillId || "";
    state.chatThreadId = data.chatThreadId || null;
  } catch (error) {
    console.error(error);
    showToast("读取本地数据失败，已使用空数据初始化。", true);
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

function validateSkillForm(payload) {
  if (!payload.name.trim()) {
    return "技能名称不能为空。";
  }
  if (!payload.description.trim()) {
    return "技能描述不能为空。";
  }
  if (!payload.level.trim()) {
    return "请选择熟练度等级。";
  }
  return "";
}

function setForm(skill = null) {
  if (skill) {
    state.editingSkillId = skill.id;
    el.formTitle.textContent = "编辑技能";
    el.nameInput.value = skill.name;
    el.descInput.value = skill.description;
    el.levelInput.value = skill.level;
    el.tagsInput.value = (skill.tags || []).join(", ");
  } else {
    state.editingSkillId = null;
    el.formTitle.textContent = "新增技能";
    el.skillForm.reset();
  }
  el.formError.textContent = "";
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
    const item = document.createElement("article");
    item.className = "skill-item";
    item.innerHTML = `
      <div class="skill-main">
        <label class="check-wrap">
          <input type="checkbox" data-id="${skill.id}" class="skill-checkbox" ${state.selectedIds.has(skill.id) ? "checked" : ""}>
          <strong class="skill-title">${escapeHtml(skill.name)}</strong>
        </label>
        <div class="skill-actions">
          <button class="btn ghost edit-btn" data-id="${skill.id}" type="button">编辑</button>
          <button class="btn danger delete-btn" data-id="${skill.id}" type="button">删除</button>
        </div>
      </div>
      <p>${escapeHtml(skill.description)}</p>
      <div class="skill-meta">
        <span class="chip">熟练度: ${escapeHtml(skill.level)}</span>
        ${(skill.tags || []).map((tag) => `<span class="chip">#${escapeHtml(tag)}</span>`).join("")}
      </div>
    `;
    frag.appendChild(item);
  });
  el.skillList.appendChild(frag);
}

function renderChatSkillSelect() {
  const current = state.activeChatSkillId;
  el.chatSkillSelect.innerHTML = "";

  if (!state.skills.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无技能可选";
    el.chatSkillSelect.appendChild(option);
    state.activeChatSkillId = "";
    renderChatWindow();
    return;
  }

  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = "请选择技能";
  el.chatSkillSelect.appendChild(defaultOption);

  state.skills.forEach((skill) => {
    const option = document.createElement("option");
    option.value = skill.id;
    option.textContent = skill.name;
    el.chatSkillSelect.appendChild(option);
  });

  const target = state.skills.some((s) => s.id === current) ? current : state.skills[0].id;
  state.activeChatSkillId = target;
  el.chatSkillSelect.value = target;
  renderChatWindow();
}

function renderChatWindow() {
  const skillId = state.activeChatSkillId;
  el.chatWindow.innerHTML = "";
  if (!skillId) {
    el.chatWindow.innerHTML = '<p class="chat-msg bot">请先新增或导入技能数据，再开始对话。</p>';
    return;
  }

  const messages = state.chats[skillId] || [];
  if (!messages.length) {
    const skill = state.skills.find((item) => item.id === skillId);
    el.chatWindow.innerHTML = `<p class="chat-msg bot">你当前选择的是「${escapeHtml(
      skill?.name || ""
    )}」。可以直接问我：学习路径、实战建议、常见误区或项目方案。</p>`;
    return;
  }

  const frag = document.createDocumentFragment();
  messages.forEach((msg) => {
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

function addChatMessage(skillId, role, content) {
  if (!state.chats[skillId]) {
    state.chats[skillId] = [];
  }
  state.chats[skillId].push({
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
  renderSkillList();
  renderChatSkillSelect();
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

  el.skillForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      name: el.nameInput.value.trim(),
      description: el.descInput.value.trim(),
      level: el.levelInput.value.trim(),
      tags: normalizeTags(el.tagsInput.value || ""),
      content: el.descInput.value.trim()
    };
    const error = validateSkillForm(payload);
    if (error) {
      el.formError.textContent = error;
      return;
    }

    try {
      if (state.editingSkillId) {
        await apiRequest(`/skills/${state.editingSkillId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        showToast("技能已更新");
      } else {
        await apiRequest("/skills", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        showToast("技能已新增");
      }
      await fetchSkills();
      setForm(null);
      renderAll();
    } catch (error) {
      showToast(error.message || "保存失败", true);
    }
  });

  el.cancelEditBtn.addEventListener("click", () => setForm(null));
  el.addSkillBtn.addEventListener("click", () => {
    setForm(null);
    el.nameInput.focus();
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
    if (target.classList.contains("edit-btn")) {
      const skill = state.skills.find((item) => item.id === id);
      if (skill) {
        setForm(skill);
      }
      return;
    }
    if (target.classList.contains("delete-btn")) {
      if (!window.confirm("确认删除该技能吗？")) {
        return;
      }
      try {
        await apiRequest(`/skills/${id}`, { method: "DELETE" });
        state.selectedIds.delete(id);
        delete state.chats[id];
        if (state.activeChatSkillId === id) {
          state.activeChatSkillId = "";
        }
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
      const selectedSet = new Set(selected);
      Object.keys(state.chats).forEach((chatId) => {
        if (selectedSet.has(chatId)) {
          delete state.chats[chatId];
        }
      });
      if (selectedSet.has(state.activeChatSkillId)) {
        state.activeChatSkillId = "";
      }
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

  el.chatSkillSelect.addEventListener("change", (event) => {
    state.activeChatSkillId = event.target.value || "";
    renderChatWindow();
    saveState();
  });

  el.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = el.chatInput.value.trim();
    if (!text) {
      return;
    }
    if (!state.activeChatSkillId) {
      showToast("请先选择一个技能。", true);
      return;
    }
    const skill = state.skills.find((item) => item.id === state.activeChatSkillId);
    if (!skill) {
      showToast("选中技能不存在。", true);
      return;
    }
    addChatMessage(skill.id, "user", text);
    renderChatWindow();
    el.chatInput.value = "";
    try {
      const result = await apiRequest("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: `当前技能：${skill.name}\n技能描述：${skill.description}\n熟练度：${skill.level}\n标签：${(skill.tags || []).join(", ")}\n\n用户问题：${text}`,
          thread_id: state.chatThreadId
        })
      });
      state.chatThreadId = result.thread_id || state.chatThreadId;
      addChatMessage(skill.id, "bot", result.answer || "助手未返回内容。");
      renderChatWindow();
      saveState();
    } catch (error) {
      addChatMessage(skill.id, "bot", `请求失败：${error.message || "未知错误"}`);
      renderChatWindow();
      saveState();
    }
  });
}

async function bootstrap() {
  loadState();
  if (el.uploadHint) {
    el.uploadHint.textContent = `当前用户：${state.userId}（可通过 ?user_id=xxx 切换）`;
  }
  setForm(null);
  initEvents();
  try {
    await fetchSkills();
  } catch (error) {
    showToast(`加载技能失败：${error.message || "未知错误"}`, true);
  }
  renderAll();
}

void bootstrap();
