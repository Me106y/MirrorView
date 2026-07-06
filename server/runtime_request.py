from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from server.config import Config

ALLOWED_BYOK_PROVIDERS = {"openai", "deepseek", "anthropic"}
DEFAULT_PROVIDER_MODELS = {
    "openai": "gpt-4o-mini",
    "deepseek": Config.DEEPSEEK_MODEL or "deepseek-chat",
    "anthropic": "claude-3-5-sonnet-latest",
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def default_platform_runtime() -> Dict[str, str]:
    provider = (Config.PLATFORM_PROVIDER or "deepseek").strip().lower()
    if provider not in {"deepseek", "openai", "anthropic"}:
        provider = "deepseek"
    model = (Config.PLATFORM_MODEL or "").strip()
    if not model:
        model = DEFAULT_PROVIDER_MODELS.get(provider, "deepseek-chat")
    return {
        "mode": "platform",
        "provider": provider,
        "model": model,
        "api_key": "",
        "base_url": "",
    }


def parse_runtime_payload(payload: Optional[Dict[str, Any]]) -> Tuple[Optional[Dict[str, str]], str]:
    body = payload or {}
    raw = body.get("runtime")

    if raw is None:
        return default_platform_runtime(), ""

    if isinstance(raw, str):
        raw_text = raw.strip()
        if raw_text:
            try:
                raw = json.loads(raw_text)
            except Exception:
                return None, "runtime must be a valid JSON object."

    if not isinstance(raw, dict):
        return None, "runtime must be an object."

    mode = _as_text(raw.get("mode") or "platform").lower()
    if mode not in {"platform", "byok"}:
        return None, "runtime.mode must be one of: platform, byok."

    if mode == "platform":
        runtime = default_platform_runtime()
        requested_model = _as_text(raw.get("model"))
        requested_base_url = _as_text(raw.get("base_url"))
        requested_api_key = _as_text(raw.get("api_key"))
        if requested_model:
            runtime["model"] = requested_model
        if requested_base_url:
            runtime["base_url"] = requested_base_url
        if requested_api_key:
            runtime["api_key"] = requested_api_key
        return runtime, ""

    provider = _as_text(raw.get("provider")).lower()
    if provider not in ALLOWED_BYOK_PROVIDERS:
        return None, "runtime.provider must be one of: openai, deepseek, anthropic."

    api_key = _as_text(raw.get("api_key"))
    if not api_key:
        return None, "runtime.api_key is required when runtime.mode is byok."

    model = _as_text(raw.get("model")) or DEFAULT_PROVIDER_MODELS.get(provider, "")
    if not model:
        return None, "runtime.model is required for BYOK provider."

    base_url = _as_text(raw.get("base_url"))
    return {
        "mode": "byok",
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
    }, ""


def build_runtime_meta(runtime: Dict[str, str]) -> Dict[str, str]:
    safe = runtime or default_platform_runtime()
    return {
        "runtime_mode": _as_text(safe.get("mode") or "platform"),
        "runtime_provider": _as_text(safe.get("provider") or "deepseek"),
    }
