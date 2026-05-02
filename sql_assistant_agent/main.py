from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from sql_assistant_agent.agent.builder import build_sql_assistant_agent
from sql_assistant_agent.config.config import PROJECT_ROOT, SKILL_FILES_DIR
from sql_assistant_agent.db.connection import DatabaseConfig, get_db_manager
from sql_assistant_agent.db.schema import get_tables_summary, introspect_schema, format_schema_markdown
from sql_assistant_agent.runtime.context import user_context
from sql_assistant_agent.storage.skill_store import SkillStore

app = FastAPI(title="SQL Assistant Agent API", version="0.1.0")
store = SkillStore()
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SKILL_FILES_DIR.mkdir(parents=True, exist_ok=True)


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


def get_user_id(x_user_id: Annotated[str | None, Header()] = None) -> str:
    user_id = (x_user_id or "").strip() or "demo-user"
    if len(user_id) > 64:
        raise HTTPException(status_code=400, detail="x-user-id 长度不能超过 64")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", user_id):
        raise HTTPException(status_code=400, detail="x-user-id 仅支持字母、数字、下划线和短横线")
    return user_id


@lru_cache(maxsize=1)
def get_agent():
    return build_sql_assistant_agent()


def _ensure_user(user_id: str) -> None:
    store.ensure_seed_for_user(user_id)


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


def _unlink_source_file(user_id: str, path_value: str) -> None:
    if not path_value:
        return
    uploads_dir = (SKILL_FILES_DIR / "users" / user_id / "uploads").resolve()
    try:
        target = Path(path_value).resolve()
    except OSError:
        return
    if target == uploads_dir or uploads_dir not in target.parents:
        return
    try:
        target.unlink(missing_ok=True)
    except OSError:
        return


class DatabaseConnectPayload(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=3306, ge=1, le=65535)
    user: str = Field(min_length=1)
    password: str = ""
    database: str = Field(min_length=1)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/database/connect")
def database_connect(
    payload: DatabaseConnectPayload,
    user_id: str = Depends(get_user_id),
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
def database_disconnect(user_id: str = Depends(get_user_id)) -> dict[str, Any]:
    db_manager = get_db_manager()
    disconnected = db_manager.disconnect(user_id)
    return {"disconnected": disconnected}


@app.get("/api/database/status")
def database_status(user_id: str = Depends(get_user_id)) -> dict[str, Any]:
    db_manager = get_db_manager()
    return db_manager.get_status(user_id)


@app.get("/api/skills")
def list_skills(user_id: str = Depends(get_user_id)) -> dict[str, Any]:
    _ensure_user(user_id)
    return {"items": store.list_skills(user_id)}


@app.post("/api/skills")
def create_skill(payload: SkillCreatePayload, user_id: str = Depends(get_user_id)) -> dict[str, Any]:
    _ensure_user(user_id)
    item = store.upsert_skill(
        user_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        tags=[tag.strip() for tag in payload.tags if tag.strip()],
        content=payload.content.strip(),
    )
    return {"item": item}


@app.delete("/api/skills/{skill_id}")
def delete_skill(skill_id: str, user_id: str = Depends(get_user_id)) -> dict[str, bool]:
    _ensure_user(user_id)
    current = store.get_skill_by_id(user_id, skill_id)
    if not current:
        raise HTTPException(status_code=404, detail="技能不存在")
    source_file = (current.get("source_file") or "").strip()
    if source_file:
        store.delete_skills_by_source_file(user_id, source_file)
        _unlink_source_file(user_id, source_file)
    else:
        store.delete_skill(user_id, skill_id)
    return {"ok": True}


@app.post("/api/skills/batch-delete")
def delete_skills(payload: BatchDeletePayload, user_id: str = Depends(get_user_id)) -> dict[str, int]:
    _ensure_user(user_id)
    source_files: set[str] = set()
    plain_skill_ids: list[str] = []
    for skill_id in payload.ids:
        current = store.get_skill_by_id(user_id, skill_id)
        if not current:
            continue
        source_file = (current.get("source_file") or "").strip()
        if source_file:
            source_files.add(source_file)
        else:
            plain_skill_ids.append(skill_id)

    deleted_count = 0
    if plain_skill_ids:
        deleted_count += store.delete_skills(user_id, plain_skill_ids)
    for source_file in source_files:
        deleted_count += store.delete_skills_by_source_file(user_id, source_file)
        _unlink_source_file(user_id, source_file)
    return {"deleted_count": deleted_count}


@app.post("/api/skills/upload")
async def upload_skills(
    user_id: str = Depends(get_user_id),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    _ensure_user(user_id)
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="仅支持上传 .md 文件")
    content_bytes = await file.read()
    text = content_bytes.decode("utf-8", errors="ignore")
    content = text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    safe_name = _safe_upload_filename(file.filename)
    saved_file = store.save_uploaded_markdown(user_id, safe_name, content)
    source = str(saved_file)
    imported_count = store.import_skills_from_markdown(user_id, content, source)
    if imported_count <= 0:
        _unlink_source_file(user_id, source)
        raise HTTPException(status_code=400, detail="未在文档中识别到可导入的技能段")
    return {"imported_count": imported_count, "items": store.list_skills(user_id)}


@app.post("/api/chat")
def chat(payload: ChatPayload, user_id: str = Depends(get_user_id)) -> ChatResponse:
    _ensure_user(user_id)
    agent = get_agent()
    client_thread_id = payload.thread_id or str(uuid4())
    checkpoint_thread_id = f"{user_id}:{client_thread_id}"
    config = {"configurable": {"thread_id": checkpoint_thread_id, "user_id": user_id}}
    with user_context(user_id):
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": payload.message}]},
                config,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"对话失败: {exc}") from exc
    return ChatResponse(
        thread_id=client_thread_id,
        answer=_extract_assistant_text(result),
        sql_query=result.get("sql_query", ""),
        validation_passed=result.get("validation_passed", True),
    )


@app.get("/")
def frontend_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/styles.css")
def frontend_style() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "styles.css")


@app.get("/app.js")
def frontend_script() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js")
