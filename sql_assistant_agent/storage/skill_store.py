from __future__ import annotations

import json
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    level TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, name)
                );
                """
            )

    def ensure_seed_for_user(self, user_id: str) -> None:
        with self._get_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM skills WHERE user_id = ?",
                (user_id,),
            ).fetchone()["count"]
            if count > 0:
                return
            now = utc_now_iso()
            for seed in SKILLS:
                conn.execute(
                    """
                    INSERT INTO skills(id, user_id, name, description, level, tags_json, content, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        seed["name"],
                        seed["description"],
                        "中级",
                        json.dumps(["内置"], ensure_ascii=False),
                        seed["content"].strip(),
                        now,
                        now,
                    ),
                )

    def list_skills(self, user_id: str) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, name, description, level, tags_json, content, created_at, updated_at
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
                SELECT id, user_id, name, description, level, tags_json, content, created_at, updated_at
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
                SELECT id, user_id, name, description, level, tags_json, content, created_at, updated_at
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
        level: str,
        tags: list[str],
        content: str,
    ) -> dict[str, Any]:
        existing = self.get_skill_by_name(user_id, name)
        now = utc_now_iso()
        with self._get_conn() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE skills
                    SET description = ?, level = ?, tags_json = ?, content = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (description, level, json.dumps(tags, ensure_ascii=False), content, now, existing["id"]),
                )
                return self.get_skill_by_id(user_id, existing["id"])  # type: ignore[return-value]

            skill_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO skills(id, user_id, name, description, level, tags_json, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_id,
                    user_id,
                    name,
                    description,
                    level,
                    json.dumps(tags, ensure_ascii=False),
                    content,
                    now,
                    now,
                ),
            )
            return self.get_skill_by_id(user_id, skill_id)  # type: ignore[return-value]

    def update_skill(
        self,
        user_id: str,
        skill_id: str,
        *,
        name: str,
        description: str,
        level: str,
        tags: list[str],
        content: str,
    ) -> dict[str, Any] | None:
        current = self.get_skill_by_id(user_id, skill_id)
        if not current:
            return None
        now = utc_now_iso()
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE skills
                SET name = ?, description = ?, level = ?, tags_json = ?, content = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    name,
                    description,
                    level,
                    json.dumps(tags, ensure_ascii=False),
                    content,
                    now,
                    skill_id,
                    user_id,
                ),
            )
        return self.get_skill_by_id(user_id, skill_id)

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

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "description": row["description"],
            "level": row["level"],
            "tags": json.loads(row["tags_json"]),
            "content": row["content"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
