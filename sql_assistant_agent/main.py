from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from sql_assistant_agent.agent.builder import build_sql_assistant_agent
from sql_assistant_agent.config.config import PROJECT_ROOT, SKILL_DB_PATH
from sql_assistant_agent.runtime.context import user_context
from sql_assistant_agent.services.markdown_skills import export_skills_markdown, parse_skills_markdown
from sql_assistant_agent.storage.skill_store import SkillStore

app = FastAPI(title="SQL Assistant Agent API", version="0.1.0")
store = SkillStore(SKILL_DB_PATH)
FRONTEND_DIR = PROJECT_ROOT / "frontend"


class SkillCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    level: str = Field(min_length=1, max_length=20)
    tags: list[str] = Field(default_factory=list)
    content: str = Field(min_length=1)


class SkillUpdatePayload(SkillCreatePayload):
    pass


class BatchDeletePayload(BaseModel):
    ids: list[str] = Field(default_factory=list)


class ChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = None


def get_user_id(x_user_id: Annotated[str | None, Header()] = None) -> str:
    user_id = (x_user_id or "").strip() or "demo-user"
    if len(user_id) > 64:
        raise HTTPException(status_code=400, detail="x-user-id 长度不能超过 64")
    return user_id


@lru_cache(maxsize=1)
def get_agent():
    return build_sql_assistant_agent()


def _ensure_user(user_id: str) -> None:
    store.ensure_seed_for_user(user_id)


def _extract_assistant_text(result: dict[str, Any]) -> str:
    messages = result.get("messages") or []
    for msg in reversed(messages):
        role = getattr(msg, "type", "") or getattr(msg, "role", "")
        if role in {"ai", "assistant"}:
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_items = [item.get("text", "") for item in content if isinstance(item, dict)]
                return "\n".join([item for item in text_items if item]).strip()
    return "未获取到助手回复。"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
        level=payload.level.strip(),
        tags=[tag.strip() for tag in payload.tags if tag.strip()],
        content=payload.content.strip(),
    )
    return {"item": item}


@app.patch("/api/skills/{skill_id}")
def update_skill(skill_id: str, payload: SkillUpdatePayload, user_id: str = Depends(get_user_id)) -> dict[str, Any]:
    _ensure_user(user_id)
    item = store.update_skill(
        user_id,
        skill_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        level=payload.level.strip(),
        tags=[tag.strip() for tag in payload.tags if tag.strip()],
        content=payload.content.strip(),
    )
    if not item:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"item": item}


@app.delete("/api/skills/{skill_id}")
def delete_skill(skill_id: str, user_id: str = Depends(get_user_id)) -> dict[str, bool]:
    _ensure_user(user_id)
    deleted = store.delete_skill(user_id, skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True}


@app.post("/api/skills/batch-delete")
def delete_skills(payload: BatchDeletePayload, user_id: str = Depends(get_user_id)) -> dict[str, int]:
    _ensure_user(user_id)
    deleted_count = store.delete_skills(user_id, payload.ids)
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
    parsed = parse_skills_markdown(text)
    if not parsed:
        raise HTTPException(status_code=400, detail="未识别到有效技能定义")
    for item in parsed:
        store.upsert_skill(
            user_id,
            name=item.name,
            description=item.description,
            level=item.level,
            tags=item.tags,
            content=item.content,
        )
    return {"imported_count": len(parsed), "items": store.list_skills(user_id)}


@app.get("/api/skills/export.md")
def export_skills(user_id: str = Depends(get_user_id)) -> PlainTextResponse:
    _ensure_user(user_id)
    md = export_skills_markdown(store.list_skills(user_id))
    headers = {"Content-Disposition": 'attachment; filename="skills.md"'}
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8", headers=headers)


@app.post("/api/chat")
def chat(payload: ChatPayload, user_id: str = Depends(get_user_id)) -> dict[str, str]:
    _ensure_user(user_id)
    try:
        agent = get_agent()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    thread_id = payload.thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
    with user_context(user_id):
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": payload.message}]},
                config,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"对话失败: {exc}") from exc
    return {"thread_id": thread_id, "answer": _extract_assistant_text(result)}


@app.get("/")
def frontend_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/styles.css")
def frontend_style() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "styles.css")


@app.get("/app.js")
def frontend_script() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js")
