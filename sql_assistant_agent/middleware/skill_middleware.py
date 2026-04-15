from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.messages import SystemMessage

from sql_assistant_agent.domain.skills import SKILLS
from sql_assistant_agent.tools.load_skill import load_skill


class SkillMiddleware(AgentMiddleware):
    """将技能说明注入系统提示词的中间件。"""

    # 在 middleware 上注册工具，模型才知道可以调用 load_skill。
    tools = [load_skill]

    def __init__(self) -> None:
        # 初始化时预构建技能摘要，避免每次请求重复拼接字符串。
        skills_list = []
        for skill in SKILLS:
            skills_list.append(f"- **{skill['name']}**: {skill['description']}")
        self.skills_prompt = "\n".join(skills_list)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        # 这里是“模型调用前”的拦截点：统一注入技能导航信息。
        # 后续可扩展：按角色注入不同技能，例如：
        # - 销售经理只注入 sales_analytics
        # - 仓储主管只注入 inventory_management
        # - 管理员注入全部技能
        skills_addendum = (
            f"\n\n## 可用技能\n\n{self.skills_prompt}\n\n"
            "当你需要处理某一类请求的详细规则时，请使用 load_skill 工具。"
        )

        # 第 1 步：先复制当前系统消息的内容块，避免直接修改原对象。
        # 这样做可以保证中间件操作是“无副作用”的，便于后续链路复用。
        new_content = list(request.system_message.content_blocks) + [
            # 第 2 步：把本次构造的技能说明追加为一个新的 text 内容块。
            {"type": "text", "text": skills_addendum}
        ]
        # 第 3 步：用追加后的内容创建一个新的 SystemMessage 对象。
        new_system_message = SystemMessage(content=new_content)
        # 第 4 步：基于原 request 生成一个“覆盖了 system_message 的新 request”。
        # request.override(...) 会返回新对象，不会原地改动原 request。
        modified_request = request.override(system_message=new_system_message)
        # 第 5 步：把修改后的请求交给下游 handler，继续执行真实模型调用。
        return handler(modified_request)

