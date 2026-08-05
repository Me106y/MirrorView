from server.services.agents.resume_craft_agent import ResumeCraftAgent


class _JsonModel:
    def __init__(self, output):
        self.output = output

    def __call__(self, _prompt):
        return self.output


def _agent_payload(message, current_step=5, wizard_state=None):
    return {
        "message": message,
        "current_step": current_step,
        "step1_profile": {"target_role": "AI 应用开发"},
        "wizard_state": wizard_state or {"current_step": current_step},
        "history": [],
    }


def test_resume_craft_agent_returns_skill_driven_state():
    model = _JsonModel(
        '{"reply":"请具体说说你在这段经历中的关键决策。",'
        '"action":"collect","next_step_suggestion":"stay",'
        '"render_ready":false,"missing_fields":["decision"],'
        '"wizard_state":{"current_step":4},"step6_preview_markdown":"",'
        '"step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        {
            "message": "我做了一个检索服务。",
            "current_step": 4,
            "step1_profile": {"target_role": "AI 应用开发"},
            "wizard_state": {"current_step": 4},
            "history": [],
        }
    )

    assert result["reply"].startswith("请具体说说")


def test_resume_craft_preserves_skill_decision_to_skip_and_revisit_naturally():
    model = _JsonModel(
        '{"reply":"证书先跳过，之后可以直接补充。",'
        '"action":"advance","next_step_suggestion":"next",'
        '"render_ready":false,"missing_fields":[], '
        '"wizard_state":{"current_step":5,"collected_by_step":{"skills_and_certs":["Python"]},'
        '"step_states":{"step5":{"skipped_dimensions":["certificates"]}}}}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        _agent_payload("证书暂时没有，先跳过", current_step=5)
    )

    assert result["reply"] == "证书先跳过，之后可以直接补充。"
    assert result["action"] == "advance"
    assert result["next_step_suggestion"] == "next"
    assert result["wizard_state"]["step_states"]["step5"]["skipped_dimensions"] == ["certificates"]


def test_resume_craft_preserves_natural_language_revision_after_skip():
    model = _JsonModel(
        '{"reply":"已补充 AWS 证书，并移除过期证书。",'
        '"action":"revise","next_step_suggestion":"stay",'
        '"render_ready":false,"missing_fields":[], '
        '"wizard_state":{"current_step":5,"collected_by_step":{"skills_and_certs":["Python", "AWS Certified Solutions Architect"]},'
        '"step_states":{"step5":{"certificates":["AWS Certified Solutions Architect"]}}}}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        _agent_payload(
            "我后来拿到了 AWS 证书，请补上，并删掉之前过期的证书",
            current_step=5,
            wizard_state={
                "current_step": 5,
                "collected_by_step": {"skills_and_certs": ["Python", "旧证书"]},
            },
        )
    )

    assert result["reply"] == "已补充 AWS 证书，并移除过期证书。"
    assert result["action"] == "revise"
    assert result["wizard_state"]["collected_by_step"]["skills_and_certs"] == [
        "Python",
        "AWS Certified Solutions Architect",
    ]


def test_resume_craft_does_not_invent_reply_when_model_returns_empty_reply():
    model = _JsonModel(
        '{"reply":"","action":"render_ready","next_step_suggestion":"stay",'
        '"render_ready":true,"missing_fields":[],"wizard_state":{"current_step":6},'
        '"step6_preview_markdown":"","step6_waiting_confirm":false,"step6_applied_changes":[]}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        _agent_payload("确认生成", current_step=6, wizard_state={"current_step": 6})
    )

    assert result["reply"] == ""


def test_resume_craft_preview_request_keeps_preview_content_and_not_render_ready():
    model = _JsonModel(
        '{"reply":"请确认以上信息是否需要修改？", "action":"preview",'
        '"next_step_suggestion":"stay", "render_ready":false, "missing_fields":[], '
        '"wizard_state":{"current_step":6,"step_states":{"step6":{'
        '"preview_ready":true,"awaiting_confirm":true,"confirmed":false,'
        '"draft_json":{"target_role":"AI 应用开发"}}}},'
        '"step6_preview_markdown":"# 简历预览\\n\\n目标岗位：AI 应用开发",'
        '"step6_waiting_confirm":true,"step6_applied_changes":[]}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        _agent_payload("生成简历预览", current_step=6, wizard_state={"current_step": 6})
    )

    assert result["action"] == "preview"
    assert result["render_ready"] is False
    assert "目标岗位：AI 应用开发" in result["step6_preview_markdown"]


def test_resume_craft_render_ready_patch_preserves_existing_draft_json():
    model = _JsonModel(
        '{"reply":"", "action":"render_ready", "next_step_suggestion":"stay",'
        '"render_ready":true, "missing_fields":[], "wizard_state":{'
        '"collected_by_step":{"step6_confirmed":true}, "step_states":{"step6":{'
        '"confirmed":true,"awaiting_confirm":false}}},'
        '"step6_preview_markdown":"", "step6_waiting_confirm":false,'
        '"step6_applied_changes":[]}'
    )
    agent = ResumeCraftAgent(llm=model)
    existing_draft = {"target_role": "AI 应用开发", "skills_and_certs": ["Python"]}

    result = agent.run_resume_craft_chat_turn(
        _agent_payload(
            "确认生成",
            current_step=6,
            wizard_state={
                "current_step": 6,
                "collected_by_step": {"step6_confirmed": False},
                "step_states": {
                    "step6": {
                        "preview_ready": True,
                        "awaiting_confirm": True,
                        "confirmed": False,
                        "draft_json": existing_draft,
                    }
                },
            },
        )
    )

    assert result["wizard_state"]["collected_by_step"]["step6_confirmed"] is True
    assert result["wizard_state"]["step_states"]["step6"]["confirmed"] is True
    assert result["wizard_state"]["step_states"]["step6"]["draft_json"] == existing_draft


def test_resume_craft_preserves_draft_when_model_returns_invalid_empty_patch():
    model = _JsonModel(
        '{"reply":"", "action":"render_ready", "next_step_suggestion":"stay",'
        '"render_ready":true, "missing_fields":[], "wizard_state":{'
        '"collected_by_step":{"step6_confirmed":true}, "step_states":{"step6":{'
        '"confirmed":true,"awaiting_confirm":false,"draft_json":""}}},'
        '"step6_preview_markdown":"", "step6_waiting_confirm":false}'
    )
    agent = ResumeCraftAgent(llm=model)
    existing_draft = {"target_role": "AI 应用开发", "skills_and_certs": ["Python"]}

    result = agent.run_resume_craft_chat_turn(
        _agent_payload(
            "确认生成",
            current_step=6,
            wizard_state={
                "current_step": 6,
                "step_states": {"step6": {"draft_json": existing_draft}},
            },
        )
    )

    assert result["wizard_state"]["step_states"]["step6"]["draft_json"] == existing_draft


def test_resume_craft_normalizes_top_level_draft_into_step6_state():
    model = _JsonModel(
        '{"reply":"", "action":"render_ready", "next_step_suggestion":"stay",'
        '"render_ready":true, "missing_fields":[], "draft_json":{'
        '"target_role":"AI 应用开发", "skills_and_certs":["Python"]},'
        '"wizard_state":{"collected_by_step":{"step6_confirmed":true},'
        '"step_states":{"step6":{"confirmed":true,"awaiting_confirm":false}}},'
        '"step6_preview_markdown":"", "step6_waiting_confirm":false}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        _agent_payload("确认生成", current_step=6, wizard_state={"current_step": 6})
    )

    assert result["wizard_state"]["step_states"]["step6"]["draft_json"] == {
        "target_role": "AI 应用开发",
        "skills_and_certs": ["Python"],
    }


def test_resume_craft_normalizes_draft_at_wizard_state_root_into_step6_state():
    model = _JsonModel(
        '{"reply":"", "action":"render_ready", "next_step_suggestion":"stay",'
        '"render_ready":true, "missing_fields":[], "wizard_state":{'
        '"current_step":6, "draft_json":{"target_role":"AI 应用开发",'
        '"skills_and_certs":["Python"]}, "collected_by_step":{"step6_confirmed":true},'
        '"step_states":{"step6":{"confirmed":true,"awaiting_confirm":false}}},'
        '"step6_preview_markdown":"", "step6_waiting_confirm":false}'
    )
    agent = ResumeCraftAgent(llm=model)

    result = agent.run_resume_craft_chat_turn(
        _agent_payload("确认生成", current_step=6, wizard_state={"current_step": 6})
    )

    assert result["wizard_state"]["step_states"]["step6"]["draft_json"] == {
        "target_role": "AI 应用开发",
        "skills_and_certs": ["Python"],
    }
