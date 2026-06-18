"""项目配置管理"""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


def get_default_device() -> str:
    """自动检测可用设备（延迟导入 torch，避免启动时初始化）"""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


# 项目根目录 (backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """全局配置，从环境变量或 .env 文件读取"""

    # LLM
    llm_api_key: str = Field(default="", description="LLM API Key，必须在 .env 中配置")
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "mimo-v2.5-pro"

    # Embedding (已缓存，使用本地路径)
    embedding_model_path: str = str(Path.home() / ".cache" / "huggingface" / "hub" / "models--dunzhang--stella-mrl-large-zh-v3.5-1792d" / "snapshots" / "17bb1c32a93a8fc5f6fc9e91d5ea86da99983cfe")
    embedding_dim: int = 1024
    embedding_device: str = ""  # 空字符串表示自动检测

    # Reranker (本地模型)
    reranker_model_path: str = str(PROJECT_ROOT / "models")

    # Chroma
    chroma_persist_dir: str = str(PROJECT_ROOT / "data" / "chroma")
    chroma_collection_name: str = "three_kingdom"

    # SQLite
    sqlite_db_path: str = str(PROJECT_ROOT / "data" / "sqlite.db")

    # Raw data
    raw_data_dir: str = str(PROJECT_ROOT / "data" / "raw")

    # Chunking
    chunk_size: int = 400
    chunk_overlap: int = 50
    agentic_split: bool = True  # 是否启用 LLM 语义分块

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def model_post_init(self, __context):
        """初始化后处理：自动检测设备"""
        if not self.embedding_device:
            object.__setattr__(self, "embedding_device", get_default_device())


settings = Settings()
