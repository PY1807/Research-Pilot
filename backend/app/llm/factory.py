"""Build the configured LLM chains from settings. Routes get them through FastAPI
dependencies (`get_answer_llm`, `get_judge_llm`), so tests swap in a FakeProvider."""

from app.config import Settings, get_settings
from app.llm.base import LLMNotConfigured, LLMProvider
from app.llm.providers import FallbackProvider, GeminiProvider, OpenAICompatibleProvider

KNOWN_PROVIDERS = ("gemini", "grok", "groq")


def _build(name: str, settings: Settings) -> LLMProvider | None:
    """One provider, or None when its API key isn't set."""
    timeout = settings.llm_timeout_seconds
    if name == "gemini":
        if not settings.gemini_api_key:
            return None
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model, timeout)
    if name in ("grok", "groq"):
        key = getattr(settings, f"{name}_api_key")
        if not key:
            return None
        return OpenAICompatibleProvider(
            name,
            getattr(settings, f"{name}_base_url"),
            key,
            getattr(settings, f"{name}_model"),
            timeout,
        )
    raise ValueError(f"Unknown LLM provider {name!r}; expected one of {KNOWN_PROVIDERS}")


def build_chain(order: str, settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    names = [n.strip() for n in order.split(",") if n.strip()]
    providers = [p for p in (_build(n, settings) for n in names) if p is not None]
    if not providers:
        raise LLMNotConfigured(
            "No LLM API key is set. Add GEMINI_API_KEY (and optionally GROK_API_KEY or "
            "GROQ_API_KEY) to the .env file in the repo root, then restart with `make up`."
        )
    return providers[0] if len(providers) == 1 else FallbackProvider(providers)


def get_answer_llm() -> LLMProvider:
    return build_chain(get_settings().llm_answer_providers)


def get_judge_llm() -> LLMProvider:
    return build_chain(get_settings().llm_judge_providers)
