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


DASHSCOPE_API_KEY = _get_required_env("DASHSCOPE_API_KEY")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_FILES_DIR = PROJECT_ROOT / "agent" / "skills"
