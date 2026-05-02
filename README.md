# SQL Assistant Agent

> 基于 **FastAPI + LangGraph 自定义 StateGraph** 的 NL2SQL 助手，通过技能文档（Skills）实现业务语义增强，让 SQL 生成"查得对"。

## 项目简介

传统 NL2SQL 方案仅依赖数据库 Schema 生成 SQL，但在真实业务场景中，字段名可能是缩写、注释缺失、业务口径不明。本项目引入 **Skills 语义层**：

- **Schema 负责"能查"** — 表结构、字段类型、主外键关系
- **Skills 负责"查对"** — 业务定义、指标口径、过滤规则、示例 SQL

## 核心特性

- **自定义 ReAct 图**：4 节点 StateGraph（规划 → 技能加载 → SQL 生成 → 校验），推理链路可观察
- **技能管理**：支持 CRUD、批量删除、`skills.md` 上传自动解析
- **多用户隔离**：通过 `x-user-id` 请求头实现用户级数据隔离
- **SQL 自动校验**：生成的 SQL 经 LLM 审查语法、字段引用和业务规则一致性
- **自动重试**：校验失败时自动修正 SQL（最多 2 次）

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| Agent 引擎 | LangGraph StateGraph（自定义 4 节点 ReAct 流程） |
| LLM | 通义千问 qwen3-max（DashScope） |
| 存储 | 文件系统（Markdown 格式） |
| 前端 | 原生 HTML + CSS + JavaScript |

## 目录结构

```text
sql-assistant-agent/
├─ sql_assistant_agent/
│  ├─ main.py                    # FastAPI 入口 + API 路由
│  ├─ agent/
│  │  ├─ builder.py              # StateGraph 构建（节点 + 边 + 条件路由）
│  │  ├─ nodes.py                # 4 个图节点函数 + 路由逻辑
│  │  ├─ prompts.py              # 各节点提示词模板
│  │  └─ state.py                # 图状态 schema 定义
│  ├─ config/config.py           # 环境变量与路径配置
│  ├─ runtime/context.py         # 用户上下文（ContextVar）
│  ├─ services/markdown_skills.py # Markdown 技能解析与导出
│  ├─ storage/skill_store.py     # 文件系统技能存储 + 检索
│  └─ tools/load_skill.py        # 技能加载工具（供扩展使用）
├─ frontend/
│  ├─ index.html                 # 页面结构
│  ├─ styles.css                 # 样式
│  └─ app.js                     # 前端逻辑
├─ agent/skills/
│  ├─ builtin/*.md               # 内置技能文档
│  └─ users/<user_id>/
│     ├─ skills.md               # 用户技能主文件
│     └─ uploads/*.md            # 上传原文件
├─ pyproject.toml
└─ README.md
```

## Agent 图结构

```
                         ┌─────────────┐
                         │   START     │
                         └──────┬──────┘
                                │
                         ┌──────▼──────┐
                         │   planner   │  分析意图，决定行动
                         └──────┬──────┘
                                │
                    ┌───────────┼───────────┐
                    │           │           │
             "load_skill"  "direct_sql"  "reply"
                    │           │           │
           ┌────────▼───┐      │      ┌────▼────┐
           │skill_loader│      │      │   END   │  直接回复
           └────────┬───┘      │      └─────────┘
                    │          │
                    └────┬─────┘
                         │
                  ┌──────▼──────┐
                  │sql_generator│  结合技能文档生成 SQL
                  └──────┬──────┘
                         │
                  ┌──────▼──────┐
                  │  validator  │  语法/语义/业务规则校验
                  └──────┬──────┘
                         │
                ┌────────┴────────┐
                │                 │
           校验通过           校验失败（≤2次）
                │                 │
          ┌─────▼─────┐    ┌─────▼──────┐
          │    END    │    │sql_generator│  修正重试
          └───────────┘    └────────────┘
```

## 环境准备

1. 安装依赖（推荐 `uv`）：

```bash
uv sync
```

2. 在项目根目录创建 `.env`：

```env
DASHSCOPE_API_KEY=你的DashScopeKey
```

## 启动

```bash
uv run uvicorn sql_assistant_agent.main:app --reload
```

- 前端页面：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/skills` | 获取技能列表 |
| `POST` | `/api/skills` | 新增/更新技能 |
| `DELETE` | `/api/skills/{skill_id}` | 删除单个技能 |
| `POST` | `/api/skills/batch-delete` | 批量删除技能 |
| `POST` | `/api/skills/upload` | 上传 `skills.md` |
| `POST` | `/api/chat` | 对话问答 |

### 对话接口

**请求：**

```json
POST /api/chat
Headers: { "x-user-id": "demo-user" }
{
  "message": "查询最近一个季度营收前10的客户",
  "thread_id": "可选，用于多轮对话"
}
```

**响应：**

```json
{
  "thread_id": "xxx",
  "answer": "根据销售分析技能，以下是查询...",
  "sql_query": "SELECT c.customer_id, c.name, ...",
  "validation_passed": true
}
```

### 请求头

| Header | 说明 | 默认值 |
|--------|------|--------|
| `x-user-id` | 用户 ID（字母、数字、下划线、短横线，≤64 字符） | `demo-user` |

## 前端功能

- **技能上传**：拖拽或选择 `skills.md` 文件上传，自动解析导入
- **技能管理**：搜索、勾选、单条删除、批量删除
- **对话问答**：基于当前生效技能的 SQL 问答，展示生成的 SQL 和校验结果
- **多用户切换**：URL 参数 `?user_id=xxx` 切换隔离空间

## 说明与约束

- 上传文件仅支持 `.md` 格式
- 存在上传技能时，仅上传技能参与路由；无上传技能时自动回退到内置技能
- 同一来源文件重复上传会先清理旧技能再导入，避免残留
- SQL 校验基于 LLM，不保证 100% 准确，生产环境建议叠加执行前人工审核
