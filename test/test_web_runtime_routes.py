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
