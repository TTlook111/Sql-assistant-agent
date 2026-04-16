from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from sql_assistant_agent.agent.builder import build_sql_assistant_agent
from sql_assistant_agent.config.config import PROJECT_ROOT, SKILL_DB_PATH, SKILL_FILES_DIR
from sql_assistant_agent.runtime.context import user_context
from sql_assistant_agent.services.markdown_skills import export_skills_markdown
from sql_assistant_agent.storage.skill_store import SkillStore

app = FastAPI(title="SQL Assistant Agent API", version="0.1.0")
store = SkillStore(SKILL_DB_PATH)
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


def _safe_upload_filename(filename: str) -> str:
    raw = Path(filename or "skills.md").name.strip() or "skills.md"
    safe = "".join(ch if (ch.isalnum() or ch in {".", "_", "-"}) else "_" for ch in raw)
    return safe[:120] or "skills.md"


def _build_upload_target_path(user_id: str, filename: str) -> Path:
    user_dir = SKILL_FILES_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / f"{uuid4().hex}_{_safe_upload_filename(filename)}"


def _build_skill_description_from_markdown(text: str) -> str:
    compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return (compact[:200] or "上传的技能文档").strip()


def _unlink_source_file(path_value: str) -> None:
    if not path_value:
        return
    base_dir = SKILL_FILES_DIR.resolve()
    try:
        target = Path(path_value).resolve()
    except OSError:
        return
    if target == base_dir or base_dir not in target.parents:
        return
    try:
        target.unlink(missing_ok=True)
    except OSError:
        return


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
        _unlink_source_file(source_file)
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
        _unlink_source_file(source_file)
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
    target_path = _build_upload_target_path(user_id, file.filename)
    target_path.write_bytes(content_bytes)
    text = content_bytes.decode("utf-8", errors="ignore")
    content = text.strip()
    if not content:
        _unlink_source_file(str(target_path))
        raise HTTPException(status_code=400, detail="文件内容为空")

    skill_name = Path(file.filename).stem.strip() or "skills"
    store.upsert_skill(
        user_id,
        name=skill_name,
        description=_build_skill_description_from_markdown(content),
        tags=[],
        content=content,
        source_file=str(target_path),
    )
    return {"imported_count": 1, "items": store.list_skills(user_id)}


@app.get("/api/skills/export.md")
def export_skills(user_id: str = Depends(get_user_id)) -> PlainTextResponse:
    _ensure_user(user_id)
    md = export_skills_markdown(store.list_skills(user_id))
    headers = {"Content-Disposition": 'attachment; filename="skills.md"'}
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8", headers=headers)


@app.post("/api/chat")
def chat(payload: ChatPayload, user_id: str = Depends(get_user_id)) -> dict[str, str]:
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
    return {"thread_id": client_thread_id, "answer": _extract_assistant_text(result)}


@app.get("/")
def frontend_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/styles.css")
def frontend_style() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "styles.css")


@app.get("/app.js")
def frontend_script() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js")
