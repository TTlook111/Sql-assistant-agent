from langchain.tools import tool

from sql_assistant_agent.config.config import SKILL_DB_PATH
from sql_assistant_agent.runtime.context import get_current_user_id
from sql_assistant_agent.storage.skill_store import SkillStore

_store = SkillStore(SKILL_DB_PATH)


@tool
def load_skill(skill_name: str) -> str:
    """将指定技能的完整内容加载到智能体上下文。

    当你需要处理某一类请求的详细规则时使用该工具。
    它会返回该技能的完整说明、策略与处理规范。

    Args:
        skill_name: 要加载的技能名称（例如 "sales_analytics", "inventory_management"）
    """
    user_id = get_current_user_id()
    _store.ensure_seed_for_user(user_id)
    skill = _store.get_skill_by_name(user_id, skill_name)
    if skill:
        return f"已加载技能：{skill_name}\n\n{skill['content']}"

    available = ", ".join(s["name"] for s in _store.list_skills(user_id))
    return f"未找到技能 '{skill_name}'。当前用户可用技能：{available or '无'}"

