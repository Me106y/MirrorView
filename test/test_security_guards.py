from types import SimpleNamespace

import pytest

from server.config import Config
from server.security import enforce_high_cost_guard, enforce_rate_limit, verify_turnstile_token


class _DummyResp:
    def __init__(self, data):
        self._data = data
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return self._data


@pytest.fixture(autouse=True)
def _restore_config():
    old = (
        Config.RATE_LIMIT_ENFORCE,
        Config.RATE_LIMIT_REQUESTS,
        Config.RATE_LIMIT_WINDOW_SECONDS,
        Config.TURNSTILE_ENFORCE,
        Config.TURNSTILE_SECRET_KEY,
    )
    yield
    (
        Config.RATE_LIMIT_ENFORCE,
        Config.RATE_LIMIT_REQUESTS,
        Config.RATE_LIMIT_WINDOW_SECONDS,
        Config.TURNSTILE_ENFORCE,
        Config.TURNSTILE_SECRET_KEY,
    ) = old


def test_rate_limit_returns_429_when_exceeded() -> None:
    Config.RATE_LIMIT_ENFORCE = True
    Config.RATE_LIMIT_REQUESTS = 1
    Config.RATE_LIMIT_WINDOW_SECONDS = 60

    ok1, _, _ = enforce_rate_limit("resume-match", "127.0.0.1")
    ok2, status2, body2 = enforce_rate_limit("resume-match", "127.0.0.1")

    assert ok1 is True
    assert ok2 is False
    assert status2 == 429
    assert body2["error"] == "rate_limited"


def test_turnstile_missing_token_fails_when_enforced() -> None:
    Config.TURNSTILE_ENFORCE = True
    Config.TURNSTILE_SECRET_KEY = "dummy"
    ok, reason = verify_turnstile_token("", "127.0.0.1")
    assert ok is False
    assert reason == "missing_turnstile_token"


def test_turnstile_accepts_success_response(monkeypatch) -> None:
    Config.TURNSTILE_ENFORCE = True
    Config.TURNSTILE_SECRET_KEY = "dummy"

    def fake_post(*args, **kwargs):
        return _DummyResp({"success": True})

    monkeypatch.setattr("server.security.requests.post", fake_post)

    ok, reason = verify_turnstile_token("token-1", "127.0.0.1")
    assert ok is True
    assert reason == ""


def test_high_cost_guard_turnstile_failure_returns_403(monkeypatch) -> None:
    Config.RATE_LIMIT_ENFORCE = False
    Config.TURNSTILE_ENFORCE = True
    Config.TURNSTILE_SECRET_KEY = "dummy"

    monkeypatch.setattr("server.security.verify_turnstile_token", lambda token, remote_ip: (False, "turnstile_rejected"))

    ok, status, body = enforce_high_cost_guard("resume-match", "bad-token", "127.0.0.1")
    assert ok is False
    assert status == 403
    assert body["error"] == "turnstile_failed"
