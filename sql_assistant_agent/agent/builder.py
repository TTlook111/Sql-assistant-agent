from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from sql_assistant_agent.agent.nodes import (
    planner_node,
    route_after_planner,
    route_after_schema,
    route_after_validator,
    schema_loader_node,
    skill_loader_node,
    sql_generator_node,
    validator_node,
)
from sql_assistant_agent.agent.state import AgentGraphState
from sql_assistant_agent.config.config import SQLITE_MEMORY_PATH


def _get_checkpointer() -> SqliteSaver:
    db_path = Path(SQLITE_MEMORY_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


def build_sql_assistant_agent():
    graph = StateGraph(AgentGraphState)

    graph.add_node("planner", planner_node)
    graph.add_node("schema_loader", schema_loader_node)
    graph.add_node("skill_loader", skill_loader_node)
    graph.add_node("sql_generator", sql_generator_node)
    graph.add_node("validator", validator_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {"schema_loader": "schema_loader", "__end__": END},
    )
    graph.add_conditional_edges(
        "schema_loader",
        route_after_schema,
        {"skill_loader": "skill_loader", "sql_generator": "sql_generator"},
    )
    graph.add_edge("skill_loader", "sql_generator")
    graph.add_edge("sql_generator", "validator")
    graph.add_conditional_edges(
        "validator",
        route_after_validator,
        {"sql_generator": "sql_generator", "__end__": END},
    )

    return graph.compile(checkpointer=_get_checkpointer())
