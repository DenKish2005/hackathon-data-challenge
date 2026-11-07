from urllib.parse import urlsplit

from cqa.infra.llm.base import Provider, ProviderError
from cqa.infra.llm.mock import MockProvider
from cqa.infra.llm.ollama import OllamaProvider
from cqa.infra.llm.openai_compatible import OpenAICompatibleProvider


def build_provider(settings):
    if settings.llm_provider == "mock":
        return MockProvider()
    options = dict(
        model=settings.llm_model,
        concurrency=settings.llm_concurrency,
        timeout=settings.llm_timeout,
        context_size=settings.llm_context_size,
        output_limit=settings.llm_output_limit,
        attempts=settings.llm_attempts,
    )
    if settings.llm_provider == "ollama":
        if not settings.llm_model or not settings.llm_base_url:
            raise ValueError("Ollama requires LLM_MODEL and LLM_BASE_URL")
        if (
            urlsplit(settings.llm_base_url).hostname not in ("localhost", "127.0.0.1", "::1")
            and not settings.external_data_allowed
        ):
            raise ValueError(
                "Remote Ollama requires organizer permission and CQA_ALLOW_EXTERNAL_DATA=true"
            )
        return OllamaProvider(settings.llm_base_url, **options)
    if settings.llm_provider == "openai_compatible":
        if not settings.external_data_allowed:
            raise ValueError(
                "External data requires organizer permission and CQA_ALLOW_EXTERNAL_DATA=true"
            )
        if not all((settings.llm_model, settings.llm_base_url, settings.llm_api_key)):
            raise ValueError("Configure LLM_MODEL, LLM_BASE_URL and LLM_API_KEY")
        return OpenAICompatibleProvider(
            settings.llm_base_url, api_key=settings.llm_api_key, **options
        )
    raise ValueError("Unknown LLM_PROVIDER")


__all__ = ["Provider", "ProviderError", "build_provider"]
