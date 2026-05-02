from __future__ import annotations

import json
import re
from typing import Any

from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_community.chat_models.tongyi import ChatTongyi

from sql_assistant_agent.agent.prompts import (
    PLANNER_SYSTEM_PROMPT,
    SQL_GENERATOR_SYSTEM_PROMPT,
    VALIDATOR_SYSTEM_PROMPT,
)
from sql_assistant_agent.agent.state import AgentGraphState, PlannerDecision
from sql_assistant_agent.config.config import DASHSCOPE_API_KEY
from sql_assistant_agent.runtime.context import get_current_user_id
from sql_assistant_agent.storage.skill_store import SkillStore

_store = SkillStore()
_model: ChatTongyi | None = None


def _get_model() -> ChatTongyi:
    global _model
    if _model is None:
        _model = ChatTongyi(model="qwen3-max", api_key=DASHSCOPE_API_KEY)
    return _model


def _build_skills_summary(user_id: str, user_query: str) -> str:
    skills = _store.search_relevant_skills(user_id, user_query, limit=5)
    if not skills:
        return "- 暂无可用技能。"
    lines: list[str] = []
    for item in skills:
        summary = (item.get("description") or "").strip()
        tags = ", ".join(item.get("tags", [])[:4])
        tags_text = f"（tags: {tags}）" if tags else ""
        lines.append(f"- **{item['name']}**: {summary}{tags_text}")
    return "\n".join(lines)


def _extract_latest_user_query(state: AgentGraphState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                ).strip()
    return ""


def _parse_json_from_text(text: str) -> dict[str, Any] | None:
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", text)
    raw = match.group(1).strip() if match else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_sql_from_text(text: str) -> str:
    match = re.search(r"```sql\s*\n?([\s\S]*?)\n?\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*\n?([\s\S]*?)\n?\s*```", text)
    if match:
        return match.group(1).strip()
    return text.strip()


def planner_node(state: AgentGraphState) -> dict[str, Any]:
    user_id = get_current_user_id()
    user_query = _extract_latest_user_query(state)
    skills_summary = _build_skills_summary(user_id, user_query)

    system_prompt = PLANNER_SYSTEM_PROMPT.format(skills_summary=skills_summary)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_query)]

    model = _get_model()
    response = model.invoke(messages)
    response_text = response.content if isinstance(response.content, str) else ""

    parsed = _parse_json_from_text(response_text)
    if parsed and "action" in parsed:
        decision: PlannerDecision = {
            "action": parsed["action"],
            "skill_name": parsed.get("skill_name", ""),
            "reasoning": parsed.get("reasoning", response_text),
        }
    else:
        decision = {
            "action": "load_skill",
            "skill_name": "",
            "reasoning": response_text,
        }

    return {
        "planner_decision": decision,
        "messages": [AIMessage(content=f"[规划] {decision['reasoning']}")],
    }


def skill_loader_node(state: AgentGraphState) -> dict[str, Any]:
    user_id = get_current_user_id()
    decision = state.get("planner_decision") or {}
    skill_name = (decision.get("skill_name") or "").strip()

    if not skill_name:
        user_query = _extract_latest_user_query(state)
        skills = _store.search_relevant_skills(user_id, user_query, limit=1)
        if skills:
            skill_name = skills[0]["name"]

    if not skill_name:
        return {
            "skill_content": "",
            "messages": [AIMessage(content="[技能加载] 未找到匹配的技能，将直接生成 SQL。")],
        }

    skill = _store.find_best_skill_match(user_id, skill_name)
    if not skill:
        return {
            "skill_content": "",
            "messages": [AIMessage(content=f"[技能加载] 未找到技能「{skill_name}」，将直接生成 SQL。")],
        }

    return {
        "skill_content": skill["content"],
        "messages": [AIMessage(content=f"[技能加载] 已加载技能「{skill['name']}」。")],
    }


def sql_generator_node(state: AgentGraphState) -> dict[str, Any]:
    user_id = get_current_user_id()
    user_query = _extract_latest_user_query(state)
    skill_content = state.get("skill_content", "")

    if not skill_content:
        skills_summary = _build_skills_summary(user_id, user_query)
        skill_content = f"当前无已加载技能，以下是可用技能摘要：\n{skills_summary}"

    validation_feedback = state.get("validation_feedback", "")
    retry_context = ""
    if validation_feedback:
        retry_context = f"\n\n## 上次校验反馈（请据此修正 SQL）\n{validation_feedback}"

    system_prompt = SQL_GENERATOR_SYSTEM_PROMPT.format(skill_content=skill_content) + retry_context
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_query)]

    model = _get_model()
    response = model.invoke(messages)
    response_text = response.content if isinstance(response.content, str) else ""

    sql_query = _extract_sql_from_text(response_text)

    return {
        "sql_query": sql_query,
        "validation_feedback": "",
        "messages": [AIMessage(content=response_text)],
    }


def validator_node(state: AgentGraphState) -> dict[str, Any]:
    sql_query = state.get("sql_query", "")
    skill_content = state.get("skill_content", "")

    if not sql_query:
        return {"validation_passed": True, "validation_feedback": ""}

    system_prompt = VALIDATOR_SYSTEM_PROMPT.format(
        skill_content=skill_content or "无技能文档",
        sql_query=sql_query,
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content="请校验上述 SQL。")]

    model = _get_model()
    response = model.invoke(messages)
    response_text = response.content if isinstance(response.content, str) else ""

    parsed = _parse_json_from_text(response_text)
    current_retry = state.get("retry_count", 0)

    if parsed and "passed" in parsed:
        passed = bool(parsed["passed"])
        issues = parsed.get("issues", [])
        suggestion = parsed.get("suggestion", "")
        feedback = ""
        if not passed:
            feedback = "问题：" + "；".join(issues) if issues else ""
            if suggestion:
                feedback += f"\n建议：{suggestion}"
        return {
            "validation_passed": passed,
            "validation_feedback": feedback,
            "retry_count": current_retry + 1 if not passed else current_retry,
            "messages": [AIMessage(content=f"[校验] {'通过' if passed else '未通过：' + feedback}")],
        }

    return {
        "validation_passed": True,
        "validation_feedback": "",
        "messages": [AIMessage(content="[校验] 校验完成。")],
    }


def route_after_planner(state: AgentGraphState) -> str:
    decision = state.get("planner_decision") or {}
    action = decision.get("action", "load_skill")
    if action == "direct_sql":
        return "sql_generator"
    return "skill_loader"


def route_after_validator(state: AgentGraphState) -> str:
    if state.get("validation_passed", True):
        return "__end__"
    retry_count = state.get("retry_count", 0)
    if retry_count >= 2:
        return "__end__"
    return "sql_generator"
