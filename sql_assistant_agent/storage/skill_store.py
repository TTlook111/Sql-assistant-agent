from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sql_assistant_agent.config.config import SKILL_FILES_DIR
from sql_assistant_agent.domain.skills import SKILLS
from sql_assistant_agent.services.markdown_skills import export_skills_markdown, parse_skills_markdown


def utc_now_iso() -> str:
    """获取当前 UTC 时间的 ISO 字符串。"""
    return datetime.now(tz=timezone.utc).isoformat()


class SkillStore:
    """文件系统版技能存储。

    - 内置技能：`agent/skills/builtin/*.md`（每个技能一个文档）
    - 用户技能：`agent/skills/users/<user_id>/skills.md`
    """

    def __init__(self, db_path: Path) -> None:
        _ = db_path  # 兼容历史调用参数，当前实现不再使用数据库。
        self.root_dir = SKILL_FILES_DIR
        self.builtin_dir = self.root_dir / "builtin"
        self.users_dir = self.root_dir / "users"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.builtin_dir.mkdir(parents=True, exist_ok=True)
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self._init_builtin_skills()

    def _init_builtin_skills(self) -> None:
        """初始化内置技能文件（每个技能一个 md）。"""
        for seed in SKILLS:
            skill_name = seed["name"].strip()
            filename = f"{_slugify(skill_name)}.md"
            target = self.builtin_dir / filename
            if target.exists():
                continue
            payload = [
                {
                    "name": skill_name,
                    "description": seed["description"],
                    "tags": seed.get("tags", ["内置"]),
                    "content": seed["content"].strip(),
                    "source_file": "",
                }
            ]
            target.write_text(export_skills_markdown(payload), encoding="utf-8")

    def ensure_seed_for_user(self, user_id: str) -> None:
        """为用户准备 skills.md，并确保内置技能文件存在。"""
        self._init_builtin_skills()
        user_file = self._user_file(user_id)
        user_file.parent.mkdir(parents=True, exist_ok=True)
        if not user_file.exists():
            user_file.write_text("# skills.md\n", encoding="utf-8")

    def list_skills(self, user_id: str) -> list[dict[str, Any]]:
        """查询并返回用户可见的全部技能（用户 + 内置）。"""
        merged = [*self._read_user_skills(user_id), *self._read_builtin_skills()]
        return sorted(merged, key=lambda item: item.get("updated_at", ""), reverse=True)

    def list_uploaded_skills(self, user_id: str) -> list[dict[str, Any]]:
        """仅返回用户上传技能（source_file 非空）。"""
        user_skills = self._read_user_skills(user_id)
        uploaded = [item for item in user_skills if (item.get("source_file") or "").strip()]
        return sorted(uploaded, key=lambda item: item.get("updated_at", ""), reverse=True)

    def list_effective_skills(self, user_id: str) -> tuple[list[dict[str, Any]], str]:
        """返回当前 Agent 生效技能集合与来源模式。"""
        uploaded = self.list_uploaded_skills(user_id)
        if uploaded:
            return uploaded, "uploaded"
        return self.list_skills(user_id), "builtin_fallback"

    def get_skill_by_name(self, user_id: str, skill_name: str) -> dict[str, Any] | None:
        """按技能名称（不区分大小写）查询技能。"""
        norm_name = skill_name.strip().lower()
        for item in self.list_skills(user_id):
            if str(item.get("name", "")).strip().lower() == norm_name:
                return item
        return None

    def get_skill_by_id(self, user_id: str, skill_id: str) -> dict[str, Any] | None:
        """按技能 ID 查询技能。"""
        for item in self.list_skills(user_id):
            if item.get("id") == skill_id:
                return item
        return None

    def upsert_skill(
        self,
        user_id: str,
        *,
        name: str,
        description: str,
        tags: list[str],
        content: str,
        source_file: str = "",
    ) -> dict[str, Any]:
        """按名称更新或插入用户技能。"""
        now = utc_now_iso()
        current = self._read_user_skills(user_id)
        target_name = name.strip().lower()
        updated = False

        for idx, item in enumerate(current):
            if str(item.get("name", "")).strip().lower() != target_name:
                continue
            current[idx] = {
                **item,
                "name": name.strip(),
                "description": description.strip(),
                "tags": [tag.strip() for tag in tags if str(tag).strip()],
                "content": content.strip(),
                "source_file": source_file.strip(),
                "updated_at": now,
            }
            updated = True
            break

        if not updated:
            current.append(
                {
                    "id": f"user:{uuid.uuid4().hex}",
                    "user_id": user_id,
                    "name": name.strip(),
                    "description": description.strip(),
                    "tags": [tag.strip() for tag in tags if str(tag).strip()],
                    "content": content.strip(),
                    "source_file": source_file.strip(),
                    "created_at": now,
                    "updated_at": now,
                }
            )

        self._write_user_skills(user_id, current)
        item = self.get_skill_by_name(user_id, name)
        if not item:
            raise ValueError("写入技能文件失败")
        return item

    def delete_skill(self, user_id: str, skill_id: str) -> bool:
        """删除单个用户技能。"""
        current = self._read_user_skills(user_id)
        remain = [item for item in current if item.get("id") != skill_id]
        if len(remain) == len(current):
            return False
        self._write_user_skills(user_id, remain)
        return True

    def delete_skills(self, user_id: str, skill_ids: list[str]) -> int:
        """批量删除多个用户技能。"""
        deleted = 0
        for skill_id in skill_ids:
            if self.delete_skill(user_id, skill_id):
                deleted += 1
        return deleted

    def delete_skills_by_source_file(self, user_id: str, source_file: str) -> int:
        """按来源文件路径删除用户技能。"""
        current = self._read_user_skills(user_id)
        remain = [item for item in current if (item.get("source_file") or "").strip() != source_file]
        deleted = len(current) - len(remain)
        if deleted > 0:
            self._write_user_skills(user_id, remain)
        return deleted

    def import_skills_from_markdown(self, user_id: str, text: str, source_file: str) -> int:
        """从 markdown 文档批量导入技能段。"""
        parsed = parse_skills_markdown(text, default_source_file=source_file.strip())
        if not parsed:
            return 0
        count = 0
        for item in parsed:
            self.upsert_skill(
                user_id,
                name=item["name"],
                description=item["description"],
                tags=item["tags"],
                content=item["content"],
                source_file=item.get("source_file", source_file),
            )
            count += 1
        return count

    def search_relevant_skills(self, user_id: str, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """按用户问题检索最相关技能 Top-K。"""
        skills, _ = self.list_effective_skills(user_id)
        if not skills:
            return []
        query_norm = _normalize_text(query)
        if not query_norm:
            return skills[:limit]
        tokens = _tokenize_text(query_norm)
        ranked: list[tuple[int, dict[str, Any]]] = []
        for skill in skills:
            score = self._score_skill(skill, query_norm, tokens)
            if score > 0:
                ranked.append((score, skill))
        ranked.sort(key=lambda item: (-item[0], item[1].get("updated_at", "")), reverse=False)
        if ranked:
            return [item[1] for item in ranked[:limit]]
        return skills[:limit]

    def find_best_skill_match(self, user_id: str, skill_name: str) -> dict[str, Any] | None:
        """按技能名匹配最佳技能，先精确再模糊。"""
        skills, _ = self.list_effective_skills(user_id)
        exact = next((item for item in skills if str(item.get("name", "")).lower() == skill_name.lower()), None)
        if exact:
            return exact
        query_norm = _normalize_text(skill_name)
        if not query_norm:
            return None
        tokens = _tokenize_text(query_norm)
        best: tuple[int, dict[str, Any]] | None = None
        for skill in skills:
            score = self._score_skill(skill, query_norm, tokens, content_weight=1)
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, skill)
        return best[1] if best else None

    def _score_skill(
        self,
        skill: dict[str, Any],
        query_norm: str,
        tokens: list[str],
        *,
        content_weight: int = 2,
    ) -> int:
        name_text = _normalize_text(skill.get("name", ""))
        desc_text = _normalize_text(skill.get("description", ""))
        tags_text = _normalize_text(" ".join(skill.get("tags", [])))
        content_text = _normalize_text(skill.get("content", ""))
        score = 0
        if query_norm == name_text:
            score += 120
        if query_norm in name_text:
            score += 80
        if query_norm in desc_text:
            score += 35
        if query_norm in tags_text:
            score += 30
        if query_norm in content_text:
            score += 8
        for token in tokens:
            if token in name_text:
                score += 25
            if token in desc_text:
                score += 12
            if token in tags_text:
                score += 10
            if token in content_text:
                score += content_weight
        return score

    def _user_file(self, user_id: str) -> Path:
        return self.users_dir / user_id / "skills.md"

    def _read_builtin_skills(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for file_path in sorted(self.builtin_dir.glob("*.md")):
            items.extend(
                self._read_skills_file(
                    file_path,
                    user_id="__builtin__",
                    id_prefix="builtin",
                    default_source_file="",
                )
            )
        return items

    def _read_user_skills(self, user_id: str) -> list[dict[str, Any]]:
        return self._read_skills_file(
            self._user_file(user_id),
            user_id=user_id,
            id_prefix="user",
            default_source_file="",
        )

    def _read_skills_file(
        self,
        file_path: Path,
        *,
        user_id: str,
        id_prefix: str,
        default_source_file: str,
    ) -> list[dict[str, Any]]:
        if not file_path.exists():
            return []
        try:
            text = file_path.read_text(encoding="utf-8")
        except OSError:
            return []
        parsed = parse_skills_markdown(text, default_source_file=default_source_file)
        try:
            file_updated_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            file_updated_at = ""
        items: list[dict[str, Any]] = []
        for item in parsed:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            items.append(
                {
                    "id": f"{id_prefix}:{_slugify(name)}",
                    "user_id": user_id,
                    "name": name,
                    "description": str(item.get("description") or ""),
                    "tags": list(item.get("tags") or []),
                    "content": str(item.get("content") or ""),
                    "source_file": str(item.get("source_file") or ""),
                    "created_at": file_updated_at,
                    "updated_at": file_updated_at,
                }
            )
        return items

    def _write_user_skills(self, user_id: str, items: list[dict[str, Any]]) -> None:
        user_file = self._user_file(user_id)
        user_file.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "name": item["name"],
                "description": item.get("description", ""),
                "tags": item.get("tags", []),
                "content": item.get("content", ""),
                "source_file": item.get("source_file", ""),
            }
            for item in items
        ]
        user_file.write_text(export_skills_markdown(payload), encoding="utf-8")


def _slugify(text: str) -> str:
    normalized = _normalize_text(text).replace(" ", "_")
    return normalized or "skill"


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"[_\-/]+", " ", str(text).lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _tokenize_text(text: str) -> list[str]:
    return [token for token in re.split(r"\s+", text) if len(token) >= 2]
