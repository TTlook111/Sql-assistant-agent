from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sql_assistant_agent.config.config import SKILL_FILES_DIR
from sql_assistant_agent.db.models import Skill
from sql_assistant_agent.services.markdown_skills import parse_skills_markdown


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"[_\-/]+", " ", str(text).lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _tokenize_text(text: str) -> list[str]:
    return [token for token in re.split(r"\s+", text) if len(token) >= 2]


def _skill_to_dict(skill: Skill, user_id: int) -> dict[str, Any]:
    return {
        "id": f"user:{skill.id}",
        "user_id": user_id,
        "name": skill.name,
        "description": skill.description or "",
        "tags": skill.tags or [],
        "content": skill.content or "",
        "source_file": skill.source_file or "",
        "created_at": skill.created_at.isoformat() if skill.created_at else "",
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else "",
    }


class MySQLSkillStore:
    def __init__(self) -> None:
        self._builtin_dir = SKILL_FILES_DIR / "builtin"
        self._builtin_dir.mkdir(parents=True, exist_ok=True)
        self._uploads_dir = SKILL_FILES_DIR / "users"
        self._uploads_dir.mkdir(parents=True, exist_ok=True)

    def _read_builtin_skills(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for file_path in sorted(self._builtin_dir.glob("*.md")):
            try:
                text = file_path.read_text(encoding="utf-8")
            except OSError:
                continue
            for parsed in parse_skills_markdown(text, default_source_file=""):
                name = str(parsed.get("name") or "").strip()
                if not name:
                    continue
                items.append({
                    "id": f"builtin:{name.lower().replace(' ', '_')}",
                    "user_id": "__builtin__",
                    "name": name,
                    "description": parsed.get("description", ""),
                    "tags": parsed.get("tags", []),
                    "content": parsed.get("content", ""),
                    "source_file": "",
                    "created_at": "",
                    "updated_at": "",
                })
        return items

    def list_skills(self, db: Session, user_id: int) -> list[dict[str, Any]]:
        rows = db.execute(
            select(Skill).where(Skill.user_id == user_id).order_by(Skill.updated_at.desc())
        ).scalars().all()
        user_skills = [_skill_to_dict(r, user_id) for r in rows]
        return [*user_skills, *self._read_builtin_skills()]

    def list_effective_skills(self, db: Session, user_id: int) -> tuple[list[dict[str, Any]], str]:
        rows = db.execute(
            select(Skill)
            .where(Skill.user_id == user_id, Skill.source_file != "")
            .order_by(Skill.updated_at.desc())
        ).scalars().all()
        uploaded = [_skill_to_dict(r, user_id) for r in rows]
        if uploaded:
            return uploaded, "uploaded"
        return self.list_skills(db, user_id), "builtin_fallback"

    def get_skill_by_id(self, db: Session, user_id: int, skill_id: str) -> dict[str, Any] | None:
        if skill_id.startswith("builtin:"):
            for item in self._read_builtin_skills():
                if item["id"] == skill_id:
                    return item
            return None
        try:
            real_id = int(skill_id.replace("user:", ""))
        except (ValueError, TypeError):
            return None
        row = db.get(Skill, real_id)
        if row and row.user_id == user_id:
            return _skill_to_dict(row, user_id)
        return None

    def upsert_skill(
        self,
        db: Session,
        user_id: int,
        *,
        name: str,
        description: str,
        tags: list[str],
        content: str,
        source_file: str = "",
    ) -> dict[str, Any]:
        existing = db.execute(
            select(Skill).where(
                Skill.user_id == user_id,
                func_lower(Skill.name) == name.strip().lower(),
            )
        ).scalar_one_or_none()

        if existing:
            existing.name = name.strip()
            existing.description = description.strip()
            existing.tags = [t.strip() for t in tags if t.strip()]
            existing.content = content.strip()
            existing.source_file = source_file.strip()
            db.flush()
            return _skill_to_dict(existing, user_id)

        new_skill = Skill(
            user_id=user_id,
            name=name.strip(),
            description=description.strip(),
            tags=[t.strip() for t in tags if t.strip()],
            content=content.strip(),
            source_file=source_file.strip(),
        )
        db.add(new_skill)
        db.flush()
        return _skill_to_dict(new_skill, user_id)

    def delete_skill(self, db: Session, user_id: int, skill_id: str) -> bool:
        if skill_id.startswith("builtin:"):
            return False
        try:
            real_id = int(skill_id.replace("user:", ""))
        except (ValueError, TypeError):
            return False
        row = db.get(Skill, real_id)
        if not row or row.user_id != user_id:
            return False
        db.delete(row)
        db.flush()
        return True

    def delete_skills(self, db: Session, user_id: int, skill_ids: list[str]) -> int:
        real_ids = []
        for sid in skill_ids:
            if sid.startswith("builtin:"):
                continue
            try:
                real_ids.append(int(sid.replace("user:", "")))
            except (ValueError, TypeError):
                continue
        if not real_ids:
            return 0
        rows = db.execute(
            select(Skill).where(Skill.id.in_(real_ids), Skill.user_id == user_id)
        ).scalars().all()
        for row in rows:
            db.delete(row)
        db.flush()
        return len(rows)

    def delete_skills_by_source_file(self, db: Session, user_id: int, source_file: str) -> int:
        rows = db.execute(
            select(Skill).where(
                Skill.user_id == user_id,
                Skill.source_file == source_file.strip(),
            )
        ).scalars().all()
        for row in rows:
            db.delete(row)
        db.flush()
        return len(rows)

    def import_skills_from_markdown(
        self, db: Session, user_id: int, text: str, source_file: str
    ) -> int:
        normalized_source = source_file.strip()
        parsed_list = parse_skills_markdown(text, default_source_file=normalized_source)
        if not parsed_list:
            return 0
        self.delete_skills_by_source_file(db, user_id, normalized_source)
        count = 0
        for item in parsed_list:
            self.upsert_skill(
                db,
                user_id,
                name=item["name"],
                description=item["description"],
                tags=item["tags"],
                content=item["content"],
                source_file=normalized_source,
            )
            count += 1
        return count

    def search_relevant_skills(
        self, db: Session, user_id: int, query: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        skills, _ = self.list_effective_skills(db, user_id)
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
        ranked.sort(key=lambda item: (-item[0], item[1].get("updated_at", "")))
        if ranked:
            return [item[1] for item in ranked[:limit]]
        return skills[:limit]

    def find_best_skill_match(
        self, db: Session, user_id: int, skill_name: str
    ) -> dict[str, Any] | None:
        skills, _ = self.list_effective_skills(db, user_id)
        exact = next(
            (s for s in skills if str(s.get("name", "")).lower() == skill_name.lower()),
            None,
        )
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

    @staticmethod
    def _score_skill(
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

    def save_uploaded_markdown(
        self, user_id: int, filename: str, content: str
    ) -> Path:
        uploads_dir = self._uploads_dir / str(user_id)
        uploads_dir.mkdir(parents=True, exist_ok=True)
        target = uploads_dir / filename
        target.write_text(content, encoding="utf-8")
        return target


def func_lower(column):
    from sqlalchemy import func
    return func.lower(column)
