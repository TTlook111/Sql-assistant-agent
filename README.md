# Sql-assistant-agent

基于 `FastAPI + LangChain/LangGraph + SQLite` 的 SQL 助手项目，支持技能（skills）管理、`skills.md` 上传生效，以及带技能路由上下文的对话生成。

## 项目特性

- 技能管理：支持技能列表、新增、单条删除、批量删除。
- 上传技能文档：支持上传 `skills.md`（Markdown），自动入库并参与检索。
- 生效策略：
  - 若存在用户上传技能，仅使用上传技能参与 Agent 路由。
  - 若无上传技能，自动回退到内置技能。
- 对话能力：通过中间件注入候选技能摘要，并可由工具按需加载完整技能内容。
- 多用户隔离：通过请求头 `x-user-id` 做用户级数据隔离。

## 技术栈

- Python `3.13+`
- FastAPI / Uvicorn
- LangChain / LangGraph
- SQLite（本地持久化技能数据）
- 前端：原生 `HTML + CSS + JavaScript`

## 目录结构

```text
sql-assistant-agent/
├─ sql_assistant_agent/
│  ├─ main.py                    # FastAPI 入口
│  ├─ middleware/skill_middleware.py
│  ├─ storage/skill_store.py
│  ├─ tools/load_skill.py
│  └─ ...
├─ frontend/                     # 前端页面与静态资源
├─ data/skills.db                # SQLite 数据文件
├─ pyproject.toml
└─ README.md
```

## 环境准备

1. 安装依赖（推荐使用 `uv`）：

```bash
uv sync
```

2. 在项目根目录创建 `.env`，至少配置：

```env
DASHSCOPE_API_KEY=你的DashScopeKey
```

## 启动方式

在项目根目录执行：

```bash
uv run uvicorn sql_assistant_agent.main:app --reload
```

启动后访问：

- 前端页面：`http://127.0.0.1:8000/`
- 健康检查：`http://127.0.0.1:8000/api/health`

## API 概览

- `GET /api/health`：服务健康检查
- `GET /api/skills`：获取技能列表
- `POST /api/skills`：新增/更新技能
- `DELETE /api/skills/{skill_id}`：删除单个技能
- `POST /api/skills/batch-delete`：批量删除技能
- `POST /api/skills/upload`：上传 `skills.md`
- `POST /api/chat`：对话问答（SQL 助手）

### 请求头说明

- `x-user-id`：可选，默认 `demo-user`，长度不超过 64。

## 前端使用说明

- 打开首页可直接进行：
  - `skills.md` 文件上传（支持拖拽）
  - 技能搜索、勾选、批量删除
  - 基于当前生效技能的对话问答
- 可通过 URL 参数切换用户隔离空间：
  - 示例：`http://127.0.0.1:8000/?user_id=test_user`

## 说明与约束

- 上传文件仅支持 `.md`。
- 若上传技能存在，将覆盖内置技能生效路径（仅上传技能参与路由）。
- `data/skills.db` 为本地数据库文件，建议在生产场景使用独立持久化方案和备份策略。
