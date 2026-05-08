from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sql_assistant_agent.auth.jwt import decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> int:
    if not credentials:
        raise HTTPException(status_code=401, detail="未登录，请先登录。")
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期，请重新登录。")
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Token 数据异常。")
    return user_id


def get_optional_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> int | None:
    if not credentials:
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
