# SQL Assistant Agent

> 基于 **FastAPI + LangGraph 自定义 StateGraph** 的 NL2SQL 助手，通过技能文档（Skills）实现业务语义增强，让 SQL 生成"查得对"，并直接返回查询结果数据。

## 项目简介

传统 NL2SQL 方案仅依赖数据库 Schema 生成 SQL，但在真实业务场景中，字段名可能是缩写、注释缺失、业务口径不明。本项目引入 **Skills 语义层**：

- **Schema 负责"能查"** — 表结构、字段类型、主外键关系
- **Skills 负责"查对"** — 业务定义、指标口径、过滤规则、示例 SQL

### 核心流程

```
用户提问 → AI规划意图 → 加载技能文档 → 生成SQL → 执行查询 → 返回数据表格
```

## 核心特性

- **自定义 ReAct 图**：4 节点 StateGraph（规划 → 技能加载 → SQL 生成 → 校验），推理链路可观察
- **数据库连接**：支持 MySQL 实时连接，自动内省 Schema（表结构、主外键、索引）并缓存
- **技能管理**：支持 CRUD、批量删除、`skills.md` 上传自动解析
- **多用户隔离**：JWT 认证 + 用户级数据隔离
- **SQL 自动校验**：生成的 SQL 经 LLM 审查语法、字段引用和业务规则一致性
- **自动重试**：校验失败时自动修正 SQL（最多 2 次）
- **数据直返**：执行 SQL 并返回查询结果，以表格形式展示
- **数据库列表**：填写连接信息后自动获取可用数据库列表供选择

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| Agent 引擎 | LangGraph StateGraph（自定义 4 节点 ReAct 流程） |
| LLM | 通义千问 qwen3-max（DashScope） |
| 数据库 | MySQL（PyMySQL），支持实时 Schema 内省 |
| 认证 | JWT（PyJWT） |
| 存储 | MySQL（用户/技能数据）+ 文件系统（Markdown 格式） |
| 前端 | 原生 HTML + CSS + JavaScript（ES Modules） |

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
│  ├─ auth/
│  │  ├─ deps.py                 # JWT 认证依赖
│  │  └─ jwt.py                  # JWT 生成与验证
│  ├─ config/config.py           # 环境变量与路径配置
│  ├─ db/
│  │  ├─ connection.py           # MySQL 连接管理（DatabaseManager）
│  │  ├─ init_db.py              # 应用数据库初始化
│  │  ├─ models.py               # SQLAlchemy 模型定义
│  │  └─ schema.py               # Schema 内省（表结构、主外键、索引）
│  ├─ runtime/context.py         # 用户上下文（ContextVar）
│  ├─ storage/
│  │  ├─ skill_store.py          # 文件系统技能存储
│  │  └─ mysql_skill_store.py    # MySQL 技能存储
│  └─ tools/load_skill.py        # 技能加载工具（供扩展使用）
├─ frontend/
│  ├─ index.html                 # 页面结构
│  ├─ styles.css                 # 主样式（导入 CSS 模块）
│  ├─ css/
│  │  ├─ variables.css           # CSS 变量定义
│  │  ├─ base.css                # 基础样式
│  │  ├─ layout.css              # 布局系统
│  │  ├─ components.css          # 通用组件样式
│  │  └─ animations.css          # 动画效果
│  └─ js/
│     ├─ app.js                  # 入口文件
│     ├─ state.js                # 状态管理（发布订阅）
│     ├─ api.js                  # API 客户端
│     ├─ auth.js                 # 认证模块
│     ├─ utils.js                # 工具函数
│     └─ components/
│        ├─ toast.js             # Toast 通知
│        ├─ statusStrip.js       # 状态栏
│        ├─ skillList.js         # 技能列表
│        ├─ fileUpload.js        # 文件上传
│        ├─ dbPanel.js           # 数据库面板
│        └─ chatPanel.js         # 聊天面板
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
# DashScope API Key（必须）
DASHSCOPE_API_KEY=你的DashScopeKey

# 应用数据库配置（可选，默认值如下）
APP_DB_HOST=127.0.0.1
APP_DB_PORT=3306
APP_DB_USER=root
APP_DB_PASSWORD=123456
APP_DB_NAME=sql_assistant

# JWT 密钥（可选）
JWT_SECRET_KEY=your-secret-key
```

## 启动

```bash
uv run uvicorn sql_assistant_agent.main:app --reload
```

- 前端页面：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## API 概览

### 认证接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 用户注册 |
| `POST` | `/api/auth/login` | 用户登录，返回 JWT |
| `GET` | `/api/auth/me` | 验证当前用户 |

### 数据库接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/database/list` | 获取 MySQL 服务器上的数据库列表 |
| `POST` | `/api/database/connect` | 连接指定数据库并加载 Schema |
| `POST` | `/api/database/disconnect` | 断开数据库连接 |
| `GET` | `/api/database/status` | 查询数据库连接状态 |

### 技能接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/skills` | 获取技能列表 |
| `POST` | `/api/skills` | 新增/更新技能 |
| `DELETE` | `/api/skills/{skill_id}` | 删除单个技能 |
| `POST` | `/api/skills/batch-delete` | 批量删除技能 |
| `POST` | `/api/skills/upload` | 上传 `skills.md` |

### 对话接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat` | 对话问答（生成SQL并执行） |
| `GET` | `/api/chat/threads` | 获取会话列表 |
| `GET` | `/api/chat/threads/{thread_id}` | 获取会话消息 |

## API 示例

### 获取数据库列表

```bash
curl -X POST http://localhost:8000/api/database/list \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"host": "127.0.0.1", "port": 3306, "user": "root", "password": "123456"}'
```

**响应：**

```json
{
  "databases": ["mydb", "test", "production"]
}
```

### 连接数据库

```bash
curl -X POST http://localhost:8000/api/database/connect \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "mydb"
  }'
```

**响应：**

```json
{
  "status": "connected",
  "database": "mydb",
  "host": "127.0.0.1",
  "tables": [
    { "name": "orders", "comment": "订单表", "columns_count": 12, "row_count": 50000 }
  ]
}
```

### 对话问答

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"message": "有哪些老师"}'
```

**响应：**

```json
{
  "thread_id": "xxx",
  "answer": "查询完成，共返回 4 条记录。",
  "sql_query": "SELECT TeacherName FROM teachers;",
  "validation_passed": true,
  "data": [
    {"TeacherName": "李老师"},
    {"TeacherName": "王老师"},
    {"TeacherName": "张老师"},
    {"TeacherName": "刘校长"}
  ],
  "columns": ["TeacherName"],
  "row_count": 4,
  "execution_error": ""
}
```

## 前端功能

- **用户认证**：注册/登录，JWT 令牌管理
- **数据库连接**：
  - 填写 Host/Port/User/Password 后自动获取数据库列表
  - 从下拉框选择数据库，一键连接
- **技能上传**：拖拽或选择 `skills.md` 文件上传，自动解析导入
- **技能管理**：搜索、勾选、单条删除、批量删除
- **对话问答**：
  - 基于当前数据库和技能的 SQL 问答
  - 直接返回查询结果，以表格形式展示
  - 支持多轮对话，会话历史记录
- **响应式设计**：支持桌面端和移动端

## 前端架构

前端采用 **原生 ES Modules** 模块化架构，无需构建工具：

```
├── 状态管理（state.js）      # 发布订阅模式，集中状态管理
├── API 层（api.js）          # 统一请求封装，JWT 认证
├── 认证模块（auth.js）       # 登录/注册/登出
└── UI 组件（components/）    # 每个功能区域独立模块
    ├── toast.js              # 通用通知
    ├── statusStrip.js        # 顶部状态栏
    ├── skillList.js          # 技能列表
    ├── fileUpload.js         # 文件上传
    ├── dbPanel.js            # 数据库面板
    └── chatPanel.js          # 聊天面板
```

## 说明与约束

- 数据库连接支持 MySQL（通过 PyMySQL），连接信息按用户隔离
- 连接成功后自动内省 Schema 并缓存，SQL 生成时直接使用缓存的表结构信息
- 上传文件仅支持 `.md` 格式
- 存在上传技能时，仅上传技能参与路由；无上传技能时自动回退到内置技能
- 同一来源文件重复上传会先清理旧技能再导入，避免残留
- SQL 校验基于 LLM，不保证 100% 准确，生产环境建议叠加执行前人工审核
- 应用数据库（`sql_assistant`）存储用户账号和技能数据，需提前创建
