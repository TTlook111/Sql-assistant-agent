from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.messages import SystemMessage

from sql_assistant_agent.config.config import SKILL_DB_PATH
from sql_assistant_agent.runtime.context import get_current_user_id
from sql_assistant_agent.storage.skill_store import SkillStore
from sql_assistant_agent.tools.load_skill import load_skill


class SkillMiddleware(AgentMiddleware):
    """将技能说明注入系统提示词的中间件。"""

    # 在 middleware 上注册工具，模型才知道可以调用 load_skill。
    tools = [load_skill]

    def __init__(self) -> None:
        """初始化中间件并绑定技能存储。

        Returns:
            None
        """
        self.store = SkillStore(SKILL_DB_PATH)

    def _build_skills_prompt(self, user_id: str, user_query: str) -> tuple[str, str]:
        """构建候选技能提示文本，并返回技能来源模式。

        Args:
            user_id: 当前用户 ID。
            user_query: 用户最新提问文本。

        Returns:
            二元组 (prompt, mode)。
            - prompt: 注入系统提示词的候选技能摘要文本。
            - mode: 技能来源模式，"uploaded"、"builtin_fallback" 或 "none"。
        """
        skills = self.store.search_relevant_skills(user_id, user_query, limit=3)
        if not skills:
            return "- 暂无可用技能。", "none"
        _, mode = self.store.list_effective_skills(user_id)
        lines: list[str] = []
        for item in skills:
            summary = (item.get("description") or "").strip()
            tags = ", ".join(item.get("tags", [])[:4])
            tags_text = f"（tags: {tags}）" if tags else ""
            lines.append(f"- **{item['name']}**: {summary}{tags_text}")
        return "\n".join(lines), mode

    def _extract_latest_user_query(self, request: ModelRequest) -> str:
        """从模型请求中提取最近一条用户消息文本。

        Args:
            request: 当前模型调用请求对象。

        Returns:
            提取到的用户文本；若未找到则返回空字符串。
        """
        messages = getattr(request, "messages", []) or []
        for msg in reversed(messages):
            role = getattr(msg, "type", "") or getattr(msg, "role", "")
            if role not in {"human", "user"}:
                continue
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_items = [item.get("text", "") for item in content if isinstance(item, dict)]
                return "\n".join([text for text in text_items if text]).strip()
        return ""

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """在模型调用前注入技能导航上下文并继续执行下游调用。

        Args:
            request: 当前模型请求对象。
            handler: 下游模型处理函数。

        Returns:
            下游 handler 返回的模型响应。
        """
        user_id = get_current_user_id()
        user_query = self._extract_latest_user_query(request)
        skills_prompt, mode = self._build_skills_prompt(user_id, user_query)
        mode_text = "用户上传 skills" if mode == "uploaded" else "内置 skills（回退）"
        skills_addendum = (
            f"\n\n## 候选技能（自动路由，用户：{user_id}，来源：{mode_text}）\n\n{skills_prompt}\n\n"
            "你是 SQL 助手。请优先依据以上候选技能中的业务口径回答。"
            "当需要字段级细节、枚举值定义、复杂规则或示例 SQL 时，调用 load_skill 工具加载完整技能内容后再生成 SQL。"
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

