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

    assert captured["max_tokens"] >= 8000


def test_resume_craft_runtime_does_not_force_json_for_html_render(monkeypatch):
    captured = {}

    def fake_model(provider, model_name, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ModelFactory, "get_model", fake_model)
    monkeypatch.setattr(
        CareerForgeAgent,
        "run_resume_craft_html",
        lambda self, payload: "<!DOCTYPE html><html><body>ok</body></html>",
    )
    service = object.__new__(AIService)

    result = service.run_resume_craft_html(
        {},
        runtime={
            "mode": "byok",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "test-key",
        },
    )

    assert "<!DOCTYPE html>" in result
    assert "response_format" not in captured


def test_platform_runtime_allows_full_resume_html_response(monkeypatch):
    captured = {}

    def fake_model(provider, model_name, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ModelFactory, "get_model", fake_model)
    service = object.__new__(AIService)

    service._build_platform_llm()

    assert captured["max_tokens"] >= 8000
    assert captured["timeout"] >= 90


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
    assert "至少 2 轮" in str(model.prompt)
    assert "最多 3 轮" in str(model.prompt)


def test_resume_craft_agent_accepts_fenced_json_response():
    model = _JsonModel(
        '```json\n'
        '{"reply":"已收到这段经历，请继续补充关键结果。",'
        '"action":"collect","next_step_suggestion":"stay",'
        '"render_ready":false,"missing_fields":["result"],'
        '"wizard_state":{"current_step":4},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,'
        '"step6_applied_changes":[]}\n'
        '```'
    )
    agent = CareerForgeAgent(llm=model)

    result = agent.run_resume_craft_chat_turn({
        "message": "我负责实现面试问答服务。",
        "current_step": 4,
        "step1_profile": _profile(),
        "wizard_state": {"current_step": 4},
        "history": [],
    })

    assert result["reply"].startswith("已收到这段经历")


def test_step3_chat_route_does_not_turn_fenced_agent_json_into_502(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False
    agent = CareerForgeAgent(
        llm=_JsonModel(
            '```json\n'
            '{"reply":"已收到这段经历，请继续补充关键结果。",'
            '"action":"collect","next_step_suggestion":"stay",'
            '"render_ready":false,"missing_fields":["result"],'
            '"wizard_state":{"current_step":4},'
            '"step6_preview_markdown":"","step6_waiting_confirm":false,'
            '"step6_applied_changes":[]}\n'
            '```'
        )
    )
    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_chat_turn",
        lambda payload, runtime=None: agent.run_resume_craft_chat_turn(payload),
    )

    response = _client().post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我负责实现面试问答服务。",
            "current_step": 4,
            "history": [{"role": "assistant", "content": "请描述一段经历。", "backendStep": 4}],
            "step1_profile": _profile(),
            "wizard_state": {"current_step": 4},
            "runtime": {"mode": "byok", "provider": "deepseek", "model": "deepseek-chat", "api_key": "test-key"},
        },
    )

    assert response.status_code == 200
    assert response.get_json()["reply"].startswith("已收到这段经历")


def test_step3_chat_route_recovers_when_model_omits_state(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False
    agent = CareerForgeAgent(llm=_JsonModel('{"reply":"已收到项目描述。"}'))
    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_chat_turn",
        lambda payload, runtime=None: agent.run_resume_craft_chat_turn(payload),
    )

    response = _client().post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "基于 LangChain 和 Agentic RAG 构建 AI 面试官，使用 Flask 和 SQLAlchemy，接口响应时间降低 42%。",
            "current_step": 4,
            "history": [],
            "step1_profile": _profile(),
            "wizard_state": {"current_step": 4},
            "runtime": {"mode": "byok", "provider": "deepseek", "model": "deepseek-chat", "api_key": "test-key"},
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["reply"] == "已收到项目描述。"
    assert body["wizard_state"]["current_step"] == 4


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
    assert "自动切换阶段" in str(model.prompt)


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
    assert "已解决事实维度账本" in prompt
    assert "同义" in prompt


def test_agent_prompt_adapts_technical_grill_to_project_domain():
    model = _JsonModel(
        '{"reply":"请继续补充技术细节。","action":"collect",'
        '"next_step_suggestion":"stay","render_ready":false,"missing_fields":[], '
        '"wizard_state":{},"step6_preview_markdown":"",'
        '"step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)

    agent.run_resume_craft_chat_turn(
        {
            "message": "项目负责实时音视频通话，后端处理房间和媒体流，使用 WebRTC 建立连接并通过 RTMP 推流。",
            "current_step": 4,
            "step1_profile": {**_profile(), "target_role": "音视频后端开发"},
            "wizard_state": {"current_step": 4},
            "history": [
                {"role": "assistant", "content": "是否使用过 WebRTC 或 RTMP？"},
                {"role": "user", "content": "确认使用过 WebRTC 和 RTMP，这部分已经说明。"},
            ],
        }
    )

    prompt = str(model.prompt)
    assert "根据项目描述、目标岗位和 JD" in prompt
    assert "1-3 个相关问题" in prompt
    assert "RTMP" in prompt
    assert "WebRTC" in prompt
    for domain_example in ("AI/RAG", "后端/分布式", "前端", "数据", "DevOps"):
        assert domain_example in prompt
    assert "候选技术" in prompt
    assert "用户确认前不得把候选技术" in prompt
    assert "不得把音视频示例套用到" in prompt
    assert "完整 history" in prompt


def test_agent_prompt_requires_question_level_grill_state_and_two_round_minimum():
    model = _JsonModel(
        '{"reply":"继续补充。","action":"collect","next_step_suggestion":"stay",'
        '"render_ready":false,"missing_fields":[],"wizard_state":{},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)
    agent.run_resume_craft_chat_turn({
        "message": "继续。",
        "current_step": 4,
        "step1_profile": _profile(),
        "wizard_state": {"current_step": 4},
        "history": [],
    })
    prompt = str(model.prompt)
    assert "pending_questions" in prompt
    assert "completed_rounds" in prompt
    assert "至少 2 轮" in prompt
    assert "最多 3 轮" in prompt
    assert "user_skipped" in prompt


def test_agent_grill_keeps_round_open_until_every_question_is_answered():
    model = _JsonModel(
        '{"reply":"已记录前三项，请继续补充第4项。","action":"collect",'
        '"next_step_suggestion":"stay","render_ready":false,"missing_fields":[], '
        '"wizard_state":{"step_states":{"step4":{"active_focus":{"grill":{'
        '"completed_rounds":0,"round_status":"awaiting_answers",'
        '"pending_questions":['
        '{"id":"q1","text":"项目背景？","dimension":"context","status":"answered"},'
        '{"id":"q2","text":"你的职责？","dimension":"role","status":"answered"},'
        '{"id":"q3","text":"采取了什么行动？","dimension":"action","status":"answered"},'
        '{"id":"q4","text":"结果如何？","dimension":"result","status":"open"}]}}}}},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)
    existing_state = {
        "current_step": 4,
        "step_states": {"step4": {"active_focus": {"grill": {
            "completed_rounds": 0,
            "round_status": "awaiting_answers",
            "pending_questions": [
                {"id": "q1", "text": "项目背景？", "dimension": "context", "status": "open"},
                {"id": "q2", "text": "你的职责？", "dimension": "role", "status": "open"},
                {"id": "q3", "text": "采取了什么行动？", "dimension": "action", "status": "open"},
                {"id": "q4", "text": "结果如何？", "dimension": "result", "status": "open"},
            ],
        }}}},
    }

    result = agent.run_resume_craft_chat_turn({
        "message": "前三项我都已经回答了，结果还需要补充。",
        "current_step": 4,
        "step1_profile": _profile(),
        "wizard_state": existing_state,
        "history": [],
    })

    grill = result["wizard_state"]["step_states"]["step4"]["active_focus"]["grill"]
    assert grill["completed_rounds"] == 0
    assert grill["round_status"] == "awaiting_answers"
    assert [item["id"] for item in grill["pending_questions"] if item["status"] == "open"] == ["q4"]
    assert result["next_step_suggestion"] == "stay"


def test_agent_grill_completes_a_round_only_after_all_questions_close():
    model = _JsonModel(
        '{"reply":"第1轮已完成，我们继续下一轮。","action":"collect",'
        '"next_step_suggestion":"stay","render_ready":false,"missing_fields":[], '
        '"wizard_state":{"step_states":{"step4":{"active_focus":{"grill":{'
        '"completed_rounds":1,"round_status":"round_completed",'
        '"pending_questions":['
        '{"id":"q1","text":"项目背景？","dimension":"context","status":"answered"},'
        '{"id":"q2","text":"你的职责？","dimension":"role","status":"answered"}]}}}}},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)
    result = agent.run_resume_craft_chat_turn({
        "message": "第2个问题也补充完了。",
        "current_step": 4,
        "step1_profile": _profile(),
        "wizard_state": {"current_step": 4, "step_states": {"step4": {"active_focus": {"grill": {
            "completed_rounds": 0,
            "round_status": "awaiting_answers",
            "pending_questions": [
                {"id": "q1", "text": "项目背景？", "dimension": "context", "status": "open"},
                {"id": "q2", "text": "你的职责？", "dimension": "role", "status": "open"},
            ],
        }}}}},
        "history": [],
    })
    grill = result["wizard_state"]["step_states"]["step4"]["active_focus"]["grill"]
    assert grill["completed_rounds"] == 1
    assert grill["round_status"] == "round_completed"


def test_agent_grill_does_not_finish_before_two_rounds():
    model = _JsonModel(
        '{"reply":"这段经历已经完成。","action":"advance",'
        '"next_step_suggestion":"next","render_ready":false,"missing_fields":[], '
        '"wizard_state":{"step_states":{"step4":{"active_focus":{"stage":"done", "grill":{'
        '"completed_rounds":1,"round_status":"project_completed",'
        '"pending_questions":[]}}}}},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)
    result = agent.run_resume_craft_chat_turn({
        "message": "这一轮没有更多补充了。",
        "current_step": 4,
        "step1_profile": _profile(),
        "wizard_state": {"current_step": 4, "step_states": {"step4": {"active_focus": {"stage": "validation", "grill": {
            "completed_rounds": 1,
            "round_status": "round_completed",
            "pending_questions": [],
        }}}}},
        "history": [],
    })
    focus = result["wizard_state"]["step_states"]["step4"]["active_focus"]
    assert focus["stage"] != "done"
    assert focus["grill"]["round_status"] != "project_completed"
    assert result["next_step_suggestion"] == "stay"


def test_agent_grill_does_not_finish_with_open_questions_even_at_round_limit():
    model = _JsonModel(
        '{"reply":"还有一个问题需要确认。","action":"advance",'
        '"next_step_suggestion":"next","render_ready":false,"missing_fields":[], '
        '"wizard_state":{"step_states":{"step4":{"active_focus":{"stage":"done", "grill":{'
        '"completed_rounds":3,"round_status":"project_completed",'
        '"pending_questions":[{"id":"q4","text":"结果如何？","dimension":"result","status":"open"}]}}}}},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)
    result = agent.run_resume_craft_chat_turn({
        "message": "还需要确认结果。",
        "current_step": 4,
        "step1_profile": _profile(),
        "wizard_state": {"current_step": 4, "step_states": {"step4": {"active_focus": {"stage": "validation", "grill": {
            "completed_rounds": 3,
            "round_status": "awaiting_answers",
            "pending_questions": [{"id": "q4", "text": "结果如何？", "dimension": "result", "status": "open"}],
        }}}}},
        "history": [],
    })
    focus = result["wizard_state"]["step_states"]["step4"]["active_focus"]
    assert focus["stage"] != "done"
    assert focus["grill"]["completed_rounds"] == 3
    assert focus["grill"]["round_status"] == "awaiting_answers"
    assert result["next_step_suggestion"] == "stay"


def test_agent_grill_allows_semantic_skip_of_current_project():
    model = _JsonModel(
        '{"reply":"好的，跳过这段经历的继续深挖。","action":"advance",'
        '"next_step_suggestion":"next","render_ready":false,"missing_fields":[], '
        '"wizard_state":{"step_states":{"step4":{"active_focus":{"stage":"done", "grill":{'
        '"completed_rounds":0,"user_skipped":true,"round_status":"skipped",'
        '"pending_questions":[]}}}}},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)
    result = agent.run_resume_craft_chat_turn({
        "message": "我不想继续回答这段项目的追问了，先跳过。",
        "current_step": 4,
        "step1_profile": _profile(),
        "wizard_state": {"current_step": 4, "step_states": {"step4": {"active_focus": {"stage": "implementation", "grill": {
            "completed_rounds": 0,
            "round_status": "awaiting_answers",
            "pending_questions": [{"id": "q1", "text": "项目结果？", "dimension": "result", "status": "open"}],
        }}}}},
        "history": [],
    })
    grill = result["wizard_state"]["step_states"]["step4"]["active_focus"]["grill"]
    assert grill["user_skipped"] is True
    assert grill["round_status"] == "skipped"
    assert result["wizard_state"]["step_states"]["step4"]["active_focus"]["stage"] == "done"


def test_agent_render_ready_adds_generation_guidance_when_model_omits_it():
    model = _JsonModel(
        '{"reply":"预览内容没有问题。","action":"confirm",'
        '"next_step_suggestion":"stay","render_ready":true,"missing_fields":[], '
        '"wizard_state":{"step_states":{"step6":{"confirmed":true,"awaiting_confirm":false,'
        '"draft_json":{"target_role":"AI应用开发"}}},"collected_by_step":{"step6_confirmed":true}},'
        '"step6_preview_markdown":"# 简历摘要","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)
    result = agent.run_resume_craft_chat_turn({
        "message": "确认预览内容。",
        "current_step": 6,
        "step1_profile": _profile(),
        "wizard_state": {"current_step": 6},
        "history": [],
    })
    assert "点击“生成简历”" in result["reply"]


def test_agent_does_not_unlock_step6_from_step5_confirmation():
    model = _JsonModel(
        '{"reply":"好的，已确认无需修改。请点击“生成简历”按钮。",'
        '"action":"render_ready","next_step_suggestion":"next","render_ready":true,'
        '"missing_fields":[],"wizard_state":{"step_states":{"step6":{'
        '"confirmed":true,"awaiting_confirm":false,"draft_json":{"target_role":"AI应用开发"}}},'
        '"collected_by_step":{"step6_confirmed":true}},"step6_preview_markdown":"# 摘要",'
        '"step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)

    result = agent.run_resume_craft_chat_turn({
        "message": "不用修改。",
        "current_step": 5,
        "step1_profile": _profile(),
        "wizard_state": {
            "current_step": 5,
            "collected_by_step": {"step6_confirmed": False},
            "step_states": {"step6": {"confirmed": False, "awaiting_confirm": True}},
        },
        "history": [],
    })

    assert result["render_ready"] is False
    assert result["wizard_state"]["collected_by_step"]["step6_confirmed"] is False
    assert result["wizard_state"]["step_states"]["step6"]["confirmed"] is False
    assert "current_step=6" in str(model.prompt)
    assert "current_step=5" in str(model.prompt)


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


def test_agent_render_ready_normalizes_step6_confirmation_state():
    model = _JsonModel(
        '{"reply":"预览已确认，可以生成简历。",'
        '"action":"confirm","next_step_suggestion":"stay","render_ready":true,'
        '"missing_fields":[],"wizard_state":{"step_states":{"step6":{'
        '"draft_json":{"target_role":"AI应用开发"}}}},'
        '"step6_preview_markdown":"# 简历摘要",'
        '"step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = CareerForgeAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        {
            "message": "没有问题，确认生成",
            "current_step": 6,
            "step1_profile": _profile(),
            "wizard_state": {
                "current_step": 6,
                "collected_by_step": {"step6_confirmed": False},
                "step_states": {"step6": {"preview_ready": True, "awaiting_confirm": True}},
            },
            "history": [{"role": "assistant", "content": "是否需要修改？"}],
        }
    )

    step6 = result["wizard_state"]["step_states"]["step6"]
    assert result["render_ready"] is True
    assert result["wizard_state"]["collected_by_step"]["step6_confirmed"] is True
    assert step6["confirmed"] is True
    assert step6["awaiting_confirm"] is False


def test_agent_recovers_structurally_incomplete_json_response():
    model = _JsonModel("```json\n{\"reply\": \"需要修复\"}\n```")
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

    assert model.calls == 1
    assert result["reply"] == "需要修复"
    assert result["wizard_state"]["current_step"] == 4
