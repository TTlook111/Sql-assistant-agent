"""项目配置：负责读取环境变量与模型配置。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 加载项目根目录的 .env 配置
load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SKILL_DB_PATH = DATA_DIR / "skills.db"
