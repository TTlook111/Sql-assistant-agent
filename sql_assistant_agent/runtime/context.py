from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_current_user_id: ContextVar[str] = ContextVar("current_user_id", default="demo-user")


def get_current_user_id() -> str:
    return _current_user_id.get()


@contextmanager
def user_context(user_id: str) -> Iterator[None]:
    token = _current_user_id.set(user_id)
    try:
        yield
    finally:
        _current_user_id.reset(token)
