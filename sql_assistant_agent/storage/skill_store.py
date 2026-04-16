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
    """获取当前 UTC 时间的 ISO 字符串。

    Returns:
        当前 UTC 时间，格式为 ISO-8601 字符串。
    """
    return datetime.now(tz=timezone.utc).isoformat()


class SkillStore:
    def __init__(self, db_path: Path) -> None:
        """初始化技能存储对象并确保数据库结构可用。

        Args:
            db_path: SQLite 数据库文件路径。

        Returns:
            None
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """创建一个 SQLite 连接并设置行工厂为字典式访问。

        Returns:
            配置好 row_factory 的数据库连接对象。
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """初始化 skills 表结构，并在字段不一致时自动迁移。

        Returns:
            None
        """
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
        """为指定用户补齐内置技能种子数据（幂等）。

        Args:
            user_id: 用户唯一标识。

        Returns:
            None
        """
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
        """查询并返回用户的全部技能（含内置和上传）。

        Args:
            user_id: 用户唯一标识。

        Returns:
            技能字典列表，按更新时间倒序。
        """
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

    def list_uploaded_skills(self, user_id: str) -> list[dict[str, Any]]:
        """仅返回用户上传的技能（source_file 非空）。

        Args:
            user_id: 用户唯一标识。

        Returns:
            上传技能列表，按更新时间倒序。
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, name, description, tags_json, content, source_file, created_at, updated_at
                FROM skills
                WHERE user_id = ? AND source_file != ''
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_effective_skills(self, user_id: str) -> tuple[list[dict[str, Any]], str]:
        """返回当前会被 Agent 使用的技能集合与来源模式。

        策略：
        1) 若存在上传技能，仅使用上传技能；
        2) 若不存在上传技能，回退到内置技能集合。

        Args:
            user_id: 用户唯一标识。

        Returns:
            二元组 (skills, mode)。
            - skills: 生效技能列表。
            - mode: 来源模式，"uploaded" 或 "builtin_fallback"。
        """
        uploaded = self.list_uploaded_skills(user_id)
        if uploaded:
            return uploaded, "uploaded"
        return self.list_skills(user_id), "builtin_fallback"

    def get_skill_by_name(self, user_id: str, skill_name: str) -> dict[str, Any] | None:
        """按技能名称（不区分大小写）查询单个技能。

        Args:
            user_id: 用户唯一标识。
            skill_name: 技能名称。

        Returns:
            命中时返回技能字典；未命中返回 None。
        """
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
        """按技能 ID 查询单个技能。

        Args:
            user_id: 用户唯一标识。
            skill_id: 技能主键 ID。

        Returns:
            命中时返回技能字典；未命中返回 None。
        """
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
        """按名称执行技能更新或插入（upsert）。

        Args:
            user_id: 用户唯一标识。
            name: 技能名称（同一用户下唯一）。
            description: 技能简介。
            tags: 技能标签列表。
            content: 技能全文内容。
            source_file: 来源文件路径，内置技能通常为空字符串。

        Returns:
            插入或更新后的最新技能字典。
        """
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
        """删除单个技能。

        Args:
            user_id: 用户唯一标识。
            skill_id: 技能主键 ID。

        Returns:
            删除成功返回 True；未命中返回 False。
        """
        with self._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM skills WHERE user_id = ? AND id = ?",
                (user_id, skill_id),
            )
            return cur.rowcount > 0

    def delete_skills(self, user_id: str, skill_ids: list[str]) -> int:
        """批量删除多个技能。

        Args:
            user_id: 用户唯一标识。
            skill_ids: 待删除技能 ID 列表。

        Returns:
            实际删除条数。
        """
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
        """按来源文件路径删除技能（用于上传文档联动删除）。

        Args:
            user_id: 用户唯一标识。
            source_file: skills 文档绝对路径字符串。

        Returns:
            实际删除条数。
        """
        with self._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM skills WHERE user_id = ? AND source_file = ?",
                (user_id, source_file),
            )
            return cur.rowcount

    def search_relevant_skills(self, user_id: str, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """按用户问题检索最相关的技能 Top-K。

        Args:
            user_id: 用户唯一标识。
            query: 用户问题文本。
            limit: 返回的最大技能数量。

        Returns:
            相关技能列表；若 query 为空则返回前 limit 条；若无匹配则回退前 limit 条。
        """
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
        """按技能名匹配最佳技能，先精确再模糊。

        Args:
            user_id: 用户唯一标识。
            skill_name: 模型传入的技能名或近似文本。

        Returns:
            命中时返回最优技能字典；未命中返回 None。
        """
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
        """计算 query 与某个技能的相关性分数。

        Args:
            skill: 候选技能字典。
            query_norm: 归一化后的查询文本。
            tokens: 查询切词结果。
            content_weight: 内容字段命中的单词权重。

        Returns:
            非负整数分数，分数越高表示越相关。
        """
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
        """将 SQLite Row 转换为业务层技能字典。

        Args:
            row: 数据库查询结果行。

        Returns:
            统一结构的技能字典。
        """
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
    """归一化文本，用于检索与匹配。

    Args:
        text: 原始文本。

    Returns:
        小写、去多余空白、并将 `_-/` 统一为空格后的文本。
    """
    normalized = re.sub(r"[_\-/]+", " ", str(text).lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _tokenize_text(text: str) -> list[str]:
    """按空白切词并过滤过短 token。

    Args:
        text: 归一化后的文本。

    Returns:
        长度大于等于 2 的 token 列表。
    """
    return [token for token in re.split(r"\s+", text) if len(token) >= 2]
