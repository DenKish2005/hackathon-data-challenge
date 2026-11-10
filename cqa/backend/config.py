"""Configuration: credentials never live in source or HTTP responses."""
from dataclasses import dataclass, field
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("CQA_DATABASE_URL", "sqlite:///./cqa/cqa.db"))
    dataset_path: str = field(default_factory=lambda: os.getenv("CQA_DATASET_PATH", "cqa/data/cqa_dev_utf8_fixed.json"))
    dev_api_url: str = field(default_factory=lambda: os.getenv("FREEDOM_DEV_API_URL", ""))
    control_api_url: str = field(default_factory=lambda: os.getenv("FREEDOM_CONTROL_API_URL", ""))
    cors_origins: str = field(default_factory=lambda: os.getenv("CQA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "mock"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    allow_external_llm: bool = field(default_factory=lambda: os.getenv("CQA_ALLOW_EXTERNAL_LLM", "false").lower() == "true")
    worker_poll_seconds: float = 0.25
    max_llm_concurrency: int = 2
