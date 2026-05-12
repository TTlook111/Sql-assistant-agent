# SQL Assistant Agent

> 基于 **FastAPI + LangGraph** 的智能 NL2SQL 助手，让自然语言查询数据库变得简单。

## 项目简介

SQL Assistant Agent 是一个将自然语言转换为 SQL 查询的智能助手。用户只需用中文描述想要查询的内容，AI 会自动生成 SQL、执行查询并返回结果数据。

**核心价值：**
- **降低门槛** — 不会写 SQL 也能查询数据库
- **语义增强** — 通过技能文档理解业务术语和指标口径
- **即时反馈** — 直接返回查询结果，不是生成 SQL 让你复制

```
用户："最近一个月销售额最高的前10个客户"
  ↓
AI 自动处理：理解意图 → 生成SQL → 执行查询 → 返回表格
```

## 核心特性

| 特性 | 说明 |
|------|------|
| **自然语言查询** | 用中文描述需求，AI 自动生成并执行 SQL |
| **技能语义层** | 通过 `skills.md` 文档补充业务定义，让查询更准确 |
| **数据库连接** | 支持 MySQL 实时连接，自动获取表结构 |
| **数据直返** | 查询结果直接以表格形式展示，支持导出 CSV |
| **多轮对话** | 支持上下文理解，可以追问和细化查询 |
| **用户隔离** | JWT 认证，每个用户独立的数据库连接和技能 |
| **SQL 安全** | 只允许执行 SELECT 等只读查询，防止误操作 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| AI 引擎 | LangGraph StateGraph（4 节点 ReAct 流程） |
| LLM | 通义千问 qwen3-max（DashScope） |
| 数据库 | MySQL（PyMySQL） |
| ORM | SQLAlchemy |
| 认证 | JWT（PyJWT + bcrypt） |
| 前端 | 原生 HTML + CSS + JavaScript（ES Modules） |
| 测试 | pytest |

## 目录结构

```text
sql-assistant-agent/
├─ sql_assistant_agent/           # 后端代码
│  ├─ main.py                    # FastAPI 入口 + 所有 API 路由
│  ├─ agent/                     # LangGraph Agent
│  │  ├─ builder.py              # StateGraph 构建
│  │  ├─ nodes.py                # 图节点函数（规划/技能/生成/校验）
│  │  ├─ prompts.py              # LLM 提示词模板
│  │  └─ state.py                # 图状态定义
│  ├─ auth/                      # 认证模块
│  │  ├─ deps.py                 # FastAPI 依赖注入
│  │  └─ jwt.py                  # JWT 生成与验证
│  ├─ config/config.py           # 环境变量配置
│  ├─ db/                        # 数据库模块
│  │  ├─ connection.py           # 用户数据库连接管理
│  │  ├─ init_db.py              # 应用数据库初始化
│  │  ├─ models.py               # SQLAlchemy 模型
│  │  └─ schema.py               # Schema 内省
│  ├─ runtime/context.py         # 用户上下文
│  ├─ services/markdown_skills.py # 技能文档解析
│  └─ storage/mysql_skill_store.py # 技能存储
├─ frontend/                     # 前端代码
│  ├─ index.html                 # 页面入口
│  ├─ styles.css                 # 样式入口
│  ├─ css/                       # CSS 模块
│  │  ├─ variables.css           # CSS 变量
│  │  ├─ base.css                # 基础样式
│  │  ├─ layout.css              # 布局
│  │  ├─ components.css          # 组件样式
│  │  └─ animations.css          # 动画
│  └─ js/                        # JavaScript 模块
│     ├─ app.js                  # 入口
│     ├─ state.js                # 状态管理
│     ├─ api.js                  # API 客户端
│     ├─ auth.js                 # 认证
│     ├─ utils.js                # 工具函数
│     └─ components/             # UI 组件
├─ tests/                        # 单元测试
│  ├─ test_main.py               # 核心功能测试
│  ├─ test_auth.py               # 认证测试
│  └─ test_utils.py              # 工具函数测试
├─ pyproject.toml                # 项目配置
└─ README.md
```

## Agent 流程

```
用户提问
    ↓
┌─────────┐     ┌─────────────┐     ┌──────────────┐     ┌───────────┐
│ Planner │ ──→ │ Skill Loader│ ──→ │ SQL Generator│ ──→ │ Validator │
│ 规划意图 │     │ 加载技能文档 │     │ 生成 SQL     │     │ 校验 SQL  │
└─────────┘     └─────────────┘     └──────────────┘     └───────────┘
                                                                │
                                                    ┌───────────┴───────────┐
                                                    │                       │
                                                校验通过               校验失败
                                                    │                       │
                                                执行查询              修正重试（≤2次）
                                                    ↓
                                              返回数据表格
```

## 快速开始

### 1. 安装依赖

```bash
# 推荐使用 uv
uv sync

# 或使用 pip
pip install -e .
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
# 必须：DashScope API Key
DASHSCOPE_API_KEY=sk-xxxxxxxx

# 可选：应用数据库（默认值如下）
APP_DB_HOST=127.0.0.1
APP_DB_PORT=3306
APP_DB_USER=root
APP_DB_PASSWORD=123456
APP_DB_NAME=sql_assistant

# 可选：JWT 密钥
JWT_SECRET_KEY=your-secret-key
```

### 3. 启动服务

```bash
uv run uvicorn sql_assistant_agent.main:app --reload
```

### 4. 访问

- **前端页面**：http://localhost:8000
- **API 文档**：http://localhost:8000/docs

## API 接口

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| GET | `/api/auth/me` | 验证 Token |

### 数据库

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/database/list` | 获取数据库列表 |
| POST | `/api/database/connect` | 连接数据库 |
| POST | `/api/database/disconnect` | 断开连接 |
| GET | `/api/database/status` | 连接状态 |

### 技能

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/skills` | 技能列表 |
| POST | `/api/skills/upload` | 上传 skills.md |
| DELETE | `/api/skills/{id}` | 删除技能 |

### 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 发送问题 |
| GET | `/api/chat/threads` | 会话列表 |
| GET | `/api/chat/threads/{id}` | 会话消息 |

## 使用示例

### 1. 连接数据库

```
左侧边栏 → 数据库连接
填写 Host/Port/User/Password → 自动加载数据库列表 → 选择数据库 → 连接
```

### 2. 查询数据

```
右侧对话框输入："有哪些老师"
  ↓
返回表格：
┌────────────┐
│ TeacherName│
├────────────┤
│ 李老师     │
│ 王老师     │
│ 张老师     │
│ 刘校长     │
└────────────┘
```

### 3. 上传技能文档

创建 `skills.md`：

```markdown
# 销售分析

## 表结构
- orders: 订单表（order_id, customer_id, amount, created_at）
- customers: 客户表（customer_id, name, region）

## 业务定义
- "销售额" = SUM(amount)，状态为 completed
- "活跃客户" = 最近90天有订单的客户
```

上传后，AI 会根据这些定义生成更准确的 SQL。

## 测试

```bash
# 运行所有测试
uv run pytest tests/ -v

# 运行特定测试
uv run pytest tests/test_main.py -v

# 查看覆盖率
uv run pytest tests/ --cov=sql_assistant_agent
```

## 环境变量

| 变量 | 必须 | 说明 | 默认值 |
|------|------|------|--------|
| `DASHSCOPE_API_KEY` | ✅ | DashScope API Key | - |
| `APP_DB_HOST` | ❌ | 应用数据库主机 | 127.0.0.1 |
| `APP_DB_PORT` | ❌ | 应用数据库端口 | 3306 |
| `APP_DB_USER` | ❌ | 应用数据库用户 | root |
| `APP_DB_PASSWORD` | ❌ | 应用数据库密码 | 123456 |
| `APP_DB_NAME` | ❌ | 应用数据库名 | sql_assistant |
| `JWT_SECRET_KEY` | ❌ | JWT 签名密钥 | 内置默认值 |
| `CORS_ORIGINS` | ❌ | CORS 允许的来源 | * |

## 注意事项

1. **SQL 安全**：只允许执行 SELECT 等只读查询，禁止 INSERT/UPDATE/DELETE/DROP
2. **技能优先级**：上传的技能优先于内置技能生效
3. **连接隔离**：每个用户的数据库连接独立，互不影响
4. **查询限制**：单次查询最多返回 1000 条记录

## License

MIT
