from server.runtime_request import build_runtime_meta, parse_runtime_payload


def test_parse_runtime_defaults_to_platform() -> None:
    runtime, err = parse_runtime_payload({})
    assert not err
    assert runtime is not None
    assert runtime["mode"] == "platform"
    assert runtime["provider"]
    assert runtime["model"]


def test_parse_runtime_byok_requires_api_key() -> None:
    runtime, err = parse_runtime_payload(
        {
            "runtime": {
                "mode": "byok",
                "provider": "openai",
                "model": "gpt-4o-mini",
            }
        }
    )
    assert runtime is None
    assert "api_key" in err


def test_parse_runtime_accepts_string_json() -> None:
    runtime, err = parse_runtime_payload(
        {
            "runtime": '{"mode":"byok","provider":"deepseek","api_key":"sk-abc12345","model":"deepseek-chat"}'
        }
    )
    assert not err
    assert runtime is not None
    assert runtime["mode"] == "byok"
    assert runtime["provider"] == "deepseek"


def test_runtime_meta_exposes_safe_fields_only() -> None:
    meta = build_runtime_meta({
        "mode": "byok",
        "provider": "anthropic",
        "api_key": "secret-never-expose",
    })
    assert meta == {
        "runtime_mode": "byok",
        "runtime_provider": "anthropic",
    }
