from langchain_core.utils.uuid import uuid7

from sql_assistant_agent.agent.builder import build_sql_assistant_agent


def main() -> None:
    agent = build_sql_assistant_agent()

    thread_id = str(uuid7())
    config = {"configurable": {"thread_id": thread_id}}

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "写一条 SQL 查询，找出最近一个月内下单金额超过 1000 美元的所有客户。"
                    ),
                }
            ]
        },
        config,
    )

    for message in result["messages"]:
        if hasattr(message, "pretty_print"):
            message.pretty_print()
        else:
            print(f"{message.type}: {message.content}")


if __name__ == "__main__":
    main()
