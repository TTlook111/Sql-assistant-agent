from langchain.agents import create_agent
from langchain_community.chat_models.tongyi import ChatTongyi
from langgraph.checkpoint.memory import InMemorySaver

from sql_assistant_agent.config.config import DASHSCOPE_API_KEY
from sql_assistant_agent.middleware.skill_middleware import SkillMiddleware


def build_sql_assistant_agent():
    """构建并返回 SQL 助手 Agent 实例。

    Returns:
        已注入 SkillMiddleware 和内存检查点能力的 LangChain Agent。
    """
    model = ChatTongyi(
        model="qwen3-max",
        api_key=DASHSCOPE_API_KEY,
    )
    return create_agent(
        model,
        system_prompt=(
            "你是一个 SQL 查询助手，帮助用户针对业务数据库编写查询语句。"
        ),
        middleware=[SkillMiddleware()],
        checkpointer=InMemorySaver(),
    )

