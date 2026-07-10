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
        "run_resume_craft_step4_decision",
        lambda payload, runtime=None: {
            "reply": "这段经历很强，我先整理成可上简历版本，并请你补充时间、指标口径和下一段经历。",
            "resume_ready_draft": {"title": "RAG 检索服务", "role": "核心开发", "period": "时间待补", "bullets": []},
            "missing_points": ["项目起止时间", "指标口径", "是否有下一段经历"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": ["RAG", "检索"],
        },
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
    assert body["meta"]["resume_craft_chat_turn_version"] == "2026-07-10-v9"
    assert body["meta"]["step4_mode"] == "agent_led"
    assert body["meta"]["step4_missing_points"]
    assert body["meta"]["step4_raw_missing_points"]


def test_resume_craft_chat_turn_step1_profile_auto_finalize_after_max_grill(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_step4_decision",
        lambda payload, runtime=None: {
            "reply": "请补充经历结果与量化指标。",
            "resume_ready_draft": {"title": "RAG 服务", "role": "核心开发", "period": "时间待补", "bullets": []},
            "missing_points": ["项目起止时间", "指标口径", "是否有下一段经历"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": ["指标"],
        },
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "结果是响应时延降低 35%。",
            "history": [
                {"role": "assistant", "content": "请补充挑战和行动。"},
                {"role": "user", "content": "挑战是并发抖动明显。"},
            ],
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
                "followup_count": 3,
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
    assert "量化指标" in body["reply"]
    assert body["next_step_suggestion"] == "stay"
    assert body["missing_fields"] == ["experience"]


def test_resume_craft_chat_turn_step4_third_round_stays_grill_and_reports_probe_round(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_step4_decision",
        lambda payload, runtime=None: {
            "reply": "继续围绕该项目补充链路细节。",
            "resume_ready_draft": {"title": "RAG 服务", "role": "核心开发", "period": "时间待补", "bullets": []},
            "missing_points": ["请继续拆解一个关键子模块的输入、处理、输出。"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": ["实现链路"],
            "next_probe_dimension": "implementation",
        },
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我补充了第二轮问题的答案。",
            "history": [
                {"role": "assistant", "content": "我们进入 Step4（工作/项目经历）。请描述第一段经历的场景、职责、行动和结果。"},
                {"role": "user", "content": "第一轮输入"},
                {"role": "assistant", "content": "请继续拆解关键子模块。"},
                {"role": "user", "content": "第二轮输入"},
                {"role": "assistant", "content": "请继续补充链路细节。"},
            ],
            "current_step": 4,
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
                "drafts": ["第一轮输入", "第二轮输入"],
                "finalized_experiences": [],
            },
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "grill_experience"
    assert body["meta"]["step4_probe_round"] == 3
    assert body["next_step_suggestion"] == "stay"


def test_resume_craft_chat_turn_step4_no_more_experience_goes_next(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

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


def test_resume_craft_chat_turn_step4_resets_stale_state_when_history_restarted(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    captured = {}

    def _fake_step4_decision(payload, runtime=None):
        captured.update(payload)
        return {
            "reply": "请补充该核心功能的实现链路细节。",
            "resume_ready_draft": {"title": "项目经历", "role": "核心开发", "period": "时间待补", "bullets": []},
            "missing_points": ["实现链路"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": ["实现链路"],
        }

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_step4_decision", _fake_step4_decision)

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我负责构建多轮面试引擎，包含检索、记忆和追问编排。",
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
            "experience_state": {
                "current_index": 2,
                "followup_count": 3,
                "drafts": ["旧草稿：请补取舍。"],
                "finalized_experiences": ["项目A：时延降低35%。"],
                "active_focus": {
                    "topic": "旧项目",
                    "stage": "tradeoff",
                    "evidence": {"implementation": True, "tradeoff": False, "validation": True},
                    "turn_count": 4,
                },
            },
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "grill_experience"
    assert captured["is_first_round"] is True
    assert captured["followup_count"] == 1
    assert captured["active_focus"]["topic"] == ""
    assert body["experience_state"]["followup_count"] == 1
    assert body["experience_state"]["finalized_experiences"] == ["项目A：时延降低35%。"]


def test_resume_craft_chat_turn_step4_agent_missing_points_followed(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_step4_decision",
        lambda payload, runtime=None: {
            "reply": "这段项目先按简历稿整理好了。请补 3 点：项目时间、指标口径、是否有下一段经历。",
            "resume_ready_draft": {"title": "在线推理服务", "role": "核心开发", "period": "时间待补", "bullets": []},
            "missing_points": ["项目起止时间", "指标口径", "下一段经历"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": ["可用性", "性能"],
        },
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
    assert "请补 3 点" in body["reply"]
    assert body["meta"]["step4_mode"] == "agent_led"
    assert body["meta"]["step4_missing_points"] == ["项目起止时间", "指标口径", "下一段经历"]
    assert body["meta"]["step4_raw_missing_points"] == ["项目起止时间", "指标口径", "下一段经历"]


def test_resume_craft_chat_turn_step4_dynamic_focus_for_different_stack(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    def _fake_step4_decision(payload, runtime=None):
        user_input = str(payload.get("user_input") or "").lower()
        if "k8s" in user_input or "kubernetes" in user_input or "微服务" in user_input:
            return {
                "reply": "这段经历已整理。请补充集群规模、SLO 抖动口径，以及是否还有下一段相关经历。",
                "resume_ready_draft": {"title": "微服务平台", "role": "平台开发", "period": "时间待补", "bullets": []},
                "missing_points": ["集群规模", "SLO 口径", "下一段经历"],
                "current_experience_completed": False,
                "ask_more_experience": True,
                "reasoning_focus": ["k8s", "slo", "微服务治理"],
            }
        return {
            "reply": "请补充项目时间、指标口径和下一段经历。",
            "resume_ready_draft": {"title": "项目经历", "role": "核心开发", "period": "时间待补", "bullets": []},
            "missing_points": ["项目时间", "指标口径", "下一段经历"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": [],
        }

    monkeypatch.setattr(routes.ai_service, "run_resume_craft_step4_decision", _fake_step4_decision)

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "基于 K8s 的微服务平台，做了灰度发布和服务治理，优化了 SLO。",
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
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "grill_experience"
    assert body["meta"]["step4_missing_points"] == ["集群规模", "SLO 口径", "下一段经历"]
    assert "LangChain" not in body["reply"]
    assert "Prompt" not in body["reply"]
    assert body["meta"]["step4_mode"] == "agent_led"


def test_resume_craft_chat_turn_step4_first_round_returns_resume_ready_draft(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_step4_decision",
        lambda payload, runtime=None: {
            "reply": (
                "这段经历很强，我先按你给的信息整理成可上简历版本（待你确认）：\n"
                "Mirrorview智能模拟面试平台｜独立开发｜（时间待补）\n"
                "基于 LangChain + Agentic RAG 架构实现 AI 面试官，支持多轮对话与上下文推理。\n"
                "后端采用 Flask + SQLAlchemy，将面试历史查询接口响应时间优化 42%。\n"
                "请再补充以下信息：\n"
                "这段项目起止时间（如 2025.03-2025.06）\n"
                "响应时间降低 42% 的口径（例如从多少 ms 降到多少 ms；如果没有具体值，保留 42% 也可以）\n"
                "是否还有要补充的经历"
            ),
            "resume_ready_draft": {
                "title": "Mirrorview智能模拟面试平台",
                "role": "独立开发",
                "period": "时间待补",
                "bullets": [
                    "基于 LangChain + Agentic RAG 架构实现 AI 面试官。",
                    "后端采用 Flask + SQLAlchemy，响应时间优化 42%。",
                ],
            },
            "missing_points": ["项目起止时间", "指标口径", "是否有下一段经历"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": ["LangChain", "Flask", "JWT"],
        },
    )

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
    assert "项目起止时间" in body["reply"]
    assert "是否还有要补充的经历" in body["reply"]
    assert body["meta"]["step4_missing_points"] == ["项目起止时间", "指标口径", "是否有下一段经历"]
    assert body["meta"]["step4_mode"] == "agent_led"


def test_resume_craft_chat_turn_step4_first_round_enforces_structured_contract(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_step4_decision",
        lambda payload, runtime=None: {
            "reply": "好的，收到。",
            "resume_ready_draft": {
                "title": "在线推理平台",
                "role": "核心开发",
                "period": "2025.03-2025.06",
                "bullets": ["负责链路重构，平均时延下降 42%。"],
            },
            "missing_points": ["SLO 口径"],
            "current_experience_completed": False,
            "ask_more_experience": True,
            "reasoning_focus": ["slo", "latency"],
        },
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "我负责在线推理平台的链路重构，时延下降 42%。",
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
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "grill_experience"
    assert body["reply"] == "好的，收到。"
    assert body["meta"]["step4_missing_points"] == ["SLO 口径"]
    assert body["meta"]["step4_mode"] == "agent_led"


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


def test_resume_craft_chat_turn_step5_no_more_skills_goes_next(monkeypatch):
    Config.TURNSTILE_ENFORCE = False
    Config.RATE_LIMIT_ENFORCE = False

    monkeypatch.setattr(
        routes.ai_service,
        "run_resume_craft_dialog",
        lambda payload, runtime=None: "好的，我们进入下一阶段。",
    )

    client = _client()
    resp = client.post(
        "/api/careerforge/resume-craft/chat-turn",
        json={
            "message": "没有更多技能了",
            "current_step": 5,
            "history": [{"role": "assistant", "content": "是否还有要补充的技能或证书？"}],
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
                "current_step": 5,
                "collected_by_step": {
                    "education": [],
                    "experiences": ["负责 RAG 项目落地"],
                    "skills_and_certs": ["Python", "LangChain"],
                    "final_preferences": "",
                    "step6_confirmed": False,
                },
            },
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "skills_done"
    assert body["next_step_suggestion"] == "next"
    assert body["missing_fields"] == []
    assert "没有更多技能或证书" in body["reply"]


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
