from langchain.tools import tool

from sql_assistant_agent.config.config import SKILL_DB_PATH
from sql_assistant_agent.runtime.context import get_current_user_id
from sql_assistant_agent.storage.skill_store import SkillStore

_store = SkillStore(SKILL_DB_PATH)


@tool
def load_skill(skill_name: str) -> str:
    """将指定技能的完整内容加载到智能体上下文。

    Args:
        skill_name: 要加载的技能名称（例如 "sales_analytics", "inventory_management"）。

    Returns:
        成功时返回已加载技能名称和该技能完整 content；
        未命中时返回当前生效来源及可用技能列表。
    """
    user_id = get_current_user_id()
    _store.ensure_seed_for_user(user_id)
    skill = _store.find_best_skill_match(user_id, skill_name)
    if skill:
        return f"已加载技能：{skill['name']}\n\n{skill['content']}"

    effective_skills, mode = _store.list_effective_skills(user_id)
    mode_text = "用户上传 skills" if mode == "uploaded" else "内置 skills（回退）"
    available = ", ".join(s["name"] for s in effective_skills)
    return f"未找到技能 '{skill_name}'。当前生效来源：{mode_text}。可用技能：{available or '无'}"

