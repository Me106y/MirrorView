"""
Model Factory for LLM and TTS providers.

Supports:
- DashScope (Alibaba Cloud) — default for MirrorView
- OpenAI
- Ollama (local)
- Boson.ai Higgs Audio v3 (TTS)

Usage:
    from server.factories.llm_factory import ModelFactory, TTSFactory

    llm = ModelFactory.get_model("dashscope", "qwen3-max", temperature=0.7)
    tts = TTSFactory.get_tts("higgs-audio-v3", voice="default")
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ModelFactory:
    """Factory for creating LLM chat model instances."""

    # Provider registry: maps provider name -> (module_path, class_name)
    _PROVIDERS = {
        "dashscope": ("langchain_community.chat_models.tongyi", "ChatTongyi"),
        "openai": ("langchain_openai", "ChatOpenAI"),
        "ollama": ("langchain_ollama", "ChatOllama"),
    }

    @classmethod
    def get_model(cls, provider: str, model_name: str, **kwargs):
        """
        Create a LangChain chat model instance.

        Args:
            provider: One of "dashscope", "openai", "ollama"
            model_name: Model identifier (e.g., "qwen3-max", "gpt-4o", "llama3")
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            LangChain BaseChatModel instance

        Raises:
            ValueError: If provider is not supported
            ImportError: If provider's dependencies are not installed
        """
        if provider not in cls._PROVIDERS:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                f"Available: {list(cls._PROVIDERS.keys())}"
            )

        module_path, class_name = cls._PROVIDERS[provider]

        try:
            import importlib
            module = importlib.import_module(module_path)
            model_cls = getattr(module, class_name)
        except ImportError as e:
            raise ImportError(
                f"Failed to import {module_path}.{class_name}. "
                f"Install the required package for provider '{provider}'."
            ) from e

        # Map common kwargs to provider-specific parameter names
        if provider == "dashscope":
            kwargs.setdefault("model", model_name)
            kwargs.setdefault("temperature", 0.7)
            # Pass DASHSCOPE_API_KEY from env if not set in kwargs
            if "dashscope_api_key" not in kwargs:
                api_key = os.environ.get("DASHSCOPE_API_KEY")
                if api_key:
                    kwargs["dashscope_api_key"] = api_key
            return model_cls(**kwargs)

        elif provider == "openai":
            kwargs.setdefault("model", model_name)
            kwargs.setdefault("temperature", 0.7)
            return model_cls(**kwargs)

        elif provider == "ollama":
            kwargs.setdefault("model", model_name)
            kwargs.setdefault("temperature", 0.7)
            kwargs.setdefault("base_url", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
            return model_cls(**kwargs)


class TTSFactory:
    """Factory for creating TTS service instances."""

    _PROVIDERS = {
        "higgs-audio-v3": ("tts_integration.server.tts_service", "HiggsAudioTTS"),
    }

    @classmethod
    def get_tts(cls, provider: str = "higgs-audio-v3", **kwargs):
        """
        Create a TTS service instance.

        Args:
            provider: TTS provider name (default: "higgs-audio-v3")
            **kwargs: Provider-specific configuration

        Returns:
            TTS service instance with a standard interface

        Raises:
            ValueError: If provider is not supported
            ImportError: If provider's dependencies are not installed
        """
        if provider not in cls._PROVIDERS:
            raise ValueError(
                f"Unsupported TTS provider: {provider}. "
                f"Available: {list(cls._PROVIDERS.keys())}"
            )

        module_path, class_name = cls._PROVIDERS[provider]

        try:
            import importlib
            module = importlib.import_module(module_path)
            tts_cls = getattr(module, class_name)
        except ImportError as e:
            raise ImportError(
                f"Failed to import {module_path}.{class_name}. "
                f"Install the required package for TTS provider '{provider}'."
            ) from e

        return tts_cls(**kwargs)


# Singleton convenience functions
_model_cache = {}
_tts_cache = {}


def get_llm(provider: str = "dashscope", model_name: str = "qwen3-max", **kwargs):
    """Get or create a cached LLM instance."""
    cache_key = (provider, model_name, tuple(sorted(kwargs.items())))
    if cache_key not in _model_cache:
        _model_cache[cache_key] = ModelFactory.get_model(provider, model_name, **kwargs)
    return _model_cache[cache_key]


def get_tts(provider: str = "higgs-audio-v3", **kwargs):
    """Get or create a cached TTS instance."""
    cache_key = (provider, tuple(sorted(kwargs.items())))
    if cache_key not in _tts_cache:
        _tts_cache[cache_key] = TTSFactory.get_tts(provider, **kwargs)
    return _tts_cache[cache_key]
