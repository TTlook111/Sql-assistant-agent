from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from sql_assistant_agent.agent.nodes import (
    planner_node,
    route_after_planner,
    route_after_validator,
    skill_loader_node,
    sql_generator_node,
    validator_node,
)
from sql_assistant_agent.agent.state import AgentGraphState


def build_sql_assistant_agent():
    graph = StateGraph(AgentGraphState)

    graph.add_node("planner", planner_node)
    graph.add_node("skill_loader", skill_loader_node)
    graph.add_node("sql_generator", sql_generator_node)
    graph.add_node("validator", validator_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {"skill_loader": "skill_loader", "sql_generator": "sql_generator"},
    )
    graph.add_edge("skill_loader", "sql_generator")
    graph.add_edge("sql_generator", "validator")
    graph.add_conditional_edges(
        "validator",
        route_after_validator,
        {"sql_generator": "sql_generator", "__end__": END},
    )

    return graph.compile(checkpointer=InMemorySaver())
