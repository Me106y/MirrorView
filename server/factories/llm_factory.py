from abc import ABC, abstractmethod
from langchain_community.chat_models.tongyi import ChatTongyi
from server.config import Config

class LLMProvider(ABC):
    @abstractmethod
    def create_chat_model(self, model_name: str, **kwargs):
        pass

class DashScopeProvider(LLMProvider):
    def create_chat_model(self, model_name: str = "qwen3-max", **kwargs):
        return ChatTongyi(
            model=model_name,
            dashscope_api_key=Config.DASHSCOPE_API_KEY,
            temperature=kwargs.get("temperature", 0.7)
        )

# Future: class OpenAIProvider(LLMProvider): ...

class ModelFactory:
    _providers = {
        "dashscope": DashScopeProvider()
    }
    
    @classmethod
    def get_model(cls, provider_name: str = "dashscope", model_name: str = "qwen3-max", **kwargs):
        provider = cls._providers.get(provider_name)
        if not provider:
            raise ValueError(f"Provider {provider_name} not supported")
        return provider.create_chat_model(model_name, **kwargs)
