"""项目配置：负责读取环境变量与模型配置。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 加载项目根目录的 .env 配置
load_dotenv()


def _get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"未检测到 {key}，请先在 .env 文件中配置。")
    return value


def _env_flag(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DASHSCOPE_API_KEY = _get_required_env("DASHSCOPE_API_KEY")
DASHSCOPE_MODEL = os.getenv("DASHSCOPE_MODEL", "qwen3-max")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_FILES_DIR = PROJECT_ROOT / "agent" / "skills"

# Agent speed controls. Defaults favor faster end-to-end responses.
SQL_ASSISTANT_USE_LLM_PLANNER = _env_flag("SQL_ASSISTANT_USE_LLM_PLANNER", False)
SQL_ASSISTANT_VALIDATE_SQL = _env_flag("SQL_ASSISTANT_VALIDATE_SQL", False)
SQL_ASSISTANT_REVIEW_ANSWER = _env_flag("SQL_ASSISTANT_REVIEW_ANSWER", True)
SQL_ASSISTANT_AUTO_RETRY_ON_REVIEW_FAIL = _env_flag(
    "SQL_ASSISTANT_AUTO_RETRY_ON_REVIEW_FAIL", True
)
SQL_ASSISTANT_QUERY_MAX_ROWS = int(os.getenv("SQL_ASSISTANT_QUERY_MAX_ROWS", "200"))

# JWT
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "sql-assistant-jwt-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72

# MySQL (应用存储)
APP_DB_HOST = os.getenv("APP_DB_HOST", "127.0.0.1")
APP_DB_PORT = int(os.getenv("APP_DB_PORT", "3306"))
APP_DB_USER = os.getenv("APP_DB_USER", "root")
APP_DB_PASSWORD = os.getenv("APP_DB_PASSWORD", "123456")
APP_DB_NAME = os.getenv("APP_DB_NAME", "sql_assistant")

# SQLite (长时记忆)
SQLITE_MEMORY_PATH = os.getenv(
    "SQLITE_MEMORY_PATH", str(PROJECT_ROOT / "data" / "memory.db")
)
