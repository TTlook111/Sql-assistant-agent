from __future__ import annotations

import re


def export_skills_markdown(skills: list[dict]) -> str:
    sections: list[str] = ["# skills.md", ""]
    for skill in skills:
        tags = ", ".join(skill.get("tags", [])) or "通用"
        source = (skill.get("source_file") or "").strip()
        sections.extend(
            [
                f"## Skill: {skill['name']}",
                f"Description: {skill.get('description', '')}",
                f"Tags: {tags}",
                *( [f"Source: {source}"] if source else [] ),
                "",
                "### Content",
                skill.get("content", "").strip() or skill.get("description", ""),
                "",
            ]
        )
    return "\n".join(sections).rstrip() + "\n"


def parse_skills_markdown(text: str, *, default_source_file: str = "") -> list[dict]:
    pattern = re.compile(r"^##\s+Skill:\s*(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        stripped = text.strip()
        if not stripped:
            return []
        # 仅包含文档标题（如 "# skills.md"）时，视为“空技能文件”。
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return []
        if all(line.startswith("#") for line in lines):
            return []
        return [
            {
                "name": "skills",
                "description": "导入的技能文档",
                "tags": [],
                "content": stripped,
                "source_file": default_source_file,
            }
        ]

    items: list[dict] = []
    for idx, match in enumerate(matches):
        name = match.group(1).strip()
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()

        desc_match = re.search(r"^Description:\s*(.*)$", body, flags=re.MULTILINE)
        tags_match = re.search(r"^Tags:\s*(.*)$", body, flags=re.MULTILINE)
        content_match = re.search(r"^###\s+Content\s*$([\s\S]*)", body, flags=re.MULTILINE)

        description = (desc_match.group(1).strip() if desc_match else "") or f"{name} 相关技能"
        tags_text = tags_match.group(1).strip() if tags_match else ""
        tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()] if tags_text else []
        # 安全约束：忽略文档内部 Source 字段，来源路径仅信任后端传入值。
        source_file = default_source_file
        content = content_match.group(1).strip() if content_match else body

        items.append(
            {
                "name": name,
                "description": description,
                "tags": tags,
                "content": content.strip(),
                "source_file": source_file,
            }
        )
    return items
