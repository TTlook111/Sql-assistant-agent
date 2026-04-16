from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_current_user_id: ContextVar[str] = ContextVar("current_user_id", default="demo-user")


def get_current_user_id() -> str:
    """获取当前协程上下文中的用户 ID。

    Returns:
        当前用户 ID；未设置时返回默认值 "demo-user"。
    """
    return _current_user_id.get()


@contextmanager
def user_context(user_id: str) -> Iterator[None]:
    """在上下文块内设置当前用户 ID，并在退出时自动恢复。

    Args:
        user_id: 需要绑定到当前上下文的用户 ID。

    Returns:
        一个上下文管理器，with 块中可通过 `get_current_user_id()` 读取该用户。
    """
    token = _current_user_id.set(user_id)
    try:
        yield
    finally:
        _current_user_id.reset(token)
