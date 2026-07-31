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
        json={
            "resume_text": "resume",
            "jd_text": "jd",
            "runtime": {"mode": "byok", "provider": "openai", "api_key": "test-key"},
        },
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


def test_resume_match_requires_runtime_payload(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-match",
        json={"resume_text": "resume", "jd_text": "jd"},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "user_runtime_required"


def _resume_craft_profile():
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


def _resume_craft_draft_json():
    return {
        "target_role": "AI 应用开发",
        "personal_info": {
            "name": "候选人",
            "phone": "1",
            "email": "a@example.com",
            "city": "杭州",
            "links": [],
        },
        "education": [],
        "experiences": ["负责 RAG 应用开发，降低响应时延 35%。"],
        "skills_and_certs": ["Python"],
        "final_preferences": "",
    }


def test_resume_craft_chat_turn_returns_400_for_empty_message():
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    response = _client().post(
        "/api/careerforge/resume-craft/chat-turn",
        json={"message": "   ", "step1_profile": _resume_craft_profile()},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "empty_message"


def test_resume_craft_chat_turn_allows_agent_to_handle_missing_step1_profile(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False
    captured = {}

    def fake_agent(payload, runtime=None):
        captured.update(payload)
        return {
            "reply": "请先告诉我你想申请的岗位。",
            "action": "collect",
            "next_step_suggestion": "stay",
            "render_ready": False,
            "missing_fields": ["target_role"],
            "wizard_state": {},
        }

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_chat_turn", fake_agent)

    response = _client().post(
        "/api/careerforge/resume-craft/chat-turn",
        json={"message": "继续分析"},
    )

    assert response.status_code == 200
    assert response.get_json()["reply"].startswith("请先告诉我")
    assert captured["step1_profile"] == {}


def test_resume_craft_chat_turn_delegates_to_skill_agent(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False
    captured = {}

    def fake_agent(payload, runtime=None):
        captured.update(payload)
        return {
            "reply": "请继续说明这段经历中最关键的决策。",
            "action": "collect",
            "next_step_suggestion": "stay",
            "render_ready": False,
            "missing_fields": ["decision"],
            "wizard_state": {"current_step": 4},
        }

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_chat_turn", fake_agent)
    response = _client().post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我负责检索服务。",
            "current_step": 4,
            "step1_profile": _resume_craft_profile(),
            "wizard_state": {"current_step": 4},
        },
    )

    assert response.status_code == 200
    assert response.get_json()["reply"].startswith("请继续说明")
    assert captured["message"] == "我负责检索服务。"
    assert captured["current_step"] == 4


def test_resume_craft_chat_turn_propagates_agent_failure(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False
    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_chat_turn",
        lambda payload, runtime=None: (_ for _ in ()).throw(RuntimeError("model unavailable")),
    )

    response = _client().post(
        "/api/careerforge/resume-craft/chat-turn",
        json={"message": "继续分析", "step1_profile": _resume_craft_profile()},
    )

    assert response.status_code == 502
    assert response.get_json()["error"] == "resume_craft_agent_failed"


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
            "draft_json": _resume_craft_draft_json(),
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
            "draft_json": _resume_craft_draft_json(),
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
            "draft_json": _resume_craft_draft_json(),
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
            "draft_json": _resume_craft_draft_json(),
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
            "draft_json": _resume_craft_draft_json(),
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


def test_resume_craft_render_returns_error_when_model_response_is_not_html(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    calls = {"count": 0}

    def _fake_render(payload, runtime=None):
        calls["count"] += 1
        return "plain text only"

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_html", _fake_render)

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "draft_json": _resume_craft_draft_json(),
            "history": [{"role": "user", "content": "请开始生成简历"}],
            "template_code": "06",
            "language": "both",
            "photo_pref": "no_photo",
        },
    )
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["error"] == "resume_craft_render_failed"
    assert calls["count"] == 1


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
            "draft_json": _resume_craft_draft_json(),
            "history": [{"role": "user", "content": "请生成简历"}],
            "template_code": "02",
            "language": "zh",
            "photo_pref": "no_photo",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "Second Block" in body["report_html"]


def test_resume_craft_render_returns_error_when_model_returns_empty(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_html", lambda payload, runtime=None: "")

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "draft_json": _resume_craft_draft_json(),
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
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["error"] == "resume_craft_render_failed"


def test_resume_craft_render_returns_pdf_payload_when_pdf_generation_succeeds(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_html",
        lambda payload, runtime=None: "<!DOCTYPE html><html><body><h1>Resume</h1></body></html>",
    )
    monkeypatch.setattr(
        routes,
        "_generate_resume_craft_pdf_artifact",
        lambda report_html, report_name: ("候选人-AI应用开发简历.pdf", "UERG", ""),
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/render",
        json={
            "draft_json": _resume_craft_draft_json(),
            "history": [{"role": "user", "content": "请生成简历"}],
            "step1_profile": {
                "template_code": "02",
                "language": "zh",
                "photo_pref": "no_photo",
                "target_role": "AI应用开发",
                "personal_info": {"name": "候选人", "phone": "1", "email": "a@b.com", "city": "杭州", "links": []},
                "education": [],
                "skills": [],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "finalized_experiences": ["负责 RAG 落地并降低时延。"],
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["report_pdf_name"].endswith(".pdf")
    assert body["report_pdf_base64"] == "UERG"
    assert body["meta"]["resume_craft_pdf_generated"] is True


def test_resume_craft_render_rejects_jd_only_facts(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_html",
        lambda payload, runtime=None: (
            "<!DOCTYPE html><html><body>"
            "<h1>简历</h1><p>熟练 Kubernetes Operator 开发。</p>"
            "</body></html>"
        ),
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
                "jd_summary": "熟练 Kubernetes Operator 开发",
                "personal_info": {"name": "候选人", "phone": "1", "email": "a@b.com", "city": "杭州", "links": []},
                "education": [],
                "skills": ["Python"],
                "certificates": [],
                "expected_experience_count": 1,
            },
            "wizard_state": {
                "current_step": 6,
                "collected_by_step": {
                    "education": [],
                    "experiences": ["负责 RAG 平台建设，时延降低35%"],
                    "skills_and_certs": ["Python", "LangChain"],
                    "final_preferences": "",
                    "step6_confirmed": True,
                },
                "step_states": {
                    "step3": {"turn_count": 2, "confirmed": True},
                    "step4": {"current_index": 2, "followup_count": 0, "drafts": [], "finalized_experiences": ["负责 RAG 平台建设，时延降低35%"]},
                    "step5": {"turn_count": 2, "confirmed": True},
                    "step6": {"turn_count": 2, "confirmed": True, "preview_ready": True, "awaiting_confirm": False, "draft_json": {
                        "target_role": "AI应用开发",
                        "personal_info": {"name": "候选人", "phone": "1", "email": "a@b.com", "city": "杭州", "links": []},
                        "education": [],
                        "experiences": ["负责 RAG 平台建设，时延降低35%"],
                        "skills_and_certs": ["Python", "LangChain"],
                        "final_preferences": "",
                    }},
                },
            },
        },
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "unsupported_fact_detected"
