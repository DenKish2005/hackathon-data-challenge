"""Explicit server configuration. Secret values never appear in reprs."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def organizer_urls():
    urls = {
        key: value
        for key, value in {
            "DEV": os.getenv("FREEDOM_DEV_API_URL") or os.getenv("CQA_DATA_URL", ""),
            "CONTROL": os.getenv("FREEDOM_CONTROL_API_URL", ""),
        }.items()
        if value
    }
    file = os.getenv("FREEDOM_DATASET_URLS_FILE")
    if file:
        try:
            extra = json.loads(Path(file).read_text(encoding="utf-8-sig"))
            if not isinstance(extra, dict) or any(
                not isinstance(k, str) or not 1 <= len(k) <= 100 or not isinstance(v, str)
                for k, v in extra.items()
            ):
                raise ValueError()
            urls.update(extra)
        except (OSError, ValueError) as exc:
            raise ValueError("Invalid private dataset URL configuration file") from exc
    return urls


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
        default_factory=organizer_urls,
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
    strategy: str = field(default_factory=lambda: os.getenv("CQA_STRATEGY", "two_pass"))
    agent_concurrency: int = field(
        default_factory=lambda: int(os.getenv("CQA_AGENT_CONCURRENCY", "1"))
    )
    prompt_version: str = "foundation-v1"

    def __post_init__(self):
        if self.strategy not in ("two_pass", "multi_agent"):
            raise ValueError("CQA_STRATEGY must be two_pass or multi_agent")
        if not 1 <= self.agent_concurrency <= 16:
            raise ValueError("CQA_AGENT_CONCURRENCY must be between 1 and 16")
        if self.strategy == "multi_agent" and not self.critic_enabled:
            raise ValueError("Multi-agent evaluation requires the final critic")
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
