from __future__ import annotations

def export_skills_markdown(skills: list[dict]) -> str:
    sections: list[str] = ["# skills.md", ""]
    for skill in skills:
        tags = ", ".join(skill.get("tags", [])) or "通用"
        sections.extend(
            [
                f"## Skill: {skill['name']}",
                f"Description: {skill.get('description', '')}",
                f"Tags: {tags}",
                "",
                "### Content",
                skill.get("content", "").strip() or skill.get("description", ""),
                "",
            ]
        )
    return "\n".join(sections).rstrip() + "\n"
