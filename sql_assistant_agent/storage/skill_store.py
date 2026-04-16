from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sql_assistant_agent.domain.skills import SKILLS


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class SkillStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_file TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, name)
                );
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(skills);").fetchall()}
            target_columns = {
                "id",
                "user_id",
                "name",
                "description",
                "tags_json",
                "content",
                "source_file",
                "created_at",
                "updated_at",
            }
            if columns != target_columns:
                source_file_expr = "source_file" if "source_file" in columns else "''"
                conn.execute(
                    """
                    CREATE TABLE skills_v2 (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        tags_json TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source_file TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(user_id, name)
                    );
                    """
                )
                conn.execute(
                    f"""
                    INSERT INTO skills_v2(id, user_id, name, description, tags_json, content, source_file, created_at, updated_at)
                    SELECT id, user_id, name, description, tags_json, content, {source_file_expr}, created_at, updated_at
                    FROM skills;
                    """
                )
                conn.execute("DROP TABLE skills;")
                conn.execute("ALTER TABLE skills_v2 RENAME TO skills;")

    def ensure_seed_for_user(self, user_id: str) -> None:
        with self._get_conn() as conn:
            now = utc_now_iso()
            for seed in SKILLS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO skills(
                        id, user_id, name, description, tags_json, content, source_file, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        seed["name"],
                        seed["description"],
                        json.dumps(seed.get("tags", ["内置"]), ensure_ascii=False),
                        seed["content"].strip(),
                        "",
                        now,
                        now,
                    ),
                )

    def list_skills(self, user_id: str) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, name, description, tags_json, content, source_file, created_at, updated_at
                FROM skills
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_skill_by_name(self, user_id: str, skill_name: str) -> dict[str, Any] | None:
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, name, description, tags_json, content, source_file, created_at, updated_at
                FROM skills
                WHERE user_id = ? AND lower(name) = lower(?)
                """,
                (user_id, skill_name),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_skill_by_id(self, user_id: str, skill_id: str) -> dict[str, Any] | None:
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, name, description, tags_json, content, source_file, created_at, updated_at
                FROM skills
                WHERE user_id = ? AND id = ?
                """,
                (user_id, skill_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

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
        existing = self.get_skill_by_name(user_id, name)
        now = utc_now_iso()
        with self._get_conn() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE skills
                    SET description = ?, tags_json = ?, content = ?, source_file = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (description, json.dumps(tags, ensure_ascii=False), content, source_file, now, existing["id"]),
                )
                return self.get_skill_by_id(user_id, existing["id"])  # type: ignore[return-value]

            skill_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO skills(id, user_id, name, description, tags_json, content, source_file, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_id,
                    user_id,
                    name,
                    description,
                    json.dumps(tags, ensure_ascii=False),
                    content,
                    source_file,
                    now,
                    now,
                ),
            )
            return self.get_skill_by_id(user_id, skill_id)  # type: ignore[return-value]

    def delete_skill(self, user_id: str, skill_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM skills WHERE user_id = ? AND id = ?",
                (user_id, skill_id),
            )
            return cur.rowcount > 0

    def delete_skills(self, user_id: str, skill_ids: list[str]) -> int:
        if not skill_ids:
            return 0
        placeholders = ",".join("?" for _ in skill_ids)
        with self._get_conn() as conn:
            cur = conn.execute(
                f"DELETE FROM skills WHERE user_id = ? AND id IN ({placeholders})",
                [user_id, *skill_ids],
            )
            return cur.rowcount

    def delete_skills_by_source_file(self, user_id: str, source_file: str) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM skills WHERE user_id = ? AND source_file = ?",
                (user_id, source_file),
            )
            return cur.rowcount

    def search_relevant_skills(self, user_id: str, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """按 query 从技能库中检索最相关的技能。"""
        skills = self.list_skills(user_id)
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
        """先精确匹配，再做轻量模糊匹配。"""
        exact = self.get_skill_by_name(user_id, skill_name)
        if exact:
            return exact

        query_norm = _normalize_text(skill_name)
        if not query_norm:
            return None
        tokens = _tokenize_text(query_norm)
        best: tuple[int, dict[str, Any]] | None = None
        for skill in self.list_skills(user_id):
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

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "description": row["description"],
            "tags": json.loads(row["tags_json"]),
            "content": row["content"],
            "source_file": row["source_file"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"[_\-/]+", " ", str(text).lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _tokenize_text(text: str) -> list[str]:
    return [token for token in re.split(r"\s+", text) if len(token) >= 2]
