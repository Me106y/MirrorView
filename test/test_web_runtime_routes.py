from flask import Flask

from server import routes
from server.config import Config


def _client():
    app = Flask(__name__)
    app.register_blueprint(routes.api, url_prefix="/api")
    app.config["TESTING"] = True
    return app.test_client()


def test_resume_match_returns_403_without_turnstile_when_enforced(monkeypatch):
    Config.TURNSTILE_ENFORCE = True
    Config.TURNSTILE_SECRET_KEY = "dummy"
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr("server.security.verify_turnstile_token", lambda token, remote_ip: (False, "missing_turnstile_token"))

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-match",
        json={"resume_text": "resume", "jd_text": "jd"},
    )
    assert resp.status_code == 403


def test_resume_match_returns_400_for_invalid_runtime(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(routes.ai_service, "run_resume_match", lambda payload, runtime=None: {"ok": True})

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-match",
        json={
            "resume_text": "resume",
            "jd_text": "jd",
            "runtime": {"mode": "byok", "provider": "openai"},
        },
    )
    assert resp.status_code == 400


def test_resume_match_still_works_without_runtime_payload(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(routes.ai_service, "run_resume_match", lambda payload, runtime=None: {"overall_score": 80})

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-match",
        json={"resume_text": "resume", "jd_text": "jd"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["result"]["overall_score"] == 80
    assert body["meta"]["runtime_mode"] == "platform"


def test_resume_craft_chat_turn_returns_400_for_empty_message():
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    client = _client()
    resp = client.post("/api/careerforge/resume-craft/chat-turn", json={"message": "   "})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "empty_message"
    assert body["intent"] == "resume-craft"
    assert body["render_ready"] is False
    assert "message" in body["missing_fields"]


def test_resume_craft_chat_turn_returns_reply(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_dialog", lambda payload, runtime=None: "先补充教育背景和项目经历。")

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我想做一份 AI 应用开发简历",
            "history": [{"role": "assistant", "content": "请先说明你的目标岗位。"}],
            "template_code": "02",
            "language": "zh",
            "photo_pref": "no_photo",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["intent"] == "resume-craft"
    assert body["action"] == "chat_turn"
    assert "教育背景" in body["reply"]
    assert body["render_ready"] is False
    assert "conversation_turns" in body["missing_fields"]


def test_resume_craft_chat_turn_returns_ready_when_required_fields_present(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_dialog", lambda payload, runtime=None: "信息已足够。")

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "联系方式补充：邮箱 a@b.com，电话 13800000000。",
            "history": [
                {"role": "assistant", "content": "请介绍背景。"},
                {
                    "role": "user",
                    "content": "目标岗位是 AI 应用开发。教育背景：清华大学计算机硕士。"
                    "工作项目经历：负责 RAG 平台。技能：Python、LangChain。",
                },
            ],
            "template_code": "02",
            "language": "zh",
            "photo_pref": "with_photo",
            "photo_uploaded": True,
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["render_ready"] is True
    assert body["missing_fields"] == []


def test_resume_craft_chat_turn_rewrites_target_role_reask_when_role_already_provided(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_dialog",
        lambda payload, runtime=None: "我已收到你的信息。请先补充目标岗位这个字段。",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "AI应用开发",
            "history": [{"role": "assistant", "content": "我们先从第一个字段开始：请告诉我你的目标岗位。"}],
            "template_code": "02",
            "language": "zh",
            "photo_pref": "no_photo",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "目标岗位" not in body["missing_fields"]
    assert "教育背景" in body["reply"]


def test_resume_craft_chat_turn_forces_role_capture_when_last_assistant_asks_role(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_dialog",
        lambda payload, runtime=None: "我已收到你的信息。请先补充目标岗位这个字段。",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "AI应用开发",
            "history": [{"role": "assistant", "content": "我们先从第一个字段开始：请告诉我你的目标岗位。"}],
            "template_code": "02",
            "language": "zh",
            "photo_pref": "no_photo",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "target_role" not in body["missing_fields"]
    assert "教育背景" in body["reply"]
    assert body["meta"]["resume_craft_chat_turn_version"] == "2026-07-07-v5"


def test_resume_craft_chat_turn_step1_profile_experience_only(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_dialog",
        lambda payload, runtime=None: "请继续补充教育背景。",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我负责搭建 RAG 检索服务。",
            "history": [{"role": "assistant", "content": "请描述第一段经历。"}],
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [{"school": "X", "major": "CS", "degree": "硕士", "period": "2020-2023", "highlights": ""}],
                "skills": ["Python"],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "experience_state": {"current_index": 1, "followup_count": 0, "drafts": [], "finalized_experiences": []},
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] in {"grill_experience", "experience_done", "confirm_finalize"}
    assert "experience_state" in body
    assert "教育背景" not in body["reply"]
    assert body["meta"]["resume_craft_chat_turn_version"] == "2026-07-09-v8"


def test_resume_craft_chat_turn_step1_profile_auto_finalize_after_max_grill(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_dialog",
        lambda payload, runtime=None: "请补充经历结果与量化指标。",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "结果是响应时延降低 35%。",
            "history": [{"role": "assistant", "content": "请补充挑战和行动。"}],
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [{"school": "X", "major": "CS", "degree": "硕士", "period": "2020-2023", "highlights": ""}],
                "skills": ["Python"],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "experience_state": {
                "current_index": 1,
                "followup_count": 2,
                "drafts": ["我负责搭建 RAG 检索服务。", "挑战是并发抖动明显。"],
                "finalized_experiences": [],
            },
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["render_ready"] is False
    assert body["action"] == "experience_done"
    assert body["experience_state"]["finalized_experiences"]
    assert "还有要补充的项目" in body["reply"]


def test_resume_craft_chat_turn_step4_no_more_experience_goes_next(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_dialog",
        lambda payload, runtime=None: "好的，我们继续下一阶段。",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "没有更多项目了",
            "current_step": 4,
            "history": [{"role": "assistant", "content": "这一段经历已完成深挖。请问还有要补充的项目/经历吗？"}],
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [{"school": "X", "major": "CS", "degree": "硕士", "period": "2020-2023", "highlights": ""}],
                "skills": ["Python"],
                "certificates": [],
                "expected_experience_count": 2,
            },
            "experience_state": {
                "current_index": 2,
                "followup_count": 0,
                "drafts": [],
                "finalized_experiences": ["项目A：负责RAG平台，时延降低35%。"],
            },
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "experience_done"
    assert body["next_step_suggestion"] == "next"
    assert body["missing_fields"] == []
    assert "进入下一阶段" in body["reply"]


def test_resume_craft_chat_turn_step4_fallback_focuses_on_missing_metric(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    # Return off-topic response so server falls back to its rule-based Grill question.
    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_dialog",
        lambda payload, runtime=None: "好的，继续。",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我负责重构召回链路，挑战是高并发下稳定性差，最终把可用性提升到了更高水平。",
            "current_step": 4,
            "history": [{"role": "assistant", "content": "请补充挑战和行动。"}],
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [{"school": "X", "major": "CS", "degree": "硕士", "period": "2020-2023", "highlights": ""}],
                "skills": ["Python"],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "experience_state": {
                "current_index": 1,
                "followup_count": 1,
                "drafts": ["项目背景：负责构建在线推理服务。"],
                "finalized_experiences": [],
            },
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "grill_experience"
    assert ("量化" in body["reply"]) or ("数字" in body["reply"])


def test_resume_craft_chat_turn_step4_avoids_repeating_generic_challenge_prompt(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    generic = "我已收到你的信息。这段经历很关键。请补充你遇到的挑战/难点，并说明它与“AI应用开发”岗位能力的关系。"
    monkeypatch.setattr(routes.ai_service, "run_resume_craft_dialog", lambda payload, runtime=None: generic)

    client = _client()
    first = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "基于 LangChain 与 Agentic RAG 架构，构建具备思维链能力的 AI 面试官，P95 响应时间降低 42%。",
            "current_step": 4,
            "history": [{"role": "assistant", "content": "我们进入 Step4（工作/项目经历）。请描述第一段经历的场景、职责、行动和结果。"}],
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [{"school": "X", "major": "CS", "degree": "硕士", "period": "2020-2023", "highlights": ""}],
                "skills": ["Python", "LangChain"],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "experience_state": {"current_index": 1, "followup_count": 0, "drafts": [], "finalized_experiences": []},
        },
    )
    assert first.status_code == 200
    first_body = first.get_json()
    exp_state = first_body["experience_state"]

    second_history = [
        {"role": "assistant", "content": "我们进入 Step4（工作/项目经历）。请描述第一段经历的场景、职责、行动和结果。"},
        {"role": "user", "content": "基于 LangChain 与 Agentic RAG 架构，构建具备思维链能力的 AI 面试官，P95 响应时间降低 42%。"},
        {"role": "assistant", "content": generic},
    ]
    second = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我主要负责 Few-shot Prompt、Temperature 调优、SQLAlchemy 会话恢复和 JWT 权限控制，系统已在30余场真实面试试运行。",
            "current_step": 4,
            "history": second_history,
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [{"school": "X", "major": "CS", "degree": "硕士", "period": "2020-2023", "highlights": ""}],
                "skills": ["Python", "LangChain"],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "experience_state": exp_state,
        },
    )
    assert second.status_code == 200
    body = second.get_json()
    assert body["action"] == "grill_experience"
    assert body["reply"] != generic
    assert "挑战" in body["reply"]
    assert ("LangChain" in body["reply"]) or ("Prompt" in body["reply"]) or ("会话恢复" in body["reply"])


def test_resume_craft_chat_turn_step4_first_round_returns_resume_ready_draft(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_dialog", lambda payload, runtime=None: "好的，继续。")

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": (
                "Mirrorview智能模拟面试平台\n"
                "基于 LangChain 与 Agentic RAG 架构，构建具备思维链能力的 AI 面试官。"
                "使用 Few-shot 技巧设计 Prompt，通过工厂模式对接 DeepSeek 模型并调优 Temperature 参数；"
                "利用数据库实现长上下文记忆与会话恢复。后端基于 Flask + SQLAlchemy，"
                "面试历史查询接口响应时间降低 42%。支持实时视频旁听与 JWT 权限控制。独立开发。"
            ),
            "current_step": 4,
            "history": [{"role": "assistant", "content": "我们进入 Step4（工作/项目经历）。请描述第一段经历的场景、职责、行动和结果。"}],
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [{"school": "X", "major": "CS", "degree": "硕士", "period": "2020-2023", "highlights": ""}],
                "skills": ["Python", "LangChain"],
                "certificates": [],
                "expected_experience_count": 2,
            },
            "experience_state": {"current_index": 1, "followup_count": 0, "drafts": [], "finalized_experiences": []},
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "grill_experience"
    assert "可上简历版本" in body["reply"]
    assert "Mirrorview智能模拟面试平台" in body["reply"]
    assert "请再补 3 个点" in body["reply"]
    assert "项目起止时间" in body["reply"]
    assert "还有没有第 2 段相关经历" in body["reply"]
    assert "请补充你遇到的挑战/难点" not in body["reply"]


def test_resume_craft_chat_turn_step3_only_education(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_dialog",
        lambda payload, runtime=None: "请继续补充教育背景中的专业和学位。",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "本科是计算机科学，硕士是软件工程。",
            "current_step": 3,
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [],
                "skills": [],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "wizard_state": {"current_step": 3},
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "collect_education"
    assert "education" in body["missing_fields"] or body["missing_fields"] == []
    assert "wizard_state" in body


def test_resume_craft_render_requires_step6_confirmation_with_wizard_state(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_html",
        lambda payload, runtime=None: "<!DOCTYPE html><html><body><h1>Resume</h1></body></html>",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [],
                "skills": [],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "wizard_state": {
                "current_step": 6,
                "collected_by_step": {
                    "education": ["X大学 计算机 硕士 2020-2023"],
                    "experiences": ["负责RAG平台建设，时延降低35%"],
                    "skills_and_certs": ["Python, LangChain"],
                    "final_preferences": "",
                    "step6_confirmed": False,
                },
                "chat_history_by_step": {"step3": [], "step4": [], "step5": [], "step6": []},
                "step_states": {
                    "step3": {"turn_count": 2, "confirmed": True},
                    "step4": {"current_index": 2, "followup_count": 0, "drafts": [], "finalized_experiences": ["负责RAG平台建设，时延降低35%"]},
                    "step5": {"turn_count": 2, "confirmed": True},
                    "step6": {"turn_count": 1, "confirmed": False},
                },
            },
        },
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "not_ready_for_render"


def test_resume_craft_render_works_with_step1_profile_and_finalized_experiences(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_html",
        lambda payload, runtime=None: "<!DOCTYPE html><html><body><h1>Resume</h1></body></html>",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "A", "phone": "1", "email": "a@b.com", "city": "上海", "links": []},
                "education": [{"school": "X", "major": "CS", "degree": "硕士", "period": "2020-2023", "highlights": ""}],
                "skills": ["Python"],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "finalized_experiences": ["我负责搭建 RAG 检索服务，将响应时延降低 35%。"],
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "<!doctype html>" in body["report_html"].lower()


def test_resume_craft_render_returns_html(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_html",
        lambda payload, runtime=None: "<!DOCTYPE html><html><body><h1>Resume</h1></body></html>",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "history": [
                {"role": "assistant", "content": "请提供你的项目经历。"},
                {"role": "user", "content": "我有 2 年后端开发经验。"},
            ],
            "template_code": "02",
            "language": "zh",
            "photo_pref": "no_photo",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["report_name"].endswith(".html")
    assert "<!doctype html>" in body["report_html"].lower()


def test_resume_craft_render_returns_400_when_photo_missing(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_html",
        lambda payload, runtime=None: "<!DOCTYPE html><html><body><h1>Resume</h1></body></html>",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "history": [{"role": "user", "content": "请生成简历"}],
            "template_code": "02",
            "language": "zh",
            "photo_pref": "with_photo",
        },
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "missing_photo"


def test_resume_craft_render_injects_photo_data_url(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_html",
        lambda payload, runtime=None: (
            "<!DOCTYPE html><html><body><img class='header-photo' src='__PHOTO_DATA_URL__'></body></html>"
        ),
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "history": [{"role": "user", "content": "请生成简历"}],
            "template_code": "02",
            "language": "zh",
            "photo_pref": "with_photo",
            "photo_data_url": "data:image/png;base64,QUJD",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "data:image/png;base64,QUJD" in body["report_html"]
    assert "__PHOTO_DATA_URL__" not in body["report_html"]


def test_resume_craft_render_retries_when_first_response_is_not_html(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    calls = {"count": 0}

    def _fake_render(payload, runtime=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return "plain text only"
        return "```html\n<!DOCTYPE html><html><body>Retry OK</body></html>\n```"

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_html", _fake_render)

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "history": [{"role": "user", "content": "请开始生成简历"}],
            "template_code": "06",
            "language": "both",
            "photo_pref": "no_photo",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "Retry OK" in body["report_html"]
    assert calls["count"] == 2


def test_resume_craft_render_extracts_html_from_second_fenced_block(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_html",
        lambda payload, runtime=None: (
            "先给出说明\n"
            "```json\n"
            '{"note":"preview"}\n'
            "```\n"
            "```html\n"
            "<!DOCTYPE html><html><body><h1>Second Block</h1></body></html>\n"
            "```"
        ),
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "history": [{"role": "user", "content": "请生成简历"}],
            "template_code": "02",
            "language": "zh",
            "photo_pref": "no_photo",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "Second Block" in body["report_html"]


def test_resume_craft_render_uses_local_fallback_when_model_returns_empty(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_html", lambda payload, runtime=None: "")

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "jd_summary": "负责 AI 应用落地",
                "personal_info": {"name": "张三", "phone": "13800000000", "email": "a@b.com", "city": "上海", "links": []},
                "education": [{"school": "X大学", "major": "计算机", "degree": "硕士", "period": "2020-2023", "highlights": ""}],
                "skills": ["Python", "LangChain"],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "finalized_experiences": ["负责 RAG 应用开发，降低响应时延 35%。"],
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "<!doctype html>" in body["report_html"].lower()
    assert "AI应用开发" in body["report_html"]
    assert body["meta"]["resume_craft_render_fallback"] == "local"
