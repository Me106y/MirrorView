from utils.logger_handler import _sanitize_text


def test_sanitize_text_redacts_key_material() -> None:
    raw = "api_key=sk-secret123 authorization=Bearer abc cookie=sessionid"
    sanitized = _sanitize_text(raw)
    assert "sk-secret123" not in sanitized
    assert "Bearer" in sanitized
    assert "***" in sanitized
