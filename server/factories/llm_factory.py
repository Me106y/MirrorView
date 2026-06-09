"""Model Factory (DeepSeek only)."""

import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Ensure DeepSeek key is available even when this module is imported directly.
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(ROOT_DIR, ".env_tts"))


class ModelFactory:
    """Factory for creating DeepSeek chat model instances."""

    _PROVIDER = "deepseek"

    # Default provider configs
    _DEFAULT_CONFIG = {
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "temperature": 0.7,
        },
    }

    @staticmethod
    def _get_chat_openai_class():
        """Resolve ChatOpenAI from available integrations."""
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI
        except ImportError:
            try:
                # Backward-compatible fallback when langchain_openai is not installed.
                from langchain_community.chat_models import ChatOpenAI
                logger.warning(
                    "langchain_openai not installed, falling back to "
                    "langchain_community.chat_models.ChatOpenAI"
                )
                return ChatOpenAI
            except ImportError as exc:
                raise ImportError(
                    "ChatOpenAI backend is unavailable. Install one of:\n"
                    "  pip install langchain-openai\n"
                    "or\n"
                    "  pip install langchain-community"
                ) from exc

    @classmethod
    def get_model(cls, provider: str, model_name: str, **kwargs):
        """
        Create a DeepSeek LangChain chat model instance.

        Args:
            provider: must be "deepseek"
            model_name: DeepSeek model identifier
            **kwargs: Overrides (temperature, base_url, api_key, etc.)

        Returns:
            LangChain BaseChatModel instance
        """
        if provider != cls._PROVIDER:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                "Only 'deepseek' is supported in this project."
            )

        ChatOpenAI = cls._get_chat_openai_class()

        api_key = kwargs.pop("api_key", os.environ.get("DEEPSEEK_API_KEY", "")).strip()
        base_url = kwargs.pop("base_url", os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))
        model = model_name or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is empty. Set it in environment or .env_tts before starting the server."
            )

        return ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            openai_api_base=base_url,
            temperature=kwargs.pop("temperature", 0.7),
            max_tokens=kwargs.pop("max_tokens", 2048),
            streaming=kwargs.pop("streaming", True),
            **kwargs,
        )


# ── Singleton caches ──

_model_cache = {}


def get_llm(provider: str = "deepseek", model_name: str = "deepseek-chat", **kwargs):
    """Get or create a cached LLM instance."""
    cache_key = (provider, model_name, tuple(sorted(kwargs.items())))
    if cache_key not in _model_cache:
        _model_cache[cache_key] = ModelFactory.get_model(provider, model_name, **kwargs)
    return _model_cache[cache_key]
