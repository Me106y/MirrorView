import pytest

from flask import Flask

from server import routes
from server.config import Config
from server.factories.llm_factory import ModelFactory
from server.services.careerforge_agent import CareerForgeAgent
from server.services.ai_service import AIService


def _client():
    app = Flask(__name__)
    app.register_blueprint(routes.api, url_prefix="/api")
    app.config["TESTING"] = True
    return app.test_client()


def _profile():
    return {
        "template_code": "02",
        "language": "zh",
        "photo_pref": "no_photo",
        "target_role": "AI 应用开发",
        "personal_info": {"name": "A", "phone": "1", "email": "a@example.com", "city": "上海", "links": []},
        "education": [],
        "skills": [],
        "certificates": [],
        "expected_experience_count": 1,
    }


def test_ai_service_defers_platform_llm_configuration_error(monkeypatch):
    error = "Did not find openai_api_key"
    monkeypatch.setattr(AIService, "_build_platform_llm", lambda self: (_ for _ in ()).throw(ValueError(error)))

    service = AIService()

    assert service.llm is None
    with pytest.raises(RuntimeError, match=error):
        service.run_resume_craft_chat_turn({"message": "继续"})


def test_resume_craft_runtime_allows_long_structured_agent_response(monkeypatch):
    captured = {}

    def fake_model(provider, model_name, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ModelFactory, "get_model", fake_model)
    service = object.__new__(AIService)

    service._build_runtime_agent(
        {
            "mode": "byok",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "test-key",
        }
    )

    assert captured["max_tokens"] >= 3000


def test_chat_turn_delegates_semantic_decision_to_agent(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False
    captured = {}

    def fake_agent(payload, runtime=None):
        captured.update(payload)
        return {
            "reply": "这段经历已经足够具体，可以继续补充下一段内容。",
            "action": "collect",
            "next_step_suggestion": "stay",
            "render_ready": False,
            "missing_fields": [],
            "wizard_state": {"current_step": 4},
        }

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_chat_turn", fake_agent)

    response = _client().post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我负责把检索、记忆和追问编排串成一条链路。",
            "current_step": 4,
            "history": [{"role": "user", "content": "上一轮信息"}],
            "step1_profile": _profile(),
            "wizard_state": {"current_step": 4},
        },
    )

    assert response.status_code == 200
    assert response.get_json()["reply"].startswith("这段经历")
    assert captured["message"].startswith("我负责")
    assert captured["current_step"] == 4
    assert captured["step1_profile"]["target_role"] == "AI 应用开发"


def test_chat_turn_returns_agent_failure_without_fixed_reply(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False
    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_chat_turn",
        lambda payload, runtime=None: (_ for _ in ()).throw(RuntimeError("model unavailable")),
    )

    response = _client().post(
        "/api/careerforge/resume-craft/chat-turn",
        json={"message": "继续分析", "step1_profile": _profile()},
    )

    assert response.status_code == 502
    body = response.get_json()
    assert body["error"] == "resume_craft_agent_failed"
    assert body["message"] == "model unavailable"


class _JsonModel:
    def __init__(self, output):
        self.output = output
        self.prompt = None
        self.calls = 0

    def invoke(self, prompt, **kwargs):
        self.calls += 1
        self.prompt = prompt
        return self.output

    def __call__(self, prompt):
        return self.invoke(prompt)


def test_agent_loads_skill_and_returns_structured_state():
    model = _JsonModel(
        '{"reply":"请具体说说你在这段经历中的关键决策。",'
        '"action":"collect","next_step_suggestion":"stay",'
        '"render_ready":false,"missing_fields":["decision"],'
        '"wizard_state":{"current_step":4},"step6_preview_markdown":"",'
        '"step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        {
            "message": "我做了一个检索服务。",
            "current_step": 4,
            "step1_profile": _profile(),
            "wizard_state": {"current_step": 4},
            "history": [],
        }
    )

    assert result["reply"].startswith("请具体说说")
    assert "Skill Specification" in str(model.prompt)
    assert "不要按固定轮数" in str(model.prompt)


def test_agent_merges_compact_state_patch_after_user_has_no_more_experience():
    model = _JsonModel(
        '{"reply":"好的，这段经历已记录。请点击页面的“下一步”，我们继续整理技能与证书。",'
        '"action":"advance","next_step_suggestion":"next",'
        '"render_ready":false,"missing_fields":[],'
        '"wizard_state":{"step_states":{"step4":{"confirmed":true}}},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    existing_state = {
        "current_step": 4,
        "collected_by_step": {"experiences": ["完整经历事实"], "skills_and_certs": []},
        "chat_history_by_step": {"step4": ["很长的历史"], "step5": []},
        "step_states": {"step4": {"confirmed": False, "drafts": ["保留草稿"]}},
    }
    agent = CareerForgeAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        {
            "message": "没有",
            "current_step": 4,
            "step1_profile": _profile(),
            "wizard_state": existing_state,
            "history": [{"role": "assistant", "content": "如果没有，我们可以进入下一步。"}],
        }
    )

    assert "下一步" in result["reply"]
    assert result["wizard_state"]["collected_by_step"]["experiences"] == ["完整经历事实"]
    assert result["wizard_state"]["step_states"]["step4"]["confirmed"] is True
    assert result["wizard_state"]["step_states"]["step4"]["drafts"] == ["保留草稿"]
    assert "minimal" in str(model.prompt)
    assert "自行点击" in str(model.prompt)


def test_agent_prompt_prevents_repeating_answered_grill_questions():
    model = _JsonModel(
        '{"reply":"信息已记录，请继续下一步。","action":"advance",'
        '"next_step_suggestion":"next","render_ready":false,"missing_fields":[], '
        '"wizard_state":{},"step6_preview_markdown":"",'
        '"step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)

    agent.run_resume_craft_chat_turn(
        {
            "message": "没有其他补充了",
            "current_step": 4,
            "step1_profile": _profile(),
            "wizard_state": {"current_step": 4},
            "history": [
                {"role": "assistant", "content": "请确认文档数量和RAG过滤逻辑。"},
                {"role": "user", "content": "已经说明了3050份文档和Jaccard过滤，其他没有了。"},
            ],
        }
    )

    prompt = str(model.prompt)
    assert "不得重复" in prompt
    assert "已回答" in prompt
    assert "没有其他补充" in prompt


def test_agent_closes_experience_when_user_has_no_more_to_add():
    model = _JsonModel(
        '{"reply":"这段经历已整理完成。若还有其他经历可以继续描述；如果没有，请点击“下一步”进入技能与证书。",'
        '"action":"advance","next_step_suggestion":"next","render_ready":false,'
        '"missing_fields":[],"wizard_state":{"collected_by_step":{"experiences":['
        '"独立开发 AI 面试官，负责 RAG、性能优化和实时旁听。"]},"step_states":{"step4":{'
        '"finalized_experiences":["独立开发 AI 面试官，负责 RAG、性能优化和实时旁听。"],'
        '"missing_fields":[],"active_focus":{"stage":"done"}}}},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        {
            "message": "没有更多了",
            "current_step": 4,
            "step1_profile": _profile(),
            "wizard_state": {
                "current_step": 4,
                "collected_by_step": {"experiences": []},
                "step_states": {"step4": {"finalized_experiences": [], "active_focus": {"stage": "validation"}}},
            },
            "history": [
                {"role": "user", "content": "我负责独立开发 AI 面试官，完成 RAG、性能优化和实时旁听。"},
                {"role": "assistant", "content": "还需要补充其他内容吗？"},
            ],
        }
    )

    assert result["wizard_state"]["step_states"]["step4"]["active_focus"]["stage"] == "done"
    assert result["wizard_state"]["step_states"]["step4"]["finalized_experiences"]
    assert "finalized_experiences" in str(model.prompt)
    assert "结束当前经历" in str(model.prompt)


def test_agent_step5_preview_returns_structured_summary_without_render_ready():
    model = _JsonModel(
        '{"reply":"我已整理出简历摘要，请确认是否需要修改。",'
        '"action":"preview","next_step_suggestion":"stay","render_ready":false,'
        '"missing_fields":[],"wizard_state":{"step_states":{"step6":{'
        '"preview_ready":true,"awaiting_confirm":true,"confirmed":false,'
        '"draft_json":{"target_role":"AI应用开发","experiences":["负责RAG应用开发"]},'
        '"preview_markdown":"# 简历摘要\\n\\n- 目标岗位：AI应用开发"}},'
        '"collected_by_step":{"step6_confirmed":false}},'
        '"step6_preview_markdown":"# 简历摘要\\n\\n- 目标岗位：AI应用开发",'
        '"step6_waiting_confirm":true,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        {
            "message": "请生成简历预览",
            "current_step": 6,
            "step1_profile": _profile(),
            "wizard_state": {"current_step": 6, "step_states": {"step6": {"draft_json": {}}}},
            "history": [],
        }
    )

    step6 = result["wizard_state"]["step_states"]["step6"]
    assert result["action"] == "preview"
    assert result["render_ready"] is False
    assert result["step6_waiting_confirm"] is True
    assert step6["preview_ready"] is True
    assert step6["draft_json"]["target_role"] == "AI应用开发"
    assert "结构化" in str(model.prompt)
    assert "step6_preview_markdown" in str(model.prompt)


def test_agent_step5_revision_keeps_generation_locked_until_confirmation():
    model = _JsonModel(
        '{"reply":"已按你的要求更新摘要，请再次确认是否需要修改。",'
        '"action":"revise","next_step_suggestion":"stay","render_ready":false,'
        '"missing_fields":[],"wizard_state":{"step_states":{"step6":{'
        '"preview_ready":true,"awaiting_confirm":true,"confirmed":false,'
        '"draft_json":{"target_role":"AI应用开发","final_preferences":"突出项目成果"},'
        '"revision_count":1}},"collected_by_step":{"step6_confirmed":false}},'
        '"step6_preview_markdown":"# 简历摘要\\n\\n- 重点：项目成果",'
        '"step6_waiting_confirm":true,"step6_applied_changes":["突出项目成果"]}'
    )
    agent = CareerForgeAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        {
            "message": "请突出项目成果",
            "current_step": 6,
            "step1_profile": _profile(),
            "wizard_state": {
                "current_step": 6,
                "step_states": {"step6": {"draft_json": {"target_role": "AI应用开发"}, "revision_count": 0}},
            },
            "history": [{"role": "assistant", "content": "是否需要修改？"}],
        }
    )

    assert result["action"] == "revise"
    assert result["render_ready"] is False
    assert result["wizard_state"]["step_states"]["step6"]["revision_count"] == 1
    assert result["wizard_state"]["collected_by_step"]["step6_confirmed"] is False


def test_agent_step5_confirmation_unlocks_generation():
    model = _JsonModel(
        '{"reply":"内容已确认，可以点击“生成简历”生成最终文件。",'
        '"action":"confirm","next_step_suggestion":"stay","render_ready":true,'
        '"missing_fields":[],"wizard_state":{"step_states":{"step6":{'
        '"preview_ready":true,"awaiting_confirm":false,"confirmed":true,'
        '"draft_json":{"target_role":"AI应用开发"}}},'
        '"collected_by_step":{"step6_confirmed":true}},'
        '"step6_preview_markdown":"# 简历摘要","step6_waiting_confirm":false,'
        '"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        {
            "message": "没有修改了，确认生成",
            "current_step": 6,
            "step1_profile": _profile(),
            "wizard_state": {
                "current_step": 6,
                "step_states": {"step6": {"preview_ready": True, "awaiting_confirm": True}},
                "collected_by_step": {"step6_confirmed": False},
            },
            "history": [{"role": "assistant", "content": "是否需要修改？"}],
        }
    )

    assert result["action"] == "confirm"
    assert result["render_ready"] is True
    assert result["wizard_state"]["collected_by_step"]["step6_confirmed"] is True
    assert result["wizard_state"]["step_states"]["step6"]["confirmed"] is True


def test_agent_exposes_invalid_json_without_repair_retry():
    model = _JsonModel("```json\n{\"reply\": \"需要修复\"}\n```")
    agent = CareerForgeAgent(llm=model)

    with pytest.raises(RuntimeError, match="invalid JSON"):
        agent.run_resume_craft_chat_turn(
            {
                "message": "我做了一个检索服务。",
                "current_step": 4,
                "step1_profile": _profile(),
                "wizard_state": {},
                "history": [],
            }
        )

    assert model.calls == 1
