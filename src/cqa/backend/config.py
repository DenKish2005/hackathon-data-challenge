"""Explicit server configuration. Secret values never appear in reprs."""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    frontend_dir: str = field(
        default_factory=lambda: os.getenv("CQA_FRONTEND_DIR", "frontend/dist")
    )
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///.runtime/cqa-foundation.db")
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            x.strip()
            for x in os.getenv(
                "CQA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if x.strip()
        )
    )
    organizer_urls: dict[str, str] = field(
        default_factory=lambda: {
            key: value
            for key, value in {
                "DEV": os.getenv("FREEDOM_DEV_API_URL") or os.getenv("CQA_DATA_URL", ""),
                "CONTROL": os.getenv("FREEDOM_CONTROL_API_URL", ""),
            }.items()
            if value
        },
        repr=False,
    )
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "mock"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""), repr=False)
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""), repr=False)
    external_data_allowed: bool = field(
        default_factory=lambda: os.getenv("CQA_ALLOW_EXTERNAL_DATA") == "true"
    )
    concurrency: int = field(default_factory=lambda: int(os.getenv("CQA_WORKERS", "2")))
    timeout: float = field(default_factory=lambda: float(os.getenv("CQA_JOB_TIMEOUT", "120")))
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "60")))
    llm_concurrency: int = field(default_factory=lambda: int(os.getenv("LLM_CONCURRENCY", "1")))
    llm_attempts: int = field(default_factory=lambda: int(os.getenv("LLM_ATTEMPTS", "3")))
    llm_context_size: int = field(
        default_factory=lambda: int(os.getenv("LLM_CONTEXT_SIZE", "65536"))
    )
    llm_output_limit: int = field(
        default_factory=lambda: int(os.getenv("LLM_OUTPUT_LIMIT", "8000"))
    )
    critic_enabled: bool = field(
        default_factory=lambda: os.getenv("CQA_ENABLE_CRITIC", "true") == "true"
    )
    prompt_version: str = "foundation-v1"

    def __post_init__(self):
        if not 1 <= self.concurrency <= 16 or self.timeout <= 0:
            raise ValueError("Invalid CQA_WORKERS or CQA_JOB_TIMEOUT")
        if (
            not 1 <= self.llm_concurrency <= 16
            or not 1 <= self.llm_attempts <= 5
            or self.llm_timeout <= 0
            or self.llm_output_limit < 1
            or self.llm_context_size <= self.llm_output_limit + 1024
        ):
            raise ValueError("Invalid LLM limits")
