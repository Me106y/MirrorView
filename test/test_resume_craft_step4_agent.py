from server.services.careerforge_agent import CareerForgeAgent
from server.services.ai_service import AIService
from server.config import Config

import json
import os
from pathlib import Path


def _agent() -> CareerForgeAgent:
    # Use a non-None placeholder to avoid model bootstrap in __init__;
    # these tests only call heuristic helpers that do not require an LLM.
    return CareerForgeAgent(llm=object())


def _mask(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "<empty>"
    if len(text) <= 12:
        return text[:3] + "***"
    return text[:8] + "..." + text[-4:]


def _read_server_config_key() -> str:
    cfg_path = Path(__file__).resolve().parents[1] / "server" / "config.json"
    if not cfg_path.exists():
        return ""
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(data.get("DEEPSEEK_API_KEY") or "").strip()


def test_000_step4_model_connection_status(capsys):
    env_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    file_key = _read_server_config_key()
    active_key = env_key or file_key or Config.DEEPSEEK_API_KEY
    source = (
        "env:DEEPSEEK_API_KEY"
        if env_key
        else ("server/config.json" if file_key else "Config.DEEPSEEK_API_KEY")
    )

    ai_service = AIService()
    decision = ai_service.run_resume_craft_step4_decision(
        {
            "profile_context": "目标岗位：AI应用开发",
            "history_text": "",
            "user_input": "我做了一个基于 LangChain 的项目。",
            "is_first_round": True,
            "followup_count": 1,
            "current_index": 1,
            "expected_experience_count": 1,
            "fallback_reply": "请继续补充这段项目的功能实现与技术细节。",
        },
        runtime={
            "mode": "platform",
            "provider": "deepseek",
            "model": Config.DEEPSEEK_MODEL,
            "api_key": active_key,
            "base_url": Config.DEEPSEEK_BASE_URL,
        },
    )
    ok = bool(decision.get("model_connection_ok"))
    err = str(decision.get("model_connection_error") or "").strip()
    with capsys.disabled():
        print(
            "[STEP4_MODEL_KEY] "
            f"source={source} env={_mask(env_key)} file={_mask(file_key)} active={_mask(active_key)} "
            f"base={Config.DEEPSEEK_BASE_URL} model={Config.DEEPSEEK_MODEL}"
        )
        print(f"[STEP4_MODEL_CONNECTION] {'SUCCESS' if ok else 'FAILED'}" + (f" | {err}" if err else ""))
    assert "model_connection_ok" in decision


def test_step4_heuristic_decision_dynamic_focus_and_missing_points():
    agent = _agent()
    decision = agent._build_step4_heuristic_decision(
        {
            "user_input": (
                "基于 LangChain 与 Agentic RAG 架构构建 AI 面试官，"
                "后端采用 Flask + SQLAlchemy，支持 JWT 权限控制，"
                "将查询接口响应时间降低 42%。"
            ),
            "is_first_round": True,
            "followup_count": 1,
            "fallback_reply": "请继续补充这段项目的关键信息。",
        }
    )

    assert len(decision["missing_points"]) == 1
    assert any("链路" in item or "核心功能" in item or "输入到输出" in item for item in decision["missing_points"])
    assert any(item in decision["reasoning_focus"] for item in ["LangChain", "Agentic RAG", "Flask", "JWT"])
    assert decision["active_focus_topic"]
    assert decision["next_probe_dimension"] == "implementation"
    assert decision["resume_ready_draft"]["title"]
    assert decision["resume_ready_draft"]["bullets"]


def test_step4_heuristic_decision_marks_completed_when_input_already_covers_all_core_evidence():
    agent = _agent()
    decision = agent._build_step4_heuristic_decision(
        {
            "user_input": (
                "项目：智能检索平台。2025.03-2025.06。"
                "我主导重构召回链路，采用 K8s + Redis 的微服务架构，挑战是高并发下时延抖动；"
                "为什么选择缓存分层与批处理，而不是直接扩容机器。"
                "通过链路追踪定位热点并做缓存分层和批处理改造，将 P95 从 620ms 降到 280ms，"
                "线上监控面板持续观测 2 周无回退。"
            ),
            "is_first_round": False,
            "followup_count": 2,
            "fallback_reply": "请继续补充这段项目的关键信息。",
        }
    )

    assert decision["missing_points"] == ["是否还有要补充的经历"]
    assert decision["next_probe_dimension"] == "more_experience"
    assert decision["current_experience_completed"] is True


def test_step4_coerce_prefers_agent_missing_points_without_route_style_rewrite():
    agent = _agent()
    payload = {
        "user_input": "我做了一个基于 LangChain 的检索服务，接口响应提升 42%。",
        "active_focus": {
            "topic": "LangChain 检索链路",
            "stage": "implementation",
            "evidence": {"implementation": True, "tradeoff": False, "validation": True},
            "turn_count": 1,
        },
    }
    fallback = agent._build_step4_heuristic_decision(payload)
    decision = agent._coerce_step4_single_focus_decision(
        payload=payload,
        candidate={
            "reply": "请补充时间、角色以及还有没有第2段经历。",
            "missing_points": ["项目时间", "角色定位", "还有没有第2段经历"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "next_probe_dimension": "tradeoff",
        },
        fallback=fallback,
    )

    assert decision["current_experience_completed"] is False
    assert decision["next_probe_dimension"] == "tradeoff"
    assert decision["missing_points"] == ["项目时间", "角色定位", "还有没有第2段经历"]
    assert "补充时间" in decision["reply"]


def test_step4_coerce_forces_first_round_into_implementation_probe_when_candidate_is_tradeoff():
    agent = _agent()
    payload = {
        "user_input": "基于 LangChain 与 Agentic RAG 架构构建 AI 面试官，接口响应时间降低 42%。",
        "is_first_round": True,
        "active_focus": {"topic": "", "stage": "implementation", "evidence": {}, "turn_count": 0},
    }
    fallback = agent._build_step4_heuristic_decision(payload)
    decision = agent._coerce_step4_single_focus_decision(
        payload=payload,
        candidate={
            "reply": "你在模型方案上做了什么取舍？",
            "missing_points": ["模型选型取舍"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "next_probe_dimension": "tradeoff",
            "active_focus_topic": "LangChain",
        },
        fallback=fallback,
    )

    assert decision["next_probe_dimension"] == "implementation"
    assert len(decision["missing_points"]) == 1
    assert any(token in decision["missing_points"][0] for token in ["实现", "链路", "输入", "输出", "核心功能"])


def test_step4_coerce_advances_stage_when_stuck_on_same_dimension_for_too_many_turns():
    agent = _agent()
    payload = {
        "user_input": "继续补充：我们做了缓存和重试，整体更稳定。",
        "is_first_round": False,
        "followup_count": 3,
        "active_focus": {
            "topic": "智能模拟面试平台",
            "stage": "tradeoff",
            "evidence": {"implementation": True, "tradeoff": False, "validation": False},
            "turn_count": 2,
        },
    }
    fallback = agent._build_step4_heuristic_decision(payload)
    decision = agent._coerce_step4_single_focus_decision(
        payload=payload,
        candidate={
            "reply": "你在模型方案上做了什么取舍？",
            "missing_points": ["请继续补充取舍细节"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "next_probe_dimension": "tradeoff",
            "active_focus_topic": "智能模拟面试平台",
        },
        fallback=fallback,
    )

    assert decision["next_probe_dimension"] == "validation"
    assert decision["active_focus"]["stage"] == "validation"


def test_step4_runtime_auth_failure_retries_without_runtime_api_key(monkeypatch):
    ai_service = AIService()
    calls = []

    bad_decision = {
        "reply": "请继续补充",
        "resume_ready_draft": {"title": "项目经历", "role": "核心开发", "period": "时间待补", "bullets": []},
        "missing_points": ["核心功能是如何拆解并实现的（关键模块/调用链）"],
        "current_experience_completed": False,
        "ask_more_experience": True,
        "reasoning_focus": [],
        "model_connection_ok": False,
        "model_connection_error": "Error code: 401 - Authentication Fails (governor)",
    }
    good_decision = {
        "reply": "可上简历版本已整理。请再补充你是如何验证效果的；是否还有要补充的经历？",
        "resume_ready_draft": {"title": "Agentic RAG 面试官", "role": "核心开发", "period": "2025.01-2025.04", "bullets": ["优化接口延迟 42%"]},
        "missing_points": ["效果如何验证（压测口径/线上指标）", "是否还有要补充的经历"],
        "current_experience_completed": False,
        "ask_more_experience": True,
        "reasoning_focus": ["LangChain", "Flask"],
        "model_connection_ok": True,
        "model_connection_error": "",
    }

    class _FakeAgent:
        def __init__(self, decision):
            self._decision = decision

        def run_resume_craft_step4_decision(self, _payload):
            return self._decision

    def _fake_builder(runtime):
        calls.append(dict(runtime or {}))
        if runtime and str(runtime.get("api_key") or "").strip():
            return _FakeAgent(bad_decision)
        return _FakeAgent(good_decision)

    monkeypatch.setattr(ai_service, "_build_runtime_agent", _fake_builder)

    result = ai_service.run_resume_craft_step4_decision(
        payload={
            "user_input": "我做了一个 LangChain 项目",
            "fallback_reply": "请继续补充",
        },
        runtime={
            "mode": "platform",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "sk-invalid",
            "base_url": "https://api.deepseek.com/v1",
        },
    )

    assert len(calls) == 2
    assert str(calls[0].get("api_key") or "").strip() == "sk-invalid"
    assert str(calls[1].get("api_key") or "").strip() == ""
    assert result["model_connection_ok"] is True
