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
    assert "<!DOCTYPE html>" in body["report_html"]


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
            "photo_pref": "with_photo",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "Retry OK" in body["report_html"]
    assert calls["count"] == 2
