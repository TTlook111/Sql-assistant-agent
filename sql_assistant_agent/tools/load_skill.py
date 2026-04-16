from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from sql_assistant_agent.config.config import SKILL_DB_PATH
from sql_assistant_agent.runtime.context import get_current_user_id
from sql_assistant_agent.storage.skill_store import SkillStore

_store = SkillStore(SKILL_DB_PATH)


@tool
def load_skill(skill_name: str, runtime: ToolRuntime) -> Command:
    """将指定技能的完整内容加载到智能体上下文。

    Args:
        skill_name: 要加载的技能名称（例如 "sales_analytics", "inventory_management"）。

    Returns:
        一个 `Command` 对象：
        - 成功时写入工具消息并更新 `skills_loaded` 状态；
        - 未命中时写入错误消息并返回可用技能列表。
    """
    user_id = get_current_user_id()
    _store.ensure_seed_for_user(user_id)
    skill = _store.find_best_skill_match(user_id, skill_name)
    if skill:
        loaded = runtime.state.get("skills_loaded", [])
        if not isinstance(loaded, list):
            loaded = []
        updated_loaded = list(dict.fromkeys([*loaded, skill["name"]]))
        skill_content = f"已加载技能：{skill['name']}\n\n{skill['content']}"
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=skill_content,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
                "skills_loaded": updated_loaded,
            }
        )

    effective_skills, mode = _store.list_effective_skills(user_id)
    mode_text = "用户上传 skills" if mode == "uploaded" else "内置 skills（回退）"
    available = ", ".join(s["name"] for s in effective_skills)
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=(
                        f"未找到技能“{skill_name}”。"
                        f"当前生效来源：{mode_text}。"
                        f"可用技能：{available or '无'}"
                    ),
                    tool_call_id=runtime.tool_call_id,
                )
            ]
        }
    )


@tool
def write_sql_query(
    query: str,
    vertical: str,
    runtime: ToolRuntime,
) -> str:
    """为指定业务域编写并校验 SQL 查询。

    使用本工具前，必须先通过 `load_skill` 加载对应业务域技能，
    以确保 SQL 依据正确的表结构和业务口径。

    Args:
        query: 待编写或校验的 SQL 查询语句。
        vertical: 业务域名称（例如 "sales_analytics"、"inventory_management"）。
    """
    skills_loaded = runtime.state.get("skills_loaded", [])
    if not isinstance(skills_loaded, list):
        skills_loaded = []

    if vertical not in skills_loaded:
        return (
            f"错误：请先加载“{vertical}”技能，再编写该业务域的 SQL。"
            f"你可以先调用 `load_skill('{vertical}')`。"
        )

    return (
        f"{vertical} 业务域 SQL：\n\n"
        f"```sql\n{query}\n```\n\n"
        f"已按“{vertical}”技能口径完成校验，可用于后续执行。"
    )

