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
from sql_assistant_agent.config.config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_MODEL,
    SQL_ASSISTANT_USE_LLM_PLANNER,
    SQL_ASSISTANT_VALIDATE_SQL,
)
from sql_assistant_agent.db.connection import get_db_manager
from sql_assistant_agent.db.init_db import get_db_session
from sql_assistant_agent.db.schema import format_schema_markdown, introspect_schema
from sql_assistant_agent.runtime.context import get_current_user_id
from sql_assistant_agent.storage.mysql_skill_store import MySQLSkillStore

_store = MySQLSkillStore()
_model = ChatTongyi(model=DASHSCOPE_MODEL, api_key=DASHSCOPE_API_KEY)


def _get_user_id_int() -> int:
    raw = get_current_user_id()
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def _build_skills_summary(user_id: int, user_query: str) -> str:
    with get_db_session() as db:
        skills = _store.search_relevant_skills(db, user_id, user_query, limit=5)
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
    user_id = _get_user_id_int()
    user_query = _extract_latest_user_query(state)
    skills_summary = _build_skills_summary(user_id, user_query)

    if not SQL_ASSISTANT_USE_LLM_PLANNER:
        lowered = user_query.strip().lower()
        is_chat_only = bool(
            lowered
            and len(lowered) <= 12
            and any(word in lowered for word in ("你好", "hello", "hi", "谢谢", "thanks"))
        )
        if is_chat_only:
            decision: PlannerDecision = {
                "action": "reply",
                "skill_name": "",
                "reasoning": "simple greeting",
                "reply_text": "你好，我可以帮你把自然语言问题转换成 SQL 并查询数据库。",
            }
            return {"planner_decision": decision, "messages": [AIMessage(content=decision["reply_text"])]}

        first_skill = ""
        for line in skills_summary.splitlines():
            match = re.match(r"- \*\*(.*?)\*\*", line)
            if match:
                first_skill = match.group(1).strip()
                break
        decision = {
            "action": "load_skill" if first_skill else "direct_sql",
            "skill_name": first_skill,
            "reasoning": "fast local routing",
            "reply_text": "",
        }
        return {
            "planner_decision": decision,
            "messages": [AIMessage(content=f"[规划] {decision['reasoning']}")],
        }

    system_prompt = PLANNER_SYSTEM_PROMPT.format(skills_summary=skills_summary)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_query)]

    response = _model.invoke(messages)
    response_text = response.content if isinstance(response.content, str) else ""

    parsed = _parse_json_from_text(response_text)
    if parsed and "action" in parsed:
        action = parsed["action"]
        if action not in ("load_skill", "direct_sql", "reply"):
            action = "load_skill"
        decision: PlannerDecision = {
            "action": action,
            "skill_name": parsed.get("skill_name", ""),
            "reasoning": parsed.get("reasoning", response_text),
            "reply_text": parsed.get("reply_text", ""),
        }
    else:
        decision = {
            "action": "reply",
            "skill_name": "",
            "reasoning": "无法解析规划结果，直接回复用户。",
            "reply_text": response_text,
        }

    if decision["action"] == "reply":
        reply_text = decision.get("reply_text") or decision["reasoning"]
        return {
            "planner_decision": decision,
            "messages": [AIMessage(content=reply_text)],
        }

    return {
        "planner_decision": decision,
        "messages": [AIMessage(content=f"[规划] {decision['reasoning']}")],
    }


def schema_loader_node(state: AgentGraphState) -> dict[str, Any]:
    user_id = _get_user_id_int()
    db_manager = get_db_manager()

    if not db_manager.is_connected(user_id):
        return {
            "db_schema": "",
            "db_connected": False,
            "messages": [AIMessage(content="[Schema] 数据库未连接，将使用技能文档生成 SQL。")],
        }

    cached = db_manager.get_schema_cache(user_id)
    if cached:
        return {
            "db_schema": cached,
            "db_connected": True,
            "messages": [],
        }

    conn = db_manager.get_raw_connection(user_id)
    if not conn:
        return {
            "db_schema": "",
            "db_connected": False,
            "messages": [AIMessage(content="[Schema] 获取数据库连接失败。")],
        }

    try:
        info = db_manager.get_connection_info(user_id)
        database = info.config.database if info else ""
        schema = introspect_schema(conn, database)
        schema_md = format_schema_markdown(schema)
        tables_summary = schema.get("tables", [])
        db_manager.set_schema_cache(user_id, schema_md, tables_summary)
        table_names = ", ".join(t["name"] for t in tables_summary[:10])
        return {
            "db_schema": schema_md,
            "db_connected": True,
            "messages": [AIMessage(content=f"[Schema] 已加载 {len(tables_summary)} 张表：{table_names}")],
        }
    finally:
        conn.close()


def skill_loader_node(state: AgentGraphState) -> dict[str, Any]:
    user_id = _get_user_id_int()
    decision = state.get("planner_decision") or {}
    skill_name = (decision.get("skill_name") or "").strip()

    with get_db_session() as db:
        if not skill_name:
            user_query = _extract_latest_user_query(state)
            skills = _store.search_relevant_skills(db, user_id, user_query, limit=1)
            if skills:
                skill_name = skills[0]["name"]

        if not skill_name:
            return {
                "skill_content": "",
                "messages": [AIMessage(content="[技能加载] 未找到匹配的技能，将直接生成 SQL。")],
            }

        skill = _store.find_best_skill_match(db, user_id, skill_name)

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
    user_id = _get_user_id_int()
    user_query = _extract_latest_user_query(state)
    skill_content = state.get("skill_content", "")
    db_schema = state.get("db_schema", "")

    if not skill_content:
        skills_summary = _build_skills_summary(user_id, user_query)
        skill_content = f"当前无已加载技能，以下是可用技能摘要：\n{skills_summary}"

    if not db_schema:
        db_schema = "未连接数据库，无 Schema 信息。请依据技能文档中的表结构生成 SQL。"

    validation_feedback = state.get("validation_feedback", "")
    retry_context = ""
    if validation_feedback:
        retry_context = f"\n\n## 上次校验反馈（请据此修正 SQL）\n{validation_feedback}"

    system_prompt = SQL_GENERATOR_SYSTEM_PROMPT.format(
        skill_content=skill_content,
        db_schema=db_schema,
    ) + retry_context
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_query)]

    response = _model.invoke(messages)
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
    db_schema = state.get("db_schema", "")

    if not sql_query:
        return {"validation_passed": True, "validation_feedback": ""}

    if not SQL_ASSISTANT_VALIDATE_SQL:
        return {
            "validation_passed": True,
            "validation_feedback": "",
            "messages": [AIMessage(content="[校验] 已跳过大模型校验以提升响应速度。")],
        }

    if not db_schema:
        db_schema = "未连接数据库，无 Schema 信息。"

    system_prompt = VALIDATOR_SYSTEM_PROMPT.format(
        skill_content=skill_content or "无技能文档",
        db_schema=db_schema,
        sql_query=sql_query,
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content="请校验上述 SQL。")]

    response = _model.invoke(messages)
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
        "validation_passed": False,
        "validation_feedback": "校验结果解析失败，请检查 SQL 语法。",
        "retry_count": current_retry + 1,
        "messages": [AIMessage(content="[校验] 校验结果解析失败，建议重新生成 SQL。")],
    }


def route_after_planner(state: AgentGraphState) -> str:
    decision = state.get("planner_decision") or {}
    action = decision.get("action", "load_skill")
    if action == "reply":
        return "__end__"
    return "schema_loader"


def route_after_schema(state: AgentGraphState) -> str:
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
