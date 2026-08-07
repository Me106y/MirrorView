from io import BytesIO

from flask import Flask

from server import routes
from server.config import Config


def _client():
    app = Flask(__name__)
    app.register_blueprint(routes.api, url_prefix="/api")
    app.config["TESTING"] = True
    return app.test_client()


def _disable_guards():
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False


def test_cover_letter_chat_forwards_json_history_and_output(monkeypatch):
    _disable_guards()
    captured = {}

    def fake_agent(payload, runtime=None):
        captured.update(payload)
        return {"reply": "可以，我先确认目标岗位。", "output_text": "", "scenario": "email"}

    monkeypatch.setattr(routes.ai_service, "run_cover_letter_chat", fake_agent)
    response = _client().post(
        "/api/careerforge/cover-letter/chat",
        json={
            "message": "我想申请产品经理",
            "history": [
                {"role": "user", "content": "我有三年经验"},
                {"role": "system", "content": "应该被过滤"},
            ],
            "jd_text": "负责产品规划",
            "scenario": "email",
            "language": "zh",
            "resume_source": "conversation",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["reply"] == "可以，我先确认目标岗位。"
    assert captured["history"] == [{"role": "user", "content": "我有三年经验"}]
    assert captured["resume_source"] == "conversation"


def test_cover_letter_chat_infers_pdf_source_for_multipart(monkeypatch):
    _disable_guards()
    captured = {}
    monkeypatch.setattr(routes, "_extract_resume_text", lambda data: "候选人有数据分析经验")

    def fake_agent(payload, runtime=None):
        captured.update(payload)
        return {"reply": "已读取简历。", "output_text": "", "scenario": "email"}

    monkeypatch.setattr(routes.ai_service, "run_cover_letter_chat", fake_agent)
    response = _client().post(
        "/api/careerforge/cover-letter/chat",
        data={
            "message": "开始撰写",
            "jd_text": "负责数据分析",
            "runtime": '{"mode":"platform"}',
            "resume": (BytesIO(b"pdf"), "resume.pdf"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert captured["resume_source"] == "pdf"
    assert captured["resume_text"] == "候选人有数据分析经验"


def test_cover_letter_chat_returns_bad_gateway_for_agent_error(monkeypatch):
    _disable_guards()
    monkeypatch.setattr(
        routes.ai_service,
        "run_cover_letter_chat",
        lambda payload, runtime=None: {"error": "runtime_call_failed", "message": "模型运行失败。"},
    )

    response = _client().post(
        "/api/careerforge/cover-letter/chat",
        json={"message": "开始", "runtime": {"mode": "platform"}},
    )

    assert response.status_code == 502
    assert response.get_json()["error"] == "runtime_call_failed"
