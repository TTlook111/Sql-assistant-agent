"use strict";

const STORAGE_KEY = "skill_studio_data_v1";
const API_BASE = "/api";
const TOKEN_KEY = "skill_studio_token";
const USERNAME_KEY = "skill_studio_username";

const state = {
  skills: [],
  selectedIds: new Set(),
  searchKeyword: "",
  chats: [],
  chatThreadId: null,
  dbConnected: false,
  token: localStorage.getItem(TOKEN_KEY) || "",
  username: localStorage.getItem(USERNAME_KEY) || "",
  threads: [],
  historyVisible: false
};

const el = {
  authOverlay: document.getElementById("authOverlay"),
  appShell: document.getElementById("appShell"),
  authForm: document.getElementById("authForm"),
  authUsername: document.getElementById("authUsername"),
  authPassword: document.getElementById("authPassword"),
  loginBtn: document.getElementById("loginBtn"),
  registerBtn: document.getElementById("registerBtn"),
  authError: document.getElementById("authError"),
  currentUser: document.getElementById("currentUser"),
  logoutBtn: document.getElementById("logoutBtn"),
  dropZone: document.getElementById("dropZone"),
  fileInput: document.getElementById("fileInput"),
  selectFileBtn: document.getElementById("selectFileBtn"),
  importBtn: document.getElementById("importBtn"),
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
  chatModeTip: document.getElementById("chatModeTip"),
  dbForm: document.getElementById("dbForm"),
  dbHost: document.getElementById("dbHost"),
  dbPort: document.getElementById("dbPort"),
  dbUser: document.getElementById("dbUser"),
  dbPassword: document.getElementById("dbPassword"),
  dbDatabase: document.getElementById("dbDatabase"),
  dbConnectBtn: document.getElementById("dbConnectBtn"),
  dbDisconnectBtn: document.getElementById("dbDisconnectBtn"),
  dbStatusBadge: document.getElementById("dbStatusBadge"),
  dbTablesPreview: document.getElementById("dbTablesPreview"),
  dbTablesList: document.getElementById("dbTablesList"),
  newChatBtn: document.getElementById("newChatBtn"),
  toggleHistoryBtn: document.getElementById("toggleHistoryBtn"),
  threadHistory: document.getElementById("threadHistory"),
  threadList: document.getElementById("threadList")
};

function getStorageKey() {
  return `${STORAGE_KEY}:${state.username || "guest"}`;
}

function getHeaders() {
  const h = {};
  if (state.token) {
    h["Authorization"] = `Bearer ${state.token}`;
  }
  return h;
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...getHeaders()
    }
  });
  if (response.status === 401) {
    handleLogout();
    throw new Error("登录已过期，请重新登录。");
  }
  if (!response.ok) {
    let message = `请求失败: ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_err) {
      // ignore
    }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  const ct = response.headers.get("content-type") || "";
  if (ct.includes("application/json")) return response.json();
  return response.text();
}

// ── Auth ────────────────────────────────────────────────────────────────

function showApp() {
  el.authOverlay.classList.add("hidden");
  el.appShell.style.display = "";
  if (el.currentUser) el.currentUser.textContent = state.username;
}

function showAuth() {
  el.authOverlay.classList.remove("hidden");
  el.appShell.style.display = "none";
}

async function handleLogin(username, password) {
  el.authError.textContent = "";
  try {
    const result = await apiRequest("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    state.token = result.token;
    state.username = result.username || username;
    localStorage.setItem(TOKEN_KEY, state.token);
    localStorage.setItem(USERNAME_KEY, state.username);
    await onLoginSuccess();
  } catch (error) {
    el.authError.textContent = error.message || "登录失败";
  }
}

async function handleRegister(username, password) {
  el.authError.textContent = "";
  try {
    const result = await apiRequest("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    state.token = result.token;
    state.username = result.username || username;
    localStorage.setItem(TOKEN_KEY, state.token);
    localStorage.setItem(USERNAME_KEY, state.username);
    await onLoginSuccess();
  } catch (error) {
    el.authError.textContent = error.message || "注册失败";
  }
}

function handleLogout() {
  state.token = "";
  state.username = "";
  state.skills = [];
  state.chats = [];
  state.chatThreadId = null;
  state.dbConnected = false;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
  showAuth();
}

async function onLoginSuccess() {
  showApp();
  loadState();
  if (el.uploadHint) {
    el.uploadHint.textContent = `当前用户：${state.username}（支持 Markdown 文件上传）`;
  }
  try {
    await fetchSkills();
  } catch (error) {
    showToast(`加载技能失败：${error.message || "未知错误"}`, true);
  }
  renderAll();
  fetchDbStatus();
}

// ── Skills / UI ─────────────────────────────────────────────────────────

async function fetchSkills() {
  const result = await apiRequest("/skills");
  state.skills = result.items || [];
  state.selectedIds = new Set();
}

function saveState() {
  const data = { chats: state.chats, chatThreadId: state.chatThreadId };
  localStorage.setItem(getStorageKey(), JSON.stringify(data));
}

function loadState() {
  try {
    const raw = localStorage.getItem(getStorageKey());
    if (!raw) return;
    const data = JSON.parse(raw);
    state.chats = Array.isArray(data.chats) ? data.chats : [];
    state.chatThreadId = data.chatThreadId || null;
  } catch (error) {
    console.error(error);
  }
}

function hasUploadedSkills() {
  return state.skills.some((s) => Boolean((s.source_file || "").trim()));
}

function getEffectiveMode() {
  if (!state.skills.length) return "none";
  return hasUploadedSkills() ? "uploaded" : "builtin_fallback";
}

function getModeLabel() {
  const mode = getEffectiveMode();
  if (mode === "uploaded") return "上传优先生效";
  if (mode === "builtin_fallback") return "内置回退";
  return "无技能上下文";
}

function isSkillEffective(skill) {
  const uploaded = Boolean((skill.source_file || "").trim());
  return getEffectiveMode() !== "uploaded" || uploaded;
}

function renderStatusStrip() {
  const uploadedCount = state.skills.filter((s) => Boolean((s.source_file || "").trim())).length;
  const modeText = getModeLabel();
  if (el.userBadge) el.userBadge.textContent = `用户：${state.username}`;
  if (el.modeBadge) el.modeBadge.textContent = `生效模式：${modeText}`;
  if (el.countBadge) el.countBadge.textContent = `技能数：${state.skills.length}（上传 ${uploadedCount}）`;
  if (el.chatModeTip) el.chatModeTip.textContent = `路由模式：${modeText}`;
}

function showToast(text, isError = false) {
  el.toast.textContent = text;
  el.toast.style.borderColor = isError ? "rgba(255, 107, 157, 0.7)" : "rgba(168, 181, 255, 0.3)";
  el.toast.classList.add("show");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => el.toast.classList.remove("show"), 2200);
}

function getFilteredSkills() {
  const keyword = state.searchKeyword.trim().toLowerCase();
  if (!keyword) return state.skills;
  return state.skills.filter((s) => {
    const targets = [s.name.toLowerCase(), s.description.toLowerCase(), (s.tags || []).join(",").toLowerCase()];
    return targets.some((t) => t.includes(keyword));
  });
}

function renderSkillList() {
  const skills = getFilteredSkills();
  el.skillList.innerHTML = "";
  el.emptyState.style.display = skills.length ? "none" : "block";
  el.selectAllCheckbox.checked = skills.length > 0 && skills.every((s) => state.selectedIds.has(s.id));
  if (!skills.length) return;

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
        ${(skill.tags || []).map((t) => `<span class="chip">#${escapeHtml(t)}</span>`).join("")}
      </div>`;
    frag.appendChild(item);
  });
  el.skillList.appendChild(frag);
}

function renderChatWindow() {
  el.chatWindow.innerHTML = "";
  if (!state.chats.length) {
    const mode = getEffectiveMode();
    let txt = "你可以直接提问，Agent 将基于当前上下文自动作答。";
    if (mode === "uploaded") txt = "你可以直接提问，Agent 将在\"上传技能\"范围内自动路由并作答。";
    else if (mode === "builtin_fallback") txt = "你可以直接提问，当前使用\"内置技能回退\"模式自动路由并作答。";
    else if (mode === "none") txt = "你可以直接提问；当前未检索到技能，Agent 将在无技能上下文下作答。";
    el.chatWindow.innerHTML = `<p class="chat-msg bot">${txt}</p>`;
    return;
  }

  const frag = document.createDocumentFragment();
  state.chats.forEach((msg) => {
    const wrapper = document.createElement("div");
    wrapper.className = `chat-msg-wrap ${msg.role}`;
    const p = document.createElement("p");
    p.className = `chat-msg ${msg.role}`;
    p.textContent = msg.content;
    wrapper.appendChild(p);
    if (msg.sql_query) {
      const sqlBlock = document.createElement("div");
      sqlBlock.className = "sql-block";
      const badge = msg.validation_passed
        ? '<span class="validation-badge passed">校验通过</span>'
        : '<span class="validation-badge failed">校验未通过</span>';
      sqlBlock.innerHTML = `${badge}<pre><code>${escapeHtml(msg.sql_query)}</code></pre>`;
      wrapper.appendChild(sqlBlock);
    }
    frag.appendChild(wrapper);
  });
  el.chatWindow.appendChild(frag);
  el.chatWindow.scrollTop = el.chatWindow.scrollHeight;
}

function escapeHtml(text) {
  return String(text ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function addChatMessage(role, content, meta = {}) {
  state.chats.push({ role, content, time: Date.now(), ...meta });
}

async function handleFile(file) {
  if (!file) return;
  if (!/\.md$/i.test(file.name)) { showToast("仅支持上传 .md 文件。", true); return; }
  const formData = new FormData();
  formData.append("file", file);
  try {
    const result = await apiRequest("/skills/upload", { method: "POST", body: formData });
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

// ── Thread History ──────────────────────────────────────────────────────

async function fetchThreads() {
  try {
    const result = await apiRequest("/chat/threads");
    state.threads = result.items || [];
    renderThreadList();
  } catch (_err) { /* ignore */ }
}

function renderThreadList() {
  el.threadList.innerHTML = "";
  if (!state.threads.length) {
    el.threadList.innerHTML = '<p class="empty-state" style="padding:12px;font-size:0.85rem">暂无历史对话。</p>';
    return;
  }
  const frag = document.createDocumentFragment();
  state.threads.forEach((t) => {
    const div = document.createElement("div");
    div.className = `thread-item${t.thread_id === state.chatThreadId ? " active" : ""}`;
    const title = t.first_message || "空对话";
    const count = t.message_count || 0;
    div.innerHTML = `<div class="thread-item-text"><div class="thread-item-title">${escapeHtml(title)}</div><div class="thread-item-meta">${count} 条消息</div></div><span class="thread-item-badge">›</span>`;
    div.addEventListener("click", () => loadThread(t.thread_id));
    frag.appendChild(div);
  });
  el.threadList.appendChild(frag);
}

async function loadThread(threadId) {
  try {
    const result = await apiRequest(`/chat/threads/${threadId}`);
    const messages = result.messages || [];
    state.chatThreadId = threadId;
    state.chats = messages.map((m) => ({
      role: m.role,
      content: m.content,
      sql_query: m.sql_query || "",
      validation_passed: true,
      time: Date.now()
    }));
    state.historyVisible = false;
    el.threadHistory.style.display = "none";
    renderAll();
  } catch (err) {
    showToast(err.message || "加载对话失败", true);
  }
}

function startNewChat() {
  state.chatThreadId = null;
  state.chats = [];
  renderChatWindow();
  saveState();
}

// ── DB ──────────────────────────────────────────────────────────────────

function renderDbStatus() {
  const connected = state.dbConnected;
  el.dbStatusBadge.textContent = connected ? "已连接" : "未连接";
  el.dbStatusBadge.className = `badge${connected ? " connected" : ""}`;
  el.dbConnectBtn.style.display = connected ? "none" : "";
  el.dbDisconnectBtn.style.display = connected ? "" : "none";
  el.dbHost.disabled = connected;
  el.dbPort.disabled = connected;
  el.dbUser.disabled = connected;
  el.dbPassword.disabled = connected;
  el.dbDatabase.disabled = connected;
}

function renderDbTables(tables) {
  if (!tables || !tables.length) { el.dbTablesPreview.style.display = "none"; return; }
  el.dbTablesPreview.style.display = "";
  el.dbTablesList.innerHTML = "";
  const frag = document.createDocumentFragment();
  tables.forEach((t) => {
    const div = document.createElement("div");
    div.className = "db-table-item";
    const comment = t.comment ? ` — ${escapeHtml(t.comment)}` : "";
    div.innerHTML = `<span><span class="db-table-name">${escapeHtml(t.name)}</span><span class="db-table-comment">${comment}</span></span><span class="db-table-meta">${t.columns_count} 列</span>`;
    frag.appendChild(div);
  });
  el.dbTablesList.appendChild(frag);
}

async function fetchDbStatus() {
  try {
    const result = await apiRequest("/database/status");
    state.dbConnected = result.connected || false;
    if (result.connected) {
      el.dbHost.value = result.host || "";
      el.dbPort.value = result.port || 3306;
      el.dbUser.value = result.user || "";
      el.dbDatabase.value = result.database || "";
    }
    renderDbStatus();
  } catch (_err) { /* ignore */ }
}

// ── Event Binding ───────────────────────────────────────────────────────

function initAuthEvents() {
  el.authForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const u = el.authUsername.value.trim();
    const p = el.authPassword.value;
    if (!u || !p) { el.authError.textContent = "请输入用户名和密码。"; return; }
    el.loginBtn.disabled = true;
    el.registerBtn.disabled = true;
    await handleLogin(u, p);
    el.loginBtn.disabled = false;
    el.registerBtn.disabled = false;
  });

  el.registerBtn.addEventListener("click", async () => {
    const u = el.authUsername.value.trim();
    const p = el.authPassword.value;
    if (!u || !p) { el.authError.textContent = "请输入用户名和密码。"; return; }
    if (p.length < 4) { el.authError.textContent = "密码至少 4 位。"; return; }
    el.loginBtn.disabled = true;
    el.registerBtn.disabled = true;
    await handleRegister(u, p);
    el.loginBtn.disabled = false;
    el.registerBtn.disabled = false;
  });

  el.logoutBtn.addEventListener("click", handleLogout);
}

function initEvents() {
  el.newChatBtn.addEventListener("click", startNewChat);
  el.toggleHistoryBtn.addEventListener("click", async () => {
    state.historyVisible = !state.historyVisible;
    el.threadHistory.style.display = state.historyVisible ? "" : "none";
    if (state.historyVisible) {
      await fetchThreads();
    }
  });

  el.selectFileBtn.addEventListener("click", () => el.fileInput.click());
  el.importBtn.addEventListener("click", () => el.fileInput.click());
  el.fileInput.addEventListener("change", async (e) => { await handleFile(e.target.files?.[0]); e.target.value = ""; });

  ["dragenter", "dragover"].forEach((n) => el.dropZone.addEventListener(n, (e) => { e.preventDefault(); el.dropZone.classList.add("drag-over"); }));
  ["dragleave", "drop"].forEach((n) => el.dropZone.addEventListener(n, () => el.dropZone.classList.remove("drag-over")));
  el.dropZone.addEventListener("drop", async (e) => { e.preventDefault(); await handleFile(e.dataTransfer?.files?.[0]); });
  el.dropZone.addEventListener("click", () => el.fileInput.click());
  el.dropZone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); el.fileInput.click(); } });

  el.searchInput.addEventListener("input", (e) => { state.searchKeyword = e.target.value || ""; renderSkillList(); });

  el.skillList.addEventListener("click", async (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    const id = target.dataset.id;
    if (!id) return;
    if (target.classList.contains("delete-btn")) {
      const cur = state.skills.find((s) => s.id === id);
      const sf = (cur?.source_file || "").trim();
      if (!window.confirm(sf ? "该技能来自上传文件，删除后会同步删除同一文件导入的全部技能，确认继续吗？" : "确认删除该技能吗？")) return;
      try {
        await apiRequest(`/skills/${id}`, { method: "DELETE" });
        state.selectedIds.delete(id);
        await fetchSkills();
        showToast("技能已删除");
        renderAll();
      } catch (err) { showToast(err.message || "删除失败", true); }
    }
  });

  el.skillList.addEventListener("change", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLInputElement) || !target.classList.contains("skill-checkbox")) return;
    const id = target.dataset.id;
    if (!id) return;
    target.checked ? state.selectedIds.add(id) : state.selectedIds.delete(id);
    const allIds = getFilteredSkills().map((s) => s.id);
    el.selectAllCheckbox.checked = allIds.length > 0 && allIds.every((n) => state.selectedIds.has(n));
  });

  el.selectAllCheckbox.addEventListener("change", (e) => {
    const checked = e.target.checked;
    getFilteredSkills().forEach((s) => checked ? state.selectedIds.add(s.id) : state.selectedIds.delete(s.id));
    renderSkillList();
  });

  el.batchDeleteBtn.addEventListener("click", async () => {
    if (!state.selectedIds.size) { showToast("请先选中要删除的技能。", true); return; }
    if (!window.confirm(`确认删除已选中的 ${state.selectedIds.size} 项技能吗？`)) return;
    try {
      await apiRequest("/skills/batch-delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: Array.from(state.selectedIds) }) });
      state.selectedIds = new Set();
      el.selectAllCheckbox.checked = false;
      await fetchSkills();
      showToast("批量删除完成");
      renderAll();
    } catch (err) { showToast(err.message || "批量删除失败", true); }
  });

  el.chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = el.chatInput.value.trim();
    if (!text) return;
    addChatMessage("user", text);
    renderChatWindow();
    el.chatInput.value = "";
    try {
      const result = await apiRequest("/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text, thread_id: state.chatThreadId }) });
      state.chatThreadId = result.thread_id || state.chatThreadId;
      addChatMessage("bot", result.answer || "助手未返回内容。", { sql_query: result.sql_query || "", validation_passed: result.validation_passed !== false });
      renderChatWindow();
      saveState();
    } catch (err) {
      addChatMessage("bot", `请求失败：${err.message || "未知错误"}`);
      renderChatWindow();
      saveState();
    }
  });
}

function initDbEvents() {
  fetchDbStatus();

  el.dbForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const host = el.dbHost.value.trim();
    const port = parseInt(el.dbPort.value, 10) || 3306;
    const user = el.dbUser.value.trim();
    const password = el.dbPassword.value;
    const database = el.dbDatabase.value.trim();
    if (!host || !user || !database) { showToast("请填写 Host、User 和 Database。", true); return; }
    el.dbConnectBtn.disabled = true;
    el.dbConnectBtn.textContent = "连接中...";
    try {
      const result = await apiRequest("/database/connect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ host, port, user, password, database }) });
      state.dbConnected = true;
      renderDbStatus();
      renderDbTables(result.tables || []);
      showToast(`已连接 ${result.database}，共 ${(result.tables || []).length} 张表`);
    } catch (err) { showToast(err.message || "连接失败", true); }
    finally { el.dbConnectBtn.disabled = false; el.dbConnectBtn.textContent = "连接"; }
  });

  el.dbDisconnectBtn.addEventListener("click", async () => {
    try {
      await apiRequest("/database/disconnect", { method: "POST" });
      state.dbConnected = false;
      renderDbStatus();
      renderDbTables([]);
      el.dbPassword.value = "";
      showToast("已断开连接");
    } catch (err) { showToast(err.message || "断开失败", true); }
  });
}

// ── Bootstrap ───────────────────────────────────────────────────────────

async function bootstrap() {
  initAuthEvents();

  if (state.token) {
    try {
      await apiRequest("/auth/me");
      await onLoginSuccess();
    } catch (_err) {
      handleLogout();
    }
  } else {
    showAuth();
  }

  initEvents();
  initDbEvents();
}

void bootstrap();
