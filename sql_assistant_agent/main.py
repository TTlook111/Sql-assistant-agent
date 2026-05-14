from __future__ import annotations

import os
import re
import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain.messages import HumanMessage, SystemMessage
from langchain_community.chat_models.tongyi import ChatTongyi
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_assistant_agent.agent.builder import build_sql_assistant_agent
from sql_assistant_agent.auth.deps import get_current_user_id
from sql_assistant_agent.auth.jwt import (
    create_access_token,
    hash_password,
    verify_password,
)
from sql_assistant_agent.config.config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_MODEL,
    PROJECT_ROOT,
    SKILL_FILES_DIR,
    SQL_ASSISTANT_AUTO_RETRY_ON_REVIEW_FAIL,
    SQL_ASSISTANT_QUERY_MAX_ROWS,
    SQL_ASSISTANT_REVIEW_ANSWER,
)
from sql_assistant_agent.db.connection import DatabaseConfig, get_db_manager
from sql_assistant_agent.db.init_db import get_db, get_db_session
from sql_assistant_agent.db.models import ChatMessage, ChatThread, User
from sql_assistant_agent.db.schema import (
    format_schema_markdown,
    get_tables_summary,
    introspect_schema,
)
from sql_assistant_agent.runtime.context import user_context
from sql_assistant_agent.storage.mysql_skill_store import MySQLSkillStore

app = FastAPI(title="SQL Assistant Agent API", version="0.2.0")

# CORS配置 - 开发环境允许所有来源，生产环境应限制
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

skill_store = MySQLSkillStore()
review_model = ChatTongyi(model=DASHSCOPE_MODEL, api_key=DASHSCOPE_API_KEY)
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SKILL_FILES_DIR.mkdir(parents=True, exist_ok=True)


# ── Payload / Response Models ───────────────────────────────────────────

class RegisterPayload(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class LoginPayload(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class SkillCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list)
    content: str = Field(min_length=1)


class BatchDeletePayload(BaseModel):
    ids: list[str] = Field(default_factory=list)


class ChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    sql_query: str = ""
    validation_passed: bool = True
    data: list[dict[str, Any]] = []
    columns: list[str] = []
    row_count: int = 0
    row_limit: int = SQL_ASSISTANT_QUERY_MAX_ROWS
    truncated: bool = False
    response_ms: int = 0
    execution_error: str = ""
    review_passed: bool = True
    review_feedback: str = ""
    review_suggestion: str = ""
    retry_count: int = 0


class DatabaseConnectPayload(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=3306, ge=1, le=65535)
    user: str = Field(min_length=1)
    password: str = ""
    database: str = Field(min_length=1)


class DatabaseListPayload(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=3306, ge=1, le=65535)
    user: str = Field(min_length=1)
    password: str = ""


# ── Helpers ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_agent():
    return build_sql_assistant_agent()


_INTERNAL_PREFIXES = ("[规划]", "[技能加载]", "[校验]", "[Schema]")


def _extract_assistant_text(result: dict[str, Any]) -> str:
    messages = result.get("messages") or []
    for msg in reversed(messages):
        role = getattr(msg, "type", "") or getattr(msg, "role", "")
        if role in {"ai", "assistant"}:
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                if any(content.startswith(p) for p in _INTERNAL_PREFIXES):
                    continue
                return content
            if isinstance(content, list):
                text_items = [item.get("text", "") for item in content if isinstance(item, dict)]
                text = "\n".join([item for item in text_items if item]).strip()
                if any(text.startswith(p) for p in _INTERNAL_PREFIXES):
                    continue
                return text
    return "未获取到助手回复。"


def _parse_json_from_text(text: str) -> dict[str, Any] | None:
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", text)
    raw = match.group(1).strip() if match else text.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _safe_upload_filename(filename: str) -> str:
    raw = Path(filename or "skills.md").name.strip() or "skills.md"
    safe = "".join(ch if (ch.isalnum() or ch in {".", "_", "-"}) else "_" for ch in raw)
    return safe[:120] or "skills.md"


def _is_readonly_sql(sql_query: str) -> bool:
    """检查SQL是否为安全的只读查询"""
    normalized = sql_query.strip().lower()

    # 只允许以这些关键字开头
    allowed_starts = ("select", "show", "describe", "desc", "explain", "with")
    if not normalized.startswith(allowed_starts):
        return False

    # 禁止包含危险关键字（防止注入）
    dangerous_keywords = (
        "insert", "update", "delete", "drop", "alter", "create",
        "truncate", "replace", "merge", "grant", "revoke",
        "exec", "execute", "xp_", "sp_",
    )
    # 移除字符串字面量后再检查
    cleaned = re.sub(r"'[^']*'", "", normalized)
    cleaned = re.sub(r'"[^"]*"', "", cleaned)
    for keyword in dangerous_keywords:
        if re.search(r'\b' + keyword + r'\b', cleaned):
            return False

    # 禁止分号（防止多条语句）
    if ';' in normalized:
        return False

    return True


def _is_data_catalog_question(message: str) -> bool:
    text = re.sub(r"\s+", "", message.lower())
    catalog_patterns = (
        "可以查询哪些数据",
        "能查询哪些数据",
        "可以查哪些数据",
        "能查哪些数据",
        "有哪些数据可以查",
        "有哪些可以查询",
        "能查什么",
        "可以查什么",
        "查询范围",
        "数据范围",
    )
    return any(pattern in text for pattern in catalog_patterns)


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _summarize_query_result(
    data: list[dict[str, Any]],
    columns: list[str],
    error: str,
    truncated: bool,
) -> str:
    if error:
        return f"执行错误：{error}"

    sample_rows = data[:5]
    summary = {
        "row_count": len(data),
        "columns": columns,
        "truncated": truncated,
        "sample_rows": sample_rows,
    }
    return json.dumps(summary, ensure_ascii=False, default=str)


def _review_answer_satisfaction(
    *,
    user_message: str,
    sql_query: str,
    answer: str,
    data: list[dict[str, Any]],
    columns: list[str],
    error: str,
    truncated: bool,
) -> dict[str, Any]:
    if not SQL_ASSISTANT_REVIEW_ANSWER:
        return {"passed": True, "feedback": "", "suggestion": ""}

    if error:
        return {
            "passed": False,
            "feedback": f"SQL 执行失败，无法满足用户查询需求：{error}",
            "suggestion": "请根据执行错误修正 SQL，再重新查询。",
        }

    if not sql_query.strip():
        return {
            "passed": False,
            "feedback": "没有生成可执行 SQL，无法判断或满足用户的数据查询需求。",
            "suggestion": "请结合用户问题和数据库结构生成只读 SQL。",
        }

    result_summary = _summarize_query_result(data, columns, error, truncated)
    system_prompt = """\
你是 SQL 助手的最终答案审查器。请判断当前 SQL、执行结果和回答是否满足用户的原始问题。

审查标准：
1. SQL 查询目标是否覆盖用户问题的核心对象、过滤条件、排序、聚合或时间范围。
2. 返回字段是否足以回答问题，且没有明显查询了无关字段。
3. 执行结果是否能支撑当前回答。
4. 如果结果为空，只在 SQL 条件合理时才算通过。
5. 不要因为回答文字简短就判失败；只要数据和 SQL 能回答问题即可通过。

只输出 JSON，不要输出其他内容：
```json
{
  "passed": true 或 false,
  "feedback": "简短说明",
  "suggestion": "如果不通过，给出如何修正 SQL 或回答的建议"
}
```
"""
    human_prompt = f"""\
用户问题：
{user_message}

SQL：
```sql
{sql_query}
```

执行结果摘要：
{result_summary}

当前回答：
{answer}
"""
    try:
        response = review_model.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
        )
    except Exception as exc:
        return {
            "passed": True,
            "feedback": f"答案审查调用失败，已保留查询结果：{exc}",
            "suggestion": "",
        }

    response_text = response.content if isinstance(response.content, str) else ""
    parsed = _parse_json_from_text(response_text)
    if not parsed or "passed" not in parsed:
        return {
            "passed": True,
            "feedback": "答案审查结果解析失败，已保留查询结果。",
            "suggestion": "",
        }

    return {
        "passed": bool(parsed.get("passed")),
        "feedback": str(parsed.get("feedback") or "").strip(),
        "suggestion": str(parsed.get("suggestion") or "").strip(),
    }


def _is_retryable_review_failure(sql_query: str, error: str) -> bool:
    if not sql_query.strip():
        return True
    if not error:
        return True
    non_retryable_errors = ("数据库未连接", "获取数据库连接失败")
    return error not in non_retryable_errors


def _format_data_catalog_answer(user_id: int) -> str:
    db_manager = get_db_manager()
    info = db_manager.get_connection_info(user_id)
    if not info:
        return "当前还没有连接数据库。请先连接数据库，我再告诉你可以查询哪些业务数据。"

    topics: list[str] = []
    for index, table in enumerate(info.tables[:12], start=1):
        comment = str(table.get("comment") or "").strip()
        if _contains_chinese(comment):
            topic = comment
        else:
            topic = f"第 {index} 类业务数据"
        topics.append(f"{index}. {topic}")

    if not topics:
        return "当前数据库已连接，但还没有识别到可展示的数据范围。你可以先重新连接数据库刷新结构信息。"

    extra = ""
    if len(info.tables) > len(topics):
        extra = f"\n\n还有 {len(info.tables) - len(topics)} 类数据没有展开显示。"
    examples = "\n\n你可以直接这样问：\n- 查询最近十条记录\n- 按月份统计销售情况\n- 查找满足某个条件的数据"
    return "当前可以查询这些业务数据：\n" + "\n".join(topics) + extra + examples


def _build_suggested_questions(user_id: int) -> list[str]:
    base = [
        "现在可以查询哪些数据？",
        "查询最近十条记录",
        "按月份统计数量变化",
    ]
    db_manager = get_db_manager()
    info = db_manager.get_connection_info(user_id)
    if not info or not info.tables:
        return base

    suggestions = ["现在可以查询哪些数据？"]
    for index, table in enumerate(info.tables[:3], start=1):
        comment = str(table.get("comment") or "").strip()
        topic = comment if _contains_chinese(comment) else f"第 {index} 类业务数据"
        suggestions.append(f"查询{topic}的最近十条记录")
    suggestions.append("按月份统计数量变化")
    return suggestions[:5]


def _extract_sql_from_text(text: str) -> str:
    match = re.search(r"```sql\s*\n?([\s\S]*?)\n?\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _get_or_create_chat_thread(
    db: Session, user_id: int, thread_id: str, first_message: str
) -> ChatThread:
    row = db.execute(
        select(ChatThread).where(
            ChatThread.user_id == user_id,
            ChatThread.thread_id == thread_id,
        )
    ).scalar_one_or_none()
    if row:
        return row

    row = ChatThread(
        user_id=user_id,
        thread_id=thread_id,
        title=first_message.strip()[:200],
    )
    db.add(row)
    db.flush()
    return row


def _append_chat_snapshot(
    *,
    user_id: int,
    thread_id: str,
    user_message: str,
    response: ChatResponse,
) -> None:
    with get_db_session() as db:
        thread = _get_or_create_chat_thread(db, user_id, thread_id, user_message)
        db.add(
            ChatMessage(
                thread_pk=thread.id,
                role="user",
                content=user_message,
            )
        )
        db.add(
            ChatMessage(
                thread_pk=thread.id,
                role="bot",
                content=response.answer,
                sql_query=response.sql_query,
                validation_passed=response.validation_passed,
                data=response.data,
                columns=response.columns,
                row_count=response.row_count,
                row_limit=response.row_limit,
                truncated=response.truncated,
                response_ms=response.response_ms,
                execution_error=response.execution_error,
            )
        )


# ── Auth Endpoints ──────────────────────────────────────────────────────

@app.post("/api/auth/register")
def register(payload: RegisterPayload) -> dict[str, Any]:
    with get_db_session() as db:
        existing = db.execute(
            select(User).where(User.username == payload.username.strip())
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="用户名已存在。")
        user = User(
            username=payload.username.strip(),
            password_hash=hash_password(payload.password),
        )
        db.add(user)
        db.flush()
        user_id = user.id
        username = user.username

    token = create_access_token(user_id, username)
    return {"token": token, "user_id": user_id, "username": username}


@app.post("/api/auth/login")
def login(payload: LoginPayload) -> dict[str, Any]:
    with get_db_session() as db:
        user = db.execute(
            select(User).where(User.username == payload.username.strip())
        ).scalar_one_or_none()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="用户名或密码错误。")
        user_id = user.id
        username = user.username

    token = create_access_token(user_id, username)
    return {"token": token, "user_id": user_id, "username": username}


@app.get("/api/auth/me")
def get_me(user_id: int = Depends(get_current_user_id)) -> dict[str, Any]:
    with get_db_session() as db:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在。")
        return {"user_id": user.id, "username": user.username}


# ── Health ──────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Database Connection (User's own MySQL) ──────────────────────────────

@app.post("/api/database/list")
def database_list(
    payload: DatabaseListPayload,
    user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    """获取MySQL服务器上的数据库列表"""
    import pymysql

    conn = None
    try:
        conn = pymysql.connect(
            host=payload.host.strip(),
            port=payload.port,
            user=payload.user.strip(),
            password=payload.password,
            charset='utf8mb4',
            connect_timeout=5,
        )
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        databases = [row[0] for row in cursor.fetchall()]
        cursor.close()

        # 过滤掉系统数据库
        system_dbs = {'information_schema', 'mysql', 'performance_schema', 'sys'}
        user_databases = [db for db in databases if db not in system_dbs]

        return {"databases": user_databases}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"获取数据库列表失败: {exc}") from exc
    finally:
        if conn:
            conn.close()


@app.post("/api/database/connect")
def database_connect(
    payload: DatabaseConnectPayload,
    user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    db_manager = get_db_manager()
    config = DatabaseConfig(
        host=payload.host.strip(),
        port=payload.port,
        user=payload.user.strip(),
        password=payload.password,
        database=payload.database.strip(),
    )
    try:
        result = db_manager.connect(user_id, config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"连接失败: {exc}") from exc

    conn = db_manager.get_raw_connection(user_id)
    if conn:
        try:
            schema = introspect_schema(conn, config.database)
            schema_md = format_schema_markdown(schema)
            tables = get_tables_summary(schema)
            db_manager.set_schema_cache(user_id, schema_md, tables)
            result["tables"] = tables
        finally:
            conn.close()

    return result


@app.post("/api/database/disconnect")
def database_disconnect(user_id: int = Depends(get_current_user_id)) -> dict[str, Any]:
    db_manager = get_db_manager()
    disconnected = db_manager.disconnect(user_id)
    return {"disconnected": disconnected}


@app.get("/api/database/status")
def database_status(user_id: int = Depends(get_current_user_id)) -> dict[str, Any]:
    db_manager = get_db_manager()
    return db_manager.get_status(user_id)


# ── Skills ──────────────────────────────────────────────────────────────

@app.get("/api/skills")
def list_skills(user_id: int = Depends(get_current_user_id)) -> dict[str, Any]:
    with get_db_session() as db:
        return {"items": skill_store.list_skills(db, user_id)}


@app.post("/api/skills")
def create_skill(
    payload: SkillCreatePayload,
    user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    with get_db_session() as db:
        item = skill_store.upsert_skill(
            db,
            user_id,
            name=payload.name.strip(),
            description=payload.description.strip(),
            tags=[tag.strip() for tag in payload.tags if tag.strip()],
            content=payload.content.strip(),
        )
        return {"item": item}


@app.delete("/api/skills/{skill_id}")
def delete_skill(
    skill_id: str,
    user_id: int = Depends(get_current_user_id),
) -> dict[str, bool]:
    with get_db_session() as db:
        current = skill_store.get_skill_by_id(db, user_id, skill_id)
        if not current:
            raise HTTPException(status_code=404, detail="技能不存在")
        source_file = (current.get("source_file") or "").strip()
        if source_file:
            skill_store.delete_skills_by_source_file(db, user_id, source_file)
        else:
            skill_store.delete_skill(db, user_id, skill_id)
    return {"ok": True}


@app.post("/api/skills/batch-delete")
def delete_skills(
    payload: BatchDeletePayload,
    user_id: int = Depends(get_current_user_id),
) -> dict[str, int]:
    with get_db_session() as db:
        deleted_count = skill_store.delete_skills(db, user_id, payload.ids)
    return {"deleted_count": deleted_count}


@app.post("/api/skills/upload")
async def upload_skills(
    user_id: int = Depends(get_current_user_id),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="仅支持上传 .md 文件")
    content_bytes = await file.read()
    text = content_bytes.decode("utf-8", errors="ignore")
    content = text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    safe_name = _safe_upload_filename(file.filename)
    saved_file = skill_store.save_uploaded_markdown(user_id, safe_name, content)
    source = str(saved_file)
    with get_db_session() as db:
        imported_count = skill_store.import_skills_from_markdown(db, user_id, content, source)
    if imported_count <= 0:
        raise HTTPException(status_code=400, detail="未在文档中识别到可导入的技能段")
    with get_db_session() as db:
        items = skill_store.list_skills(db, user_id)
    return {"imported_count": imported_count, "items": items}


# ── Chat ────────────────────────────────────────────────────────────────

def _execute_sql_for_user(user_id: int, sql_query: str) -> tuple[list[dict[str, Any]], list[str], str, bool]:
    """执行SQL查询并返回结果"""
    if not sql_query or not sql_query.strip():
        return [], [], "", False

    # 清理SQL（移除可能的markdown代码块标记）
    sql_query = sql_query.strip()
    if sql_query.startswith("```sql"):
        sql_query = sql_query[6:]
    if sql_query.startswith("```"):
        sql_query = sql_query[3:]
    if sql_query.endswith("```"):
        sql_query = sql_query[:-3]
    sql_query = sql_query.strip()
    if not _is_readonly_sql(sql_query):
        return [], [], "仅允许执行只读查询语句", False

    db_manager = get_db_manager()
    if not db_manager.is_connected(user_id):
        return [], [], "数据库未连接", False

    conn = db_manager.get_raw_connection(user_id)
    if not conn:
        return [], [], "获取数据库连接失败", False

    try:
        import pymysql.cursors
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(sql_query)

        # 获取列名
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        # 获取数据
        rows = cursor.fetchmany(SQL_ASSISTANT_QUERY_MAX_ROWS + 1)
        truncated = len(rows) > SQL_ASSISTANT_QUERY_MAX_ROWS
        if truncated:
            rows = rows[:SQL_ASSISTANT_QUERY_MAX_ROWS]
        data = []
        for row in rows:
            row_dict = {}
            for col in columns:
                value = row.get(col)
                # 处理特殊类型
                if value is None:
                    row_dict[col] = None
                elif isinstance(value, (int, float, str, bool)):
                    row_dict[col] = value
                else:
                    row_dict[col] = str(value)
            data.append(row_dict)

        return data, columns, "", truncated
    except Exception as e:
        return [], [], str(e), False
    finally:
        conn.close()


@app.post("/api/chat")
def chat(
    payload: ChatPayload,
    user_id: int = Depends(get_current_user_id),
) -> ChatResponse:
    import time

    started = time.perf_counter()
    if _is_data_catalog_question(payload.message):
        client_thread_id = payload.thread_id or str(uuid4())
        response = ChatResponse(
            thread_id=client_thread_id,
            answer=_format_data_catalog_answer(user_id),
            validation_passed=True,
            response_ms=round((time.perf_counter() - started) * 1000),
        )
        _append_chat_snapshot(
            user_id=user_id,
            thread_id=client_thread_id,
            user_message=payload.message,
            response=response,
        )
        return response

    agent = get_agent()
    client_thread_id = payload.thread_id or str(uuid4())
    checkpoint_thread_id = f"{user_id}:{client_thread_id}"
    config = {"configurable": {"thread_id": checkpoint_thread_id, "user_id": str(user_id)}}
    with user_context(str(user_id)):
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": payload.message}]},
                config,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"对话失败: {exc}") from exc

    sql_query = result.get("sql_query", "")
    validation_passed = result.get("validation_passed", True)

    # 执行SQL查询
    data, columns, error, truncated = _execute_sql_for_user(user_id, sql_query)

    # 生成回答文本
    answer = _extract_assistant_text(result)
    if not error and data:
        suffix = f"（已按上限返回前 {SQL_ASSISTANT_QUERY_MAX_ROWS} 条）" if truncated else ""
        answer = f"查询完成，共返回 {len(data)} 条记录{suffix}。"
    elif not error and sql_query:
        answer = "查询完成，未查询到符合条件的数据。"
    elif error:
        answer = f"查询执行失败：{error}"

    review = _review_answer_satisfaction(
        user_message=payload.message,
        sql_query=sql_query,
        answer=answer,
        data=data,
        columns=columns,
        error=error,
        truncated=truncated,
    )
    retry_count = 0

    if (
        SQL_ASSISTANT_AUTO_RETRY_ON_REVIEW_FAIL
        and not review["passed"]
        and _is_retryable_review_failure(sql_query, error)
    ):
        retry_count = 1
        retry_message = (
            f"{payload.message}\n\n"
            "上一次结果未通过最终答案审查，请重新生成 SQL。\n"
            f"审查反馈：{review['feedback']}\n"
            f"修正建议：{review['suggestion']}"
        )
        with user_context(str(user_id)):
            try:
                result = agent.invoke(
                    {"messages": [{"role": "user", "content": retry_message}]},
                    config,
                )
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"纠错重试失败: {exc}") from exc

        sql_query = result.get("sql_query", "")
        validation_passed = result.get("validation_passed", validation_passed)
        data, columns, error, truncated = _execute_sql_for_user(user_id, sql_query)
        answer = _extract_assistant_text(result)
        if not error and data:
            suffix = f"（已按上限返回前 {SQL_ASSISTANT_QUERY_MAX_ROWS} 条）" if truncated else ""
            answer = f"查询完成，共返回 {len(data)} 条记录{suffix}。"
        elif not error and sql_query:
            answer = "查询完成，未查询到符合条件的数据。"
        elif error:
            answer = f"查询执行失败：{error}"

        review = _review_answer_satisfaction(
            user_message=payload.message,
            sql_query=sql_query,
            answer=answer,
            data=data,
            columns=columns,
            error=error,
            truncated=truncated,
        )

    validation_passed = validation_passed and bool(review["passed"])
    if review["feedback"] and not review["passed"]:
        answer = f"{answer}\n\n自检未通过：{review['feedback']}"
        if review["suggestion"]:
            answer += f"\n建议：{review['suggestion']}"

    response = ChatResponse(
        thread_id=client_thread_id,
        answer=answer,
        sql_query=sql_query,
        validation_passed=validation_passed,
        data=data,
        columns=columns,
        row_count=len(data),
        row_limit=SQL_ASSISTANT_QUERY_MAX_ROWS,
        truncated=truncated,
        response_ms=round((time.perf_counter() - started) * 1000),
        execution_error=error,
        review_passed=bool(review["passed"]),
        review_feedback=review["feedback"],
        review_suggestion=review["suggestion"],
        retry_count=retry_count,
    )
    _append_chat_snapshot(
        user_id=user_id,
        thread_id=client_thread_id,
        user_message=payload.message,
        response=response,
    )
    return response


# ── Chat History ────────────────────────────────────────────────────────

_INTERNAL_PREFIXES_TUPLE = ("[规划]", "[技能加载]", "[校验]", "[Schema]")


def _is_internal_message(msg: Any) -> bool:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return any(content.startswith(p) for p in _INTERNAL_PREFIXES_TUPLE)
    return False


@app.get("/api/chat/threads")
def list_threads(user_id: int = Depends(get_current_user_id)) -> dict[str, Any]:
    with get_db_session() as db:
        rows = db.execute(
            select(ChatThread)
            .where(ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.desc(), ChatThread.id.desc())
        ).scalars().all()
        if rows:
            return {
                "items": [
                    {
                        "thread_id": row.thread_id,
                        "first_message": row.title,
                        "message_count": len(row.messages),
                        "created_at": row.created_at.isoformat() if row.created_at else "",
                    }
                    for row in rows
                ]
            }

    agent = get_agent()
    checkpointer = agent.checkpointer
    prefix = f"{user_id}:"

    threads: list[dict[str, Any]] = []
    seen: set[str] = set()

    for checkpoint_tuple in checkpointer.list(None):
        thread_id = checkpoint_tuple.config.get("configurable", {}).get("thread_id", "")
        if not thread_id.startswith(prefix):
            continue
        client_tid = thread_id[len(prefix):]
        if client_tid in seen:
            continue
        seen.add(client_tid)

        cv = checkpoint_tuple.checkpoint.get("channel_values", {})
        messages = cv.get("messages", [])
        user_messages = [m for m in messages if getattr(m, "type", "") == "human"]
        first_msg = user_messages[0].content if user_messages else ""
        if isinstance(first_msg, list):
            first_msg = " ".join(
                item.get("text", "") for item in first_msg if isinstance(item, dict)
            )

        ts = checkpoint_tuple.checkpoint.get("ts", "")
        threads.append({
            "thread_id": client_tid,
            "first_message": first_msg[:100] if isinstance(first_msg, str) else "",
            "message_count": len(messages),
            "created_at": ts,
        })

    threads.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return {"items": threads}


@app.get("/api/chat/threads/{thread_id}")
def get_thread_messages(
    thread_id: str,
    user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    with get_db_session() as db:
        thread = db.execute(
            select(ChatThread).where(
                ChatThread.user_id == user_id,
                ChatThread.thread_id == thread_id,
            )
        ).scalar_one_or_none()
        if thread:
            messages = sorted(thread.messages, key=lambda item: item.id)
            return {
                "thread_id": thread_id,
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "sql_query": msg.sql_query,
                        "validation_passed": msg.validation_passed,
                        "data": msg.data or [],
                        "columns": msg.columns or [],
                        "row_count": msg.row_count,
                        "row_limit": msg.row_limit,
                        "truncated": msg.truncated,
                        "response_ms": msg.response_ms,
                        "execution_error": msg.execution_error,
                    }
                    for msg in messages
                ],
            }

    agent = get_agent()
    checkpointer = agent.checkpointer
    checkpoint_thread_id = f"{user_id}:{thread_id}"
    config = {"configurable": {"thread_id": checkpoint_thread_id}}

    checkpoint_tuple = checkpointer.get_tuple(config)
    if not checkpoint_tuple:
        raise HTTPException(status_code=404, detail="对话不存在。")

    cv = checkpoint_tuple.checkpoint.get("channel_values", {})
    messages = cv.get("messages", [])

    result: list[dict[str, Any]] = []
    for msg in messages:
        role = getattr(msg, "type", "")
        content = getattr(msg, "content", "")
        if _is_internal_message(msg):
            continue
        if role == "human":
            text = content if isinstance(content, str) else ""
            if isinstance(content, list):
                text = " ".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            result.append({"role": "user", "content": text})
        elif role == "ai":
            text = content if isinstance(content, str) else ""
            if isinstance(content, list):
                text = " ".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            sql = _extract_sql_from_text(text)
            item: dict[str, Any] = {"role": "bot", "content": text, "sql_query": sql}
            if sql:
                data, columns, error, truncated = _execute_sql_for_user(user_id, sql)
                if error:
                    item["execution_error"] = error
                else:
                    item["data"] = data
                    item["columns"] = columns
                    item["row_count"] = len(data)
                    item["row_limit"] = SQL_ASSISTANT_QUERY_MAX_ROWS
                    item["truncated"] = truncated
                    if data:
                        suffix = f"（已按上限返回前 {SQL_ASSISTANT_QUERY_MAX_ROWS} 条）" if truncated else ""
                        item["content"] = f"查询完成，共返回 {len(data)} 条记录{suffix}。"
                    else:
                        item["content"] = "查询完成，未查询到符合条件的数据。"
            result.append(item)

    return {"thread_id": thread_id, "messages": result}


@app.get("/api/chat/suggestions")
def get_chat_suggestions(user_id: int = Depends(get_current_user_id)) -> dict[str, Any]:
    return {"items": _build_suggested_questions(user_id)}


# ── Frontend Static Files ───────────────────────────────────────────────

@app.get("/")
async def serve_index():
    """Serve the main HTML file"""
    return FileResponse(FRONTEND_DIR / "index.html")

# Mount static files at the end to avoid conflicts with API routes
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")
