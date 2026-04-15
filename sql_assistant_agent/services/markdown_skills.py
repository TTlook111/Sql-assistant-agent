from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class ParsedSkill:
    name: str
    description: str
    level: str
    tags: list[str]
    content: str


def _normalize_level(value: str) -> str:
    mapping = {
        "beginner": "初级",
        "intermediate": "中级",
        "advanced": "高级",
        "expert": "专家",
    }
    raw = value.strip().lower()
    return mapping.get(raw, value.strip() or "中级")


def _split_tags(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,，]", value) if item.strip()]


def parse_skills_markdown(markdown: str) -> list[ParsedSkill]:
    blocks = [b.strip() for b in re.split(r"\n(?=##\s+)", markdown) if b.strip().startswith("## ")]
    parsed: list[ParsedSkill] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        first_line = re.sub(r"^##\s+", "", lines[0]).strip()
        name = re.sub(r"^(skill|技能)\s*[:：]\s*", "", first_line, flags=re.IGNORECASE).strip()
        if not name:
            continue

        description = ""
        level = "中级"
        tags: list[str] = []
        content_lines: list[str] = []

        for line in lines[1:]:
            clean = re.sub(r"^[-*]\s*", "", line)
            if re.match(r"^(description|desc|描述)\s*[:：]", clean, flags=re.IGNORECASE):
                description = re.sub(r"^(description|desc|描述)\s*[:：]\s*", "", clean, flags=re.IGNORECASE).strip()
                content_lines.append(clean)
                continue
            if re.match(r"^(level|熟练度)\s*[:：]", clean, flags=re.IGNORECASE):
                level = _normalize_level(
                    re.sub(r"^(level|熟练度)\s*[:：]\s*", "", clean, flags=re.IGNORECASE).strip()
                )
                content_lines.append(clean)
                continue
            if re.match(r"^(tags?|标签)\s*[:：]", clean, flags=re.IGNORECASE):
                tags = _split_tags(re.sub(r"^(tags?|标签)\s*[:：]\s*", "", clean, flags=re.IGNORECASE))
                content_lines.append(clean)
                continue
            content_lines.append(line)

        if not description:
            fallback = [line for line in lines[1:] if not line.startswith("```") and not line.startswith("|")]
            description = " ".join(fallback).strip()[:200] if fallback else f"{name} 技能"

        content = "\n".join(content_lines).strip() or description
        parsed.append(
            ParsedSkill(
                name=name,
                description=description,
                level=level,
                tags=tags,
                content=content,
            )
        )

    return parsed


def export_skills_markdown(skills: list[dict]) -> str:
    sections: list[str] = ["# skills.md", ""]
    for skill in skills:
        tags = ", ".join(skill.get("tags", [])) or "通用"
        sections.extend(
            [
                f"## Skill: {skill['name']}",
                f"Description: {skill.get('description', '')}",
                f"Level: {skill.get('level', '中级')}",
                f"Tags: {tags}",
                "",
                "### Content",
                skill.get("content", "").strip() or skill.get("description", ""),
                "",
            ]
        )
    return "\n".join(sections).rstrip() + "\n"
