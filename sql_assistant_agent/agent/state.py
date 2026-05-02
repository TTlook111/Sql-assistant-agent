from __future__ import annotations

from typing import Annotated, Any, NotRequired, TypedDict

from langchain.messages import AnyMessage
from langgraph.graph import add_messages


class PlannerDecision(TypedDict):
    action: str
    skill_name: NotRequired[str]
    reasoning: str
    reply_text: NotRequired[str]


class AgentGraphState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    planner_decision: NotRequired[PlannerDecision | None]
    skill_content: NotRequired[str]
    sql_query: NotRequired[str]
    validation_passed: NotRequired[bool]
    validation_feedback: NotRequired[str]
    retry_count: NotRequired[int]
