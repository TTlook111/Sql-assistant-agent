from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
from sql_assistant_agent.config.config import PROJECT_ROOT, SKILL_FILES_DIR
from sql_assistant_agent.db.connection import DatabaseConfig, get_db_manager
from sql_assistant_agent.db.init_db import get_db, get_db_session
from sql_assistant_agent.db.models import User
from sql_assistant_agent.db.schema import (
    format_schema_markdown,
    get_tables_summary,
    introspect_schema,
)
from sql_assistant_agent.runtime.context import user_context
from sql_assistant_agent.storage.mysql_skill_store import MySQLSkillStore

app = FastAPI(title="SQL Assistant Agent API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

skill_store = MySQLSkillStore()
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
    execution_error: str = ""


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


def _safe_upload_filename(filename: str) -> str:
    raw = Path(filename or "skills.md").name.strip() or "skills.md"
    safe = "".join(ch if (ch.isalnum() or ch in {".", "_", "-"}) else "_" for ch in raw)
    return safe[:120] or "skills.md"


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
        conn.close()

        # 过滤掉系统数据库
        system_dbs = {'information_schema', 'mysql', 'performance_schema', 'sys'}
        user_databases = [db for db in databases if db not in system_dbs]

        return {"databases": user_databases}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"获取数据库列表失败: {exc}") from exc


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

def _execute_sql_for_user(user_id: int, sql_query: str) -> tuple[list[dict[str, Any]], list[str], str]:
    """执行SQL查询并返回结果"""
    if not sql_query or not sql_query.strip():
        return [], [], ""

    # 清理SQL（移除可能的markdown代码块标记）
    sql_query = sql_query.strip()
    if sql_query.startswith("```sql"):
        sql_query = sql_query[6:]
    if sql_query.startswith("```"):
        sql_query = sql_query[3:]
    if sql_query.endswith("```"):
        sql_query = sql_query[:-3]
    sql_query = sql_query.strip()

    db_manager = get_db_manager()
    if not db_manager.is_connected(user_id):
        return [], [], "数据库未连接"

    conn = db_manager.get_raw_connection(user_id)
    if not conn:
        return [], [], "获取数据库连接失败"

    try:
        import pymysql.cursors
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(sql_query)

        # 获取列名
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        # 获取数据
        rows = cursor.fetchall()
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

        return data, columns, ""
    except Exception as e:
        return [], [], str(e)
    finally:
        conn.close()


@app.post("/api/chat")
def chat(
    payload: ChatPayload,
    user_id: int = Depends(get_current_user_id),
) -> ChatResponse:
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
    data, columns, error = _execute_sql_for_user(user_id, sql_query)

    # 生成回答文本
    answer = _extract_assistant_text(result)
    if not error and data:
        answer = f"查询完成，共返回 {len(data)} 条记录。"
    elif error:
        answer = f"查询执行失败：{error}"

    return ChatResponse(
        thread_id=client_thread_id,
        answer=answer,
        sql_query=sql_query,
        validation_passed=validation_passed,
        data=data,
        columns=columns,
        row_count=len(data),
        execution_error=error,
    )


# ── Chat History ────────────────────────────────────────────────────────

_INTERNAL_PREFIXES_TUPLE = ("[规划]", "[技能加载]", "[校验]", "[Schema]")


def _is_internal_message(msg: Any) -> bool:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return any(content.startswith(p) for p in _INTERNAL_PREFIXES_TUPLE)
    return False


@app.get("/api/chat/threads")
def list_threads(user_id: int = Depends(get_current_user_id)) -> dict[str, Any]:
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
    agent = get_agent()
    checkpointer = agent.checkpointer
    checkpoint_thread_id = f"{user_id}:{thread_id}"
    config = {"configurable": {"thread_id": checkpoint_thread_id}}

    checkpoint_tuple = checkpointer.get_tuple(config)
    if not checkpoint_tuple:
        raise HTTPException(status_code=404, detail="对话不存在。")

    cv = checkpoint_tuple.checkpoint.get("channel_values", {})
    messages = cv.get("messages", [])

    result: list[dict[str, str]] = []
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
            sql = ""
            if "```sql" in text:
                import re
                m = re.search(r"```sql\s*\n?([\s\S]*?)\n?\s*```", text)
                if m:
                    sql = m.group(1).strip()
            result.append({"role": "bot", "content": text, "sql_query": sql})

    return {"thread_id": thread_id, "messages": result}


# ── Frontend Static Files ───────────────────────────────────────────────

@app.get("/")
async def serve_index():
    """Serve the main HTML file"""
    return FileResponse(FRONTEND_DIR / "index.html")

# Mount static files at the end to avoid conflicts with API routes
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")
