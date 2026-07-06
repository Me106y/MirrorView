"""
Model Factory for LLM and TTS providers.

Supports:
- DeepSeek (via OpenAI-compatible API) — default for MirrorView
- DashScope (Alibaba Cloud) — legacy
- OpenAI — generic
- Anthropic — generic
- Ollama — local
- Boson.ai Higgs Audio v3 (TTS)

Usage:
    from server.factories.llm_factory import ModelFactory

    llm = ModelFactory.get_model("deepseek", "deepseek-chat", temperature=0.7)
"""

import os
import logging

logger = logging.getLogger(__name__)


class ModelFactory:
    """Factory for creating LLM chat model instances."""

    _PROVIDERS = {
        "deepseek":  None,  # handled specially — OpenAI-compatible
        "openai":    ("langchain_openai", "ChatOpenAI"),
        "anthropic": ("langchain_anthropic", "ChatAnthropic"),
        "dashscope": ("langchain_community.chat_models.tongyi", "ChatTongyi"),
        "ollama":    ("langchain_ollama", "ChatOllama"),
    }

    # Default provider configs
    _DEFAULT_CONFIG = {
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "temperature": 0.7,
        },
    }

    @staticmethod
    def _get_chat_openai_cls():
        """
        Prefer modern `langchain_openai.ChatOpenAI`.
        Fallback to `langchain_community.chat_models.ChatOpenAI` for environments
        where langchain-openai is not installed.
        """
        try:
            from langchain_openai import ChatOpenAI  # type: ignore
            return ChatOpenAI
        except ImportError:
            logger.warning(
                "langchain_openai is not installed, falling back to "
                "langchain_community.chat_models.ChatOpenAI"
            )
            try:
                from langchain_community.chat_models import ChatOpenAI  # type: ignore
                return ChatOpenAI
            except ImportError as e:
                raise ModuleNotFoundError(
                    "No ChatOpenAI backend available. "
                    "Install one of: `pip install langchain-openai` (recommended) "
                    "or ensure `langchain-community` includes ChatOpenAI."
                ) from e

    @classmethod
    def get_model(cls, provider: str, model_name: str, **kwargs):
        """
        Create a LangChain chat model instance.

        Args:
            provider: "deepseek" | "openai" | "anthropic" | "dashscope" | "ollama"
            model_name: Model identifier
            **kwargs: Overrides (temperature, base_url, api_key, etc.)

        Returns:
            LangChain BaseChatModel instance
        """
        if provider not in cls._PROVIDERS:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                f"Available: {list(cls._PROVIDERS.keys())}"
            )

        # ── DeepSeek (OpenAI-compatible) ──
        if provider == "deepseek":
            ChatOpenAI = cls._get_chat_openai_cls()

            api_key = kwargs.pop("api_key", os.environ.get("DEEPSEEK_API_KEY", ""))
            base_url = kwargs.pop("base_url", "https://api.deepseek.com/v1")

            return ChatOpenAI(
                model=model_name,
                openai_api_key=api_key,
                openai_api_base=base_url,
                temperature=kwargs.pop("temperature", 0.7),
                max_tokens=kwargs.pop("max_tokens", 2048),
                streaming=kwargs.pop("streaming", True),
                **kwargs,
            )

        # ── Generic OpenAI ──
        if provider == "openai":
            ChatOpenAI = cls._get_chat_openai_cls()

            base_url = kwargs.pop("base_url", os.environ.get("OPENAI_BASE_URL", None))
            api_key = kwargs.pop("api_key", os.environ.get("OPENAI_API_KEY", ""))

            extra = {}
            if base_url:
                extra["openai_api_base"] = base_url

            return ChatOpenAI(
                model=model_name,
                openai_api_key=api_key,
                temperature=kwargs.pop("temperature", 0.7),
                max_tokens=kwargs.pop("max_tokens", 2048),
                **extra,
                **kwargs,
            )

        # ── Anthropic ──
        if provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
            except ImportError as e:
                raise ModuleNotFoundError(
                    "Anthropic provider requires optional dependency "
                    "`langchain-anthropic`. Install it in your runtime "
                    "environment before using provider=anthropic."
                ) from e

            api_key = kwargs.pop("api_key", os.environ.get("ANTHROPIC_API_KEY", ""))
            base_url = kwargs.pop("base_url", os.environ.get("ANTHROPIC_BASE_URL", None))

            extra = {}
            if base_url:
                extra["base_url"] = base_url

            return ChatAnthropic(
                model=model_name,
                anthropic_api_key=api_key,
                temperature=kwargs.pop("temperature", 0.7),
                max_tokens=kwargs.pop("max_tokens", 2048),
                **extra,
                **kwargs,
            )

        # ── DashScope (legacy) ──
        if provider == "dashscope":
            module_path, class_name = cls._PROVIDERS[provider]
            import importlib
            module = importlib.import_module(module_path)
            model_cls = getattr(module, class_name)

            api_key = kwargs.pop("dashscope_api_key",
                                 os.environ.get("DASHSCOPE_API_KEY", ""))
            kwargs.setdefault("model", model_name)
            kwargs.setdefault("temperature", 0.7)
            if api_key:
                kwargs["dashscope_api_key"] = api_key
            return model_cls(**kwargs)

        # ── Ollama ──
        if provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=model_name,
                temperature=kwargs.pop("temperature", 0.7),
                base_url=kwargs.pop("base_url",
                                    os.environ.get("OLLAMA_BASE_URL",
                                                   "http://localhost:11434")),
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
