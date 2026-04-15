"""项目配置：负责读取环境变量与模型配置。"""
import os

from dotenv import load_dotenv

# 加载项目根目录的 .env 配置
load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not DASHSCOPE_API_KEY:
    raise ValueError("未检测到 DASHSCOPE_API_KEY，请先在 .env 文件中配置。")
